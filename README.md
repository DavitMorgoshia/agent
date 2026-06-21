# Contract Intake Agent

An AI-powered system that processes vendor contracts arriving by email — extracts structured data, validates against company policies (RAG), and routes to storage or human review.

## What It Does

1. **Email intake** — Mailgun (or Postmark) forwards attachment emails to a webhook
2. **Extraction** — Claude reads the attached PDF/image/text and returns structured JSON
3. **RAG validation** — ChromaDB knowledge base with internal policies; Claude checks vendor approval status, payment terms compliance, SLA minimums, and auto-renewal rules
4. **Routing** — High-confidence, compliant contracts go to SQLite; anything flagged goes to review queue with specific reasons
5. **Notification** — Slack (or console) notification with result summary

## Architecture

```
Email arrives
     │
     ▼
[Mailgun/Postmark Webhook]
     │
     ▼
[FastAPI /webhook/* endpoint]
     │
     ├─► [File text extraction]
     │       PDF (PyMuPDF) or scanned/image (Claude Vision)
     │
     ├─► [LLM Extraction — Claude Haiku]
     │       → ContractExtraction JSON
     │       (low confidence → retry with Claude Sonnet)
     │
     ├─► [RAG Validation — ChromaDB + Claude Sonnet]
     │       Queries: approved vendors, payment policy,
     │                SLA requirements, contract guidelines
     │       → RAGValidation JSON
     │
     ├─► [Router]
     │       confidence ≥ 0.75 + no violations → AUTO_STORED
     │       otherwise → FLAGGED_FOR_REVIEW (with reasons)
     │
     ├─► [SQLite storage]
     │       contracts table (auto-stored)
     │       review_queue table (flagged)
     │
     └─► [Slack notification]
             Green: auto-stored details
             Red: review required + reasons
```

## Quickstart

### 1. Prerequisites

```bash
python3.9 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY (required)
# Set SLACK_WEBHOOK_URL if you want Slack notifications
```

### 3. Generate sample PDFs

```bash
python3.9 scripts/generate_samples.py
# Creates sample_contracts/01_clean_contract.pdf
#              sample_contracts/02_messy_contract.pdf
#              sample_contracts/03_risky_contract.pdf
```

### 4. Run the test script (no email setup needed)

```bash
# Process each sample contract inline (no server required)
python3.9 scripts/test_local.py sample_contracts/01_clean_contract.pdf
python3.9 scripts/test_local.py sample_contracts/02_messy_contract.pdf
python3.9 scripts/test_local.py sample_contracts/03_risky_contract.pdf
```

### 5. (Optional) Run the server

```bash
uvicorn app.main:app --reload
```

Then test via HTTP:
```bash
curl -X POST http://localhost:8000/test/upload \
  -F "file=@sample_contracts/01_clean_contract.pdf" \
  -F "sender=vendor@technovasolutions.com" \
  -F "subject=Contract for Review"
```

Check results:
```bash
curl http://localhost:8000/stats
curl http://localhost:8000/contracts
curl http://localhost:8000/review-queue
```

---

## Email Setup (Mailgun)

### 1. Sign up for Mailgun (free tier works)
- Go to [mailgun.com](https://mailgun.com) → add a domain or use their sandbox
- Under **Receiving** → **Routes** → Create a route:
  - **Filter**: `match_recipient("contracts@yourdomain.com")`
  - **Actions**: `forward("https://your-host/webhook/mailgun")` + `store()`

### 2. Expose your server
For local dev, use [ngrok](https://ngrok.com):
```bash
ngrok http 8000
# Copy the https URL, e.g. https://abc123.ngrok.io
# Set Mailgun route to: https://abc123.ngrok.io/webhook/mailgun
```

For production, deploy to any cloud provider (Fly.io, Railway, Render, etc.).

### 3. Send a test email
Send an email with a PDF attachment to `contracts@yourdomain.com`.

---

## Sample Contracts — Expected Results

| File | Vendor | Expected Result | Key Reasons |
|------|--------|-----------------|-------------|
| `01_clean_contract.pdf` | TechNova Solutions | **AUTO_STORED** | Approved vendor, Net-30, 99.95% SLA, clean terms |
| `02_messy_contract.pdf` | Quantum Dynamics Ltd. | **FLAGGED** | Unknown vendor, Net-60, missing SLA credits, IP clause issue, 15-day auto-renewal notice |
| `03_risky_contract.pdf` | GlobalSync Solutions | **FLAGGED** | Restricted vendor, Net-60, $500 liability cap, unlimited client indemnification, 10-day auto-renewal |

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook/mailgun` | Mailgun inbound parse webhook |
| `POST` | `/webhook/postmark` | Postmark inbound webhook |
| `POST` | `/test/upload` | Direct file upload (no email needed) |
| `GET` | `/contracts` | List auto-stored contracts |
| `GET` | `/review-queue` | List flagged contracts (`?resolved=true` for resolved) |
| `GET` | `/stats` | Processing statistics |
| `POST` | `/seed-kb` | Re-seed knowledge base (`?force=true` to rebuild) |
| `GET` | `/health` | Health check |

---

## Knowledge Base

The RAG system draws from 4 internal policy documents in `knowledge_base/`:

- `01_approved_vendors.md` — Registry of approved, restricted, and on-hold vendors
- `02_payment_policy.md` — Acceptable payment terms, value thresholds, CFO approval requirements
- `03_sla_requirements.md` — Minimum uptime SLAs by service tier, incident response times
- `04_contract_guidelines.md` — Auto-renewal rules, liability caps, IP ownership, termination rights

To update policies, edit these files and run:
```bash
curl -X POST http://localhost:8000/seed-kb?force=true
# or
python3.9 scripts/seed_kb.py --force
```

---

## Project Structure

```
contract-processor/
├── app/
│   ├── main.py         # FastAPI webhooks + REST API
│   ├── models.py       # Pydantic schemas
│   ├── extractor.py    # PDF/image text extraction + LLM extraction
│   ├── rag.py          # ChromaDB seeding and querying
│   ├── router.py       # Routing decision logic
│   ├── storage.py      # SQLite persistence
│   └── notifier.py     # Slack notifications
├── knowledge_base/     # Policy documents (edit these to tune RAG)
├── scripts/
│   ├── generate_samples.py   # Generate 3 test PDFs
│   ├── seed_kb.py            # Seed ChromaDB
│   └── test_local.py         # Run pipeline without email
├── sample_contracts/   # Generated test PDFs
├── data/               # Runtime: SQLite DB + ChromaDB (gitignored)
├── .env.example
├── requirements.txt
└── docker-compose.yml
```

---

## Design Decisions

**Why Haiku for extraction, Sonnet for RAG?**
Extraction is a structured prompt with clear output format — Haiku handles it fast and cheaply. RAG analysis requires cross-referencing multiple policy chunks against extracted data and reasoning about compliance, which benefits from Sonnet's stronger reasoning. Low-confidence extractions automatically escalate to Sonnet.

**Why ChromaDB?**
Zero-config local vector store. The knowledge base is small (4 documents) and doesn't need a hosted service. ChromaDB's default embedding function (all-MiniLM-L6-v2 via ONNX) runs locally without an embedding API call.

**Why SQLite?**
Two tables, append-mostly, no concurrent writes, demo-friendly. A production system would use PostgreSQL.

**Confidence threshold = 0.75**
Conservative enough to catch unclear documents while not over-flagging clean ones. Claude is instructed to under-score rather than over-score.
