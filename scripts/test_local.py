#!/usr/bin/env python3.9
"""
Local test script — processes a contract file directly without email setup.
Uses the /test/upload endpoint or runs the pipeline inline.

Usage:
  python3.9 scripts/test_local.py sample_contracts/01_clean_contract.pdf
  python3.9 scripts/test_local.py sample_contracts/02_messy_contract.pdf --sender legal@vendor.com
  python3.9 scripts/test_local.py sample_contracts/03_risky_contract.pdf
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx


def test_via_api(file_path: Path, sender: str, subject: str, base_url: str) -> dict:
    """POST file to the running server's /test/upload endpoint."""
    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, _guess_content_type(file_path))}
        data = {"sender": sender, "subject": subject}

        with httpx.Client(timeout=120) as client:
            resp = client.post(f"{base_url}/test/upload", files=files, data=data)

    resp.raise_for_status()
    return resp.json()


def test_inline(file_path: Path, sender: str, subject: str) -> dict:
    """Run the pipeline directly without a running server."""
    import os
    import uuid
    from datetime import datetime

    from dotenv import load_dotenv
    load_dotenv()

    from app.extractor import extract_contract_data, get_document_text
    from app.llm import create_client, get_provider
    from app.models import ProcessingResult, ProcessingStatus
    from app.notifier import send_notification
    from app.rag import seed_knowledge_base, validate_with_rag
    from app.router import decide_routing
    from app.storage import init_db, save_result

    try:
        client = create_client()
        print(f"  Using provider: {get_provider()}")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    init_db()

    print("  [1/4] Seeding knowledge base...")
    seed_knowledge_base()

    file_bytes = file_path.read_bytes()
    content_type = _guess_content_type(file_path)

    print(f"  [2/4] Extracting text from {file_path.name}...")
    t0 = time.time()
    text, file_type = get_document_text(file_bytes, file_path.name, content_type, client)
    print(f"        Done in {time.time()-t0:.1f}s — {len(text)} chars ({file_type})")

    print("  [3/4] Running LLM extraction...")
    t0 = time.time()
    extraction = extract_contract_data(text, client)
    print(f"        Done in {time.time()-t0:.1f}s — confidence: {extraction.confidence_score:.0%}")

    print("  [4/4] Running RAG validation...")
    t0 = time.time()
    rag = validate_with_rag(extraction, client)
    print(f"        Done in {time.time()-t0:.1f}s — risk: {rag.overall_risk_level}")

    status, reasons = decide_routing(extraction, rag)

    result = ProcessingResult(
        id=str(uuid.uuid4()),
        status=status,
        extraction=extraction,
        rag_validation=rag,
        review_reasons=reasons,
        email_sender=sender,
        email_subject=subject,
        file_name=file_path.name,
        processed_at=datetime.utcnow(),
    )

    save_result(result)
    send_notification(result)

    return result.model_dump(mode="json")


def _guess_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".txt": "text/plain",
        ".csv": "text/csv",
    }.get(ext, "application/octet-stream")


def pretty_print_result(result: dict) -> None:
    status = result.get("status", "unknown")
    e = result.get("extraction") or {}
    r = result.get("rag_validation") or {}

    border = "=" * 65
    print(f"\n{border}")
    print(f"  PROCESSING RESULT")
    print(f"{border}")
    print(f"  Status:        {status.upper()}")
    print(f"  ID:            {result.get('id', 'N/A')[:8]}...")
    print(f"  File:          {result.get('file_name', 'N/A')}")
    print()

    if e:
        print("  EXTRACTION:")
        print(f"    Vendor:        {e.get('vendor_name', 'N/A')}")
        print(f"    Type:          {e.get('contract_type', 'N/A')}")
        val = e.get('contract_value_usd')
        print(f"    Value:         {'${:,.0f}'.format(val) if val else 'N/A'}")
        print(f"    Dates:         {e.get('start_date', 'N/A')} → {e.get('end_date', 'N/A')}")
        print(f"    Payment:       Net-{e.get('payment_terms_days', '?')}")
        print(f"    Auto-renewal:  {e.get('auto_renewal', 'N/A')}")
        print(f"    SLA uptime:    {e.get('sla_uptime_percent', 'N/A')}%")
        print(f"    Governing law: {e.get('governing_law', 'N/A')}")
        print(f"    Confidence:    {e.get('confidence_score', 0):.0%}")

        if e.get("potential_red_flags"):
            print("\n  RED FLAGS:")
            for flag in e["potential_red_flags"]:
                print(f"    ⚠  {flag}")

        if e.get("missing_critical_fields"):
            print(f"\n  MISSING FIELDS: {', '.join(e['missing_critical_fields'])}")

    if r:
        print(f"\n  RAG VALIDATION:")
        print(f"    Vendor known:     {r.get('vendor_known', False)}")
        print(f"    Vendor status:    {r.get('vendor_approval_status', 'UNKNOWN')}")
        print(f"    Payment ok:       {r.get('payment_terms_compliant', '?')}")
        print(f"    SLA ok:           {r.get('sla_compliant', '?')}")
        print(f"    Overall risk:     {r.get('overall_risk_level', 'unknown').upper()}")

        if r.get("policy_violations"):
            print("\n  POLICY VIOLATIONS:")
            for v in r["policy_violations"]:
                print(f"    ✗  {v}")

        if r.get("enrichment_notes"):
            print("\n  ENRICHMENT NOTES:")
            for n in r["enrichment_notes"]:
                print(f"    ℹ  {n}")

    if result.get("review_reasons"):
        print(f"\n  REVIEW REASONS:")
        for reason in result["review_reasons"]:
            print(f"    →  {reason}")

    print(f"\n{border}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test contract processing locally")
    parser.add_argument("file", help="Path to contract file (PDF, image, or text)")
    parser.add_argument("--sender", default="vendor@example.com", help="Email sender")
    parser.add_argument("--subject", default="Contract for Review", help="Email subject")
    parser.add_argument("--server", default=None,
                        help="Server URL (e.g. http://localhost:8000). If omitted, runs inline.")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    print(f"\nProcessing: {file_path.name}")
    print(f"Sender: {args.sender} | Subject: {args.subject}\n")

    if args.server:
        print(f"Using server: {args.server}")
        result = test_via_api(file_path, args.sender, args.subject, args.server)
    else:
        print("Running inline (no server needed)...")
        result = test_inline(file_path, args.sender, args.subject)

    pretty_print_result(result)

    # Also save raw JSON for inspection
    out_path = Path("data") / f"result_{file_path.stem}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"Full JSON saved to: {out_path}")
