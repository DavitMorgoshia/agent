"""
Document text extraction and LLM-powered structured data extraction.

Handles PDFs (text-based and scanned), images, and plain text files.
Uses LLMClient vision for image/scanned content, PyMuPDF for text PDFs.
"""

import base64
import json
import logging
import re
from typing import Optional, Tuple

import fitz  # PyMuPDF

from .llm import LLMClient
from .models import ContractExtraction

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT_TEMPLATE = """You are a contract analyst. Extract structured information from the vendor contract text below.

Return a JSON object with EXACTLY these fields (use null for missing/unclear values, not empty strings):
{{
  "vendor_name": string or null,
  "vendor_email": string or null,
  "vendor_address": string or null,
  "contract_type": one of ["software_license", "services", "maintenance", "nda", "partnership", "other"] or null,
  "contract_value_usd": number (USD equivalent) or null,
  "currency": string (ISO code like "USD", "EUR") or null,
  "start_date": "YYYY-MM-DD" or null,
  "end_date": "YYYY-MM-DD" or null,
  "payment_terms_days": integer (30 for Net-30, 60 for Net-60) or null,
  "payment_schedule": one of ["monthly", "quarterly", "annual", "one_time", "milestone"] or null,
  "governing_law": string (jurisdiction) or null,
  "auto_renewal": boolean or null,
  "termination_notice_days": integer or null,
  "liability_cap_usd": number or null,
  "sla_uptime_percent": number (e.g. 99.9) or null,
  "sla_response_time_hours": number or null,
  "key_obligations": [list of strings, max 5, most important obligations],
  "potential_red_flags": [list of strings - unusual clauses, one-sided terms, missing protections],
  "confidence_score": float 0.0-1.0 (your confidence in the overall extraction quality),
  "missing_critical_fields": [list of field names that are clearly absent from the document]
}}

Rules:
- Be conservative with confidence_score: only give 0.8+ when the document is clear and complete
- List real red flags, not boilerplate concerns (e.g. "unlimited liability clause", "no SLA defined", "auto-renewal with 90-day notice")
- For missing_critical_fields, only list fields that are genuinely absent (not just fields where you're uncertain)
- Do not invent data — use null rather than guessing

CONTRACT TEXT:
{text}
"""

OCR_PROMPT = (
    "Extract ALL text from this document image. "
    "Preserve the structure as much as possible. "
    "Return only the extracted text, nothing else."
)

OCR_PAGES_PROMPT = (
    "Extract ALL text from these document pages. "
    "Combine all pages into a single continuous text, preserving structure. "
    "Return only the extracted text."
)


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, bool]:
    """Returns (text, is_scanned). is_scanned hints that Vision would do better."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text = []
    total_chars = 0

    for page in doc:
        text = page.get_text("text")
        pages_text.append(text)
        total_chars += len(text.strip())

    doc.close()
    full_text = "\n\n--- PAGE BREAK ---\n\n".join(pages_text)
    avg_chars = total_chars / max(len(pages_text), 1)
    return full_text, avg_chars < 100


def get_pdf_page_images(file_bytes: bytes, max_pages: int = 5) -> list:
    """Convert first N PDF pages to base64 PNG strings for vision models."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        images.append(base64.standard_b64encode(pix.tobytes("png")).decode("utf-8"))
    doc.close()
    return images


def get_document_text(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    client: LLMClient,
) -> Tuple[str, str]:
    """
    Extract text from any supported file type.
    Returns (extracted_text, file_type_label).
    """
    fname_lower = filename.lower()
    ct_lower = content_type.lower()

    if "pdf" in ct_lower or fname_lower.endswith(".pdf"):
        text, is_scanned = extract_text_from_pdf(file_bytes)
        if is_scanned or len(text.strip()) < 200:
            logger.info("PDF appears scanned — using vision extraction")
            pages = get_pdf_page_images(file_bytes)
            text = client.complete_with_pages(OCR_PAGES_PROMPT, pages, tier="fast", max_tokens=8192)
            return text, "scanned_pdf"
        return text, "pdf"

    if any(ct_lower.startswith(t) for t in ["image/jpeg", "image/png", "image/webp", "image/gif"]):
        mt = ct_lower.split(";")[0].strip()
        text = client.complete_with_image(OCR_PROMPT, file_bytes, mt, tier="fast", max_tokens=4096)
        return text, "image"

    if "text" in ct_lower or fname_lower.endswith((".txt", ".md", ".csv")):
        return file_bytes.decode("utf-8", errors="replace"), "text"

    # Fallback: try PDF parse, then raw text
    try:
        text, is_scanned = extract_text_from_pdf(file_bytes)
        if len(text.strip()) > 50:
            return text, "pdf_fallback"
    except Exception:
        pass

    return file_bytes.decode("utf-8", errors="replace"), "text_fallback"


def extract_contract_data(
    text: str,
    client: LLMClient,
    use_smart: bool = False,
) -> ContractExtraction:
    """
    Send extracted text to the LLM for structured JSON extraction.
    Uses the fast model by default; escalates to smart on low confidence or parse failure.
    """
    tier = "smart" if use_smart else "fast"

    text_for_prompt = text[:8000]
    if len(text) > 8000:
        text_for_prompt += f"\n\n[...{len(text) - 9000} chars omitted...]\n\n" + text[-1000:]

    prompt = EXTRACTION_PROMPT_TEMPLATE.format(text=text_for_prompt)

    raw = client.complete(prompt, tier=tier, max_tokens=2048).strip()

    # Strip markdown code fences if the model wrapped its output
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("JSON parse failed (%s) — retrying with smart model", e)
        if not use_smart:
            return extract_contract_data(text, client, use_smart=True)
        return ContractExtraction(
            confidence_score=0.1,
            missing_critical_fields=["all fields — extraction failed"],
            raw_text_excerpt=text[:500],
        )

    try:
        extraction = ContractExtraction(
            vendor_name=data.get("vendor_name"),
            vendor_email=data.get("vendor_email"),
            vendor_address=data.get("vendor_address"),
            contract_type=data.get("contract_type"),
            contract_value_usd=_to_float(data.get("contract_value_usd")),
            currency=data.get("currency"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            payment_terms_days=_to_int(data.get("payment_terms_days")),
            payment_schedule=data.get("payment_schedule"),
            governing_law=data.get("governing_law"),
            auto_renewal=data.get("auto_renewal"),
            termination_notice_days=_to_int(data.get("termination_notice_days")),
            liability_cap_usd=_to_float(data.get("liability_cap_usd")),
            sla_uptime_percent=_to_float(data.get("sla_uptime_percent")),
            sla_response_time_hours=_to_float(data.get("sla_response_time_hours")),
            key_obligations=data.get("key_obligations") or [],
            potential_red_flags=data.get("potential_red_flags") or [],
            confidence_score=float(data.get("confidence_score") or 0.5),
            missing_critical_fields=data.get("missing_critical_fields") or [],
            raw_text_excerpt=text[:300],
        )

        if extraction.confidence_score < 0.6 and not use_smart:
            logger.info("Low confidence (%.2f) — retrying with smart model", extraction.confidence_score)
            return extract_contract_data(text, client, use_smart=True)

        return extraction

    except Exception as e:
        logger.error("Model mapping error: %s | raw: %s", e, data)
        return ContractExtraction(
            confidence_score=0.2,
            missing_critical_fields=["extraction mapping failed"],
            raw_text_excerpt=text[:300],
        )


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def _to_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return None
