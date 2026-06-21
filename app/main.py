"""
FastAPI application: vendor contract intake via email webhook.

Endpoints:
  POST /webhook/mailgun     — Mailgun inbound parse webhook
  POST /webhook/postmark    — Postmark inbound webhook (alternative)
  POST /test/upload         — Direct file upload for local testing
  GET  /contracts           — List auto-stored contracts
  GET  /review-queue        — List flagged contracts
  GET  /stats               — Summary statistics
  POST /seed-kb             — (Re)seed the knowledge base
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .extractor import extract_contract_data, get_document_text
from .llm import LLMClient, create_client
from .models import ProcessingResult, ProcessingStatus
from .notifier import send_notification
from .rag import seed_knowledge_base, validate_with_rag
from .router import decide_routing
from .storage import get_contracts, get_review_queue, get_stats, init_db, save_result

# Load .env from the project root regardless of where uvicorn was launched from
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Contract Intake Agent",
    description="AI-powered vendor contract processing via email",
    version="1.0.0",
)

def _get_llm_client() -> LLMClient:
    try:
        return create_client()
    except ValueError as e:
        raise HTTPException(500, str(e))


@app.on_event("startup")
async def startup():
    init_db()
    try:
        n = seed_knowledge_base()
        logger.info("Knowledge base ready: %d chunks", n)
    except Exception as e:
        logger.error("KB seed failed: %s — RAG will degrade gracefully", e)


async def _process_attachment(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    email_sender: str,
    email_subject: str,
    client: LLMClient,
) -> ProcessingResult:
    """Core processing pipeline: extract → RAG → route → store → notify."""
    processing_id = str(uuid.uuid4())
    notes = []

    # Step 1: Extract text from the file
    logger.info("Extracting text from %s (%s)", filename, content_type)
    try:
        text, file_type = get_document_text(file_bytes, filename, content_type, client)
        notes.append(f"Text extracted using {file_type}")
    except Exception as e:
        logger.error("Text extraction failed: %s", e)
        result = ProcessingResult(
            id=processing_id,
            status=ProcessingStatus.EXTRACTION_FAILED,
            review_reasons=[f"File could not be read: {str(e)}"],
            email_sender=email_sender,
            email_subject=email_subject,
            file_name=filename,
            processed_at=datetime.utcnow(),
            processing_notes=[f"Extraction error: {str(e)}"],
        )
        save_result(result)
        send_notification(result)
        return result

    if len(text.strip()) < 50:
        result = ProcessingResult(
            id=processing_id,
            status=ProcessingStatus.EXTRACTION_FAILED,
            review_reasons=["Attached file appears empty or unreadable"],
            email_sender=email_sender,
            email_subject=email_subject,
            file_name=filename,
            processed_at=datetime.utcnow(),
            processing_notes=["Empty text extracted"],
        )
        save_result(result)
        send_notification(result)
        return result

    # Step 2: LLM extraction
    logger.info("Running LLM extraction (text length: %d chars)", len(text))
    try:
        extraction = extract_contract_data(text, client)
        notes.append(f"Extraction confidence: {extraction.confidence_score:.0%}")
    except Exception as e:
        logger.error("LLM extraction failed: %s", e)
        result = ProcessingResult(
            id=processing_id,
            status=ProcessingStatus.EXTRACTION_FAILED,
            review_reasons=[f"LLM extraction error: {str(e)}"],
            email_sender=email_sender,
            email_subject=email_subject,
            file_name=filename,
            file_type=file_type,
            processed_at=datetime.utcnow(),
            processing_notes=notes + [f"LLM error: {str(e)}"],
        )
        save_result(result)
        send_notification(result)
        return result

    # Step 3: RAG validation
    logger.info("Running RAG validation for vendor: %s", extraction.vendor_name)
    try:
        rag_validation = validate_with_rag(extraction, client)
        notes.append(f"RAG risk level: {rag_validation.overall_risk_level}")
    except Exception as e:
        logger.error("RAG validation failed: %s", e)
        from .models import RAGValidation
        rag_validation = RAGValidation(
            enrichment_notes=[f"RAG unavailable: {str(e)}"],
            overall_risk_level="medium",
        )
        notes.append("RAG validation failed — defaulting to medium risk")

    # Step 4: Route
    status, review_reasons = decide_routing(extraction, rag_validation)
    logger.info("Routing decision: %s (%d reasons)", status.value, len(review_reasons))

    result = ProcessingResult(
        id=processing_id,
        status=status,
        extraction=extraction,
        rag_validation=rag_validation,
        review_reasons=review_reasons,
        email_sender=email_sender,
        email_subject=email_subject,
        file_name=filename,
        file_type=file_type if "file_type" in dir() else None,
        processed_at=datetime.utcnow(),
        processing_notes=notes,
    )

    # Step 5: Store and notify
    save_result(result)
    send_notification(result)

    return result


# ─────────────────────────────────────────────
# Mailgun Inbound Parse Webhook
# ─────────────────────────────────────────────

@app.post("/webhook/mailgun")
async def mailgun_webhook(request: Request):
    """
    Receives Mailgun inbound parse webhook.
    Mailgun sends multipart/form-data with attachment-N fields.
    """
    form = await request.form()

    sender = str(form.get("sender") or form.get("from") or "unknown@unknown.com")
    subject = str(form.get("subject") or "No Subject")
    attachment_count = int(form.get("attachment-count") or 0)

    logger.info("Mailgun webhook: from=%s, subject=%s, attachments=%d",
                sender, subject, attachment_count)

    if attachment_count == 0:
        return JSONResponse({"status": "skipped", "reason": "No attachments"})

    client = _get_llm_client()
    results = []

    for i in range(1, attachment_count + 1):
        attachment = form.get(f"attachment-{i}")
        if not attachment:
            continue

        file_bytes = await attachment.read()
        filename = attachment.filename or f"attachment-{i}"
        content_type = attachment.content_type or "application/octet-stream"

        result = await _process_attachment(
            file_bytes, filename, content_type, sender, subject, client
        )
        results.append({"id": result.id, "status": result.status.value, "file": filename})

    return JSONResponse({"status": "processed", "results": results})


# ─────────────────────────────────────────────
# Postmark Inbound Webhook (alternative)
# ─────────────────────────────────────────────

@app.post("/webhook/postmark")
async def postmark_webhook(request: Request):
    """
    Receives Postmark inbound webhook (JSON format).
    """
    body = await request.json()

    sender = body.get("From") or body.get("FromFull", {}).get("Email") or "unknown"
    subject = body.get("Subject") or "No Subject"
    attachments = body.get("Attachments") or []

    logger.info("Postmark webhook: from=%s, subject=%s, attachments=%d",
                sender, subject, len(attachments))

    if not attachments:
        return JSONResponse({"status": "skipped", "reason": "No attachments"})

    import base64
    client = _get_llm_client()
    results = []

    for att in attachments:
        filename = att.get("Name") or "attachment"
        content_type = att.get("ContentType") or "application/octet-stream"
        content_b64 = att.get("Content") or ""

        try:
            file_bytes = base64.b64decode(content_b64)
        except Exception:
            results.append({"file": filename, "error": "Base64 decode failed"})
            continue

        result = await _process_attachment(
            file_bytes, filename, content_type, sender, subject, client
        )
        results.append({"id": result.id, "status": result.status.value, "file": filename})

    return JSONResponse({"status": "processed", "results": results})


# ─────────────────────────────────────────────
# Direct Upload (for local testing / demo)
# ─────────────────────────────────────────────

@app.post("/test/upload")
async def test_upload(
    file: UploadFile = File(...),
    sender: str = Form(default="test@example.com"),
    subject: str = Form(default="Test Contract Upload"),
):
    """
    Direct file upload for testing without email setup.
    POST multipart/form-data with 'file', optional 'sender', 'subject'.
    """
    client = _get_llm_client()
    file_bytes = await file.read()
    filename = file.filename or "uploaded_file"
    content_type = file.content_type or "application/octet-stream"

    logger.info("Direct upload: file=%s, size=%d bytes", filename, len(file_bytes))

    result = await _process_attachment(
        file_bytes, filename, content_type, sender, subject, client
    )

    return JSONResponse(result.model_dump(mode="json"))


# ─────────────────────────────────────────────
# Read API
# ─────────────────────────────────────────────

@app.get("/contracts")
async def list_contracts(limit: int = 50):
    return JSONResponse(get_contracts(limit))


@app.get("/review-queue")
async def list_review_queue(resolved: bool = False, limit: int = 50):
    return JSONResponse(get_review_queue(resolved=resolved, limit=limit))


@app.get("/stats")
async def stats():
    return JSONResponse(get_stats())


@app.post("/seed-kb")
async def reseed_knowledge_base(force: bool = False):
    n = seed_knowledge_base(force=force)
    return JSONResponse({"chunks_loaded": n})


@app.get("/health")
async def health():
    return {"status": "ok"}
