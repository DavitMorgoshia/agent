"""
RAG module: ChromaDB vector store backed by internal policy documents.

On first run, seeds the knowledge base from ./knowledge_base/*.md files.
Querying returns the most relevant policy excerpts, then a Claude call
interprets them against the extracted contract data.
"""

# Patch sqlite3 with a newer bundled version — required on systems with sqlite < 3.35
try:
    import pysqlite3 as _pysqlite3
    import sys as _sys
    _sys.modules["sqlite3"] = _pysqlite3
except ImportError:
    pass

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.utils import embedding_functions

from .llm import LLMClient
from .models import ContractExtraction, RAGValidation

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent / "knowledge_base"
CHROMA_PERSIST_DIR = Path(__file__).parent.parent / "data" / "chromadb"

RAG_ANALYSIS_PROMPT = """You are a contract compliance analyst. Based on the retrieved policy excerpts, evaluate this contract extraction.

CONTRACT EXTRACTION:
{extraction_json}

RELEVANT POLICY EXCERPTS:
{policy_excerpts}

Return a JSON object (no markdown) with:
{{
  "vendor_known": boolean (true if vendor name appears in approved vendor registry),
  "vendor_approval_status": "APPROVED" | "PROBATIONARY" | "ON_HOLD" | "RESTRICTED" | "UNKNOWN",
  "vendor_category": string or null (category from registry if found),
  "payment_terms_compliant": boolean,
  "payment_terms_issues": [list of specific policy violations for payment terms],
  "sla_compliant": boolean,
  "sla_issues": [list of specific SLA policy violations],
  "auto_renewal_flagged": boolean (true if auto_renewal=true with notice < 30 days, or notice not specified),
  "policy_violations": [list of specific policy violations found, each as a clear sentence],
  "enrichment_notes": [list of useful notes, e.g. vendor tier, applicable policies, positive observations],
  "overall_risk_level": "low" | "medium" | "high",
  "matching_policy_excerpts": [list of 1-3 most relevant policy quotes you used]
}}

Be specific. Reference exact policy thresholds (e.g. "Net-60 exceeds maximum Net-45 for contracts over $250k").
If information is missing from the extraction, note it as a potential issue but don't fabricate data.
"""


def _get_chroma_client() -> chromadb.PersistentClient:
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))


def _get_collection(client: chromadb.PersistentClient) -> chromadb.Collection:
    ef = embedding_functions.DefaultEmbeddingFunction()
    return client.get_or_create_collection(
        name="contract_policies",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks for better retrieval."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += chunk_size - overlap
    return chunks


def seed_knowledge_base(force: bool = False) -> int:
    """
    Load knowledge base documents into ChromaDB.
    Returns number of chunks loaded. Skips if already seeded (unless force=True).
    """
    client = _get_chroma_client()
    collection = _get_collection(client)

    if not force and collection.count() > 0:
        logger.info("Knowledge base already seeded (%d chunks)", collection.count())
        return collection.count()

    if force:
        client.delete_collection("contract_policies")
        collection = _get_collection(client)

    md_files = sorted(KNOWLEDGE_BASE_DIR.glob("*.md"))
    if not md_files:
        logger.warning("No .md files found in %s", KNOWLEDGE_BASE_DIR)
        return 0

    all_ids, all_texts, all_metas = [], [], []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        doc_name = md_file.stem
        chunks = _chunk_text(content)

        for chunk_idx, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{doc_name}-{chunk_idx}".encode()).hexdigest()
            all_ids.append(chunk_id)
            all_texts.append(chunk)
            all_metas.append({
                "source": doc_name,
                "chunk_index": chunk_idx,
                "total_chunks": len(chunks),
            })

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(all_ids), batch_size):
        collection.upsert(
            ids=all_ids[i:i + batch_size],
            documents=all_texts[i:i + batch_size],
            metadatas=all_metas[i:i + batch_size],
        )

    total = collection.count()
    logger.info("Seeded knowledge base: %d chunks from %d files", total, len(md_files))
    return total


def query_policies(
    extraction: ContractExtraction,
    n_results: int = 8,
) -> List[str]:
    """
    Build targeted queries from extraction data and retrieve relevant policy chunks.
    """
    client = _get_chroma_client()
    collection = _get_collection(client)

    if collection.count() == 0:
        logger.warning("Knowledge base is empty — seeding now")
        seed_knowledge_base()

    # Build focused queries based on what was extracted
    queries = []

    if extraction.vendor_name:
        queries.append(f"approved vendor {extraction.vendor_name} registry approval status")

    if extraction.payment_terms_days is not None:
        queries.append(f"payment terms Net-{extraction.payment_terms_days} policy compliance")

    if extraction.auto_renewal:
        notice = extraction.termination_notice_days or "unspecified"
        queries.append(f"auto-renewal clause notice period {notice} days policy")

    if extraction.sla_uptime_percent:
        queries.append(f"SLA uptime {extraction.sla_uptime_percent}% minimum requirements")

    if extraction.contract_value_usd:
        queries.append(f"contract value ${extraction.contract_value_usd:.0f} approval authority threshold")

    if extraction.governing_law:
        queries.append(f"governing law jurisdiction {extraction.governing_law} policy")

    if extraction.liability_cap_usd:
        queries.append("liability cap indemnification acceptable clause")

    if not queries:
        queries = ["contract review policy red flags guidelines", "vendor approval payment terms SLA"]

    # Deduplicate results across queries
    seen_ids = set()
    all_docs = []

    for query in queries:
        try:
            results = collection.query(
                query_texts=[query],
                n_results=min(4, collection.count()),
            )
            docs = results.get("documents", [[]])[0]
            ids = results.get("ids", [[]])[0]
            for doc_id, doc in zip(ids, docs):
                if doc_id not in seen_ids and doc.strip():
                    seen_ids.add(doc_id)
                    all_docs.append(doc)
        except Exception as e:
            logger.warning("Query failed for '%s': %s", query, e)

    return all_docs[:n_results]


def validate_with_rag(
    extraction: ContractExtraction,
    client: LLMClient,
) -> RAGValidation:
    """
    Query the knowledge base and use Claude to interpret policy relevance
    against the extracted contract data.
    """
    policy_chunks = query_policies(extraction)

    if not policy_chunks:
        logger.warning("No policy chunks retrieved — returning minimal validation")
        return RAGValidation(
            enrichment_notes=["Knowledge base unavailable — manual policy check required"],
            overall_risk_level="medium",
        )

    excerpts_text = "\n\n---\n\n".join(
        f"[Source: {i + 1}]\n{chunk}" for i, chunk in enumerate(policy_chunks)
    )

    extraction_dict = extraction.model_dump(exclude={"raw_text_excerpt"})
    prompt = RAG_ANALYSIS_PROMPT.format(
        extraction_json=json.dumps(extraction_dict, indent=2),
        policy_excerpts=excerpts_text,
    )

    raw = client.complete(prompt, tier="smart", max_tokens=2048).strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
        return RAGValidation(
            vendor_known=data.get("vendor_known", False),
            vendor_approval_status=data.get("vendor_approval_status"),
            vendor_category=data.get("vendor_category"),
            payment_terms_compliant=data.get("payment_terms_compliant", True),
            payment_terms_issues=data.get("payment_terms_issues") or [],
            sla_compliant=data.get("sla_compliant", True),
            sla_issues=data.get("sla_issues") or [],
            auto_renewal_flagged=data.get("auto_renewal_flagged", False),
            policy_violations=data.get("policy_violations") or [],
            enrichment_notes=data.get("enrichment_notes") or [],
            overall_risk_level=data.get("overall_risk_level", "medium"),
            matching_policy_excerpts=data.get("matching_policy_excerpts") or [],
        )
    except (json.JSONDecodeError, Exception) as e:
        logger.error("RAG validation parse error: %s | raw: %s", e, raw[:200])
        return RAGValidation(
            enrichment_notes=["RAG validation parse error — manual review recommended"],
            overall_risk_level="medium",
        )
