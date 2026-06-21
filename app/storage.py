"""
SQLite persistence for processing results.
Two tables: contracts (auto-stored clean ones) and review_queue (flagged ones).
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from .models import ProcessingResult, ProcessingStatus

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "contracts.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                vendor_name TEXT,
                contract_type TEXT,
                contract_value_usd REAL,
                start_date TEXT,
                end_date TEXT,
                payment_terms_days INTEGER,
                governing_law TEXT,
                sla_uptime_percent REAL,
                auto_renewal INTEGER,
                email_sender TEXT,
                email_subject TEXT,
                file_name TEXT,
                confidence_score REAL,
                vendor_approval_status TEXT,
                overall_risk_level TEXT,
                full_json TEXT NOT NULL,
                processed_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_queue (
                id TEXT PRIMARY KEY,
                vendor_name TEXT,
                email_sender TEXT,
                email_subject TEXT,
                file_name TEXT,
                review_reasons TEXT NOT NULL,
                confidence_score REAL,
                overall_risk_level TEXT,
                full_json TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                resolved INTEGER DEFAULT 0,
                resolved_at TEXT,
                resolver_notes TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_contracts_vendor ON contracts(vendor_name)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_review_resolved ON review_queue(resolved)
        """)


def save_result(result: ProcessingResult) -> None:
    """Persist a processing result to the appropriate table."""
    full_json = result.model_dump_json()
    e = result.extraction
    r = result.rag_validation

    with _get_conn() as conn:
        if result.status == ProcessingStatus.AUTO_STORED:
            conn.execute("""
                INSERT OR REPLACE INTO contracts
                (id, status, vendor_name, contract_type, contract_value_usd,
                 start_date, end_date, payment_terms_days, governing_law,
                 sla_uptime_percent, auto_renewal, email_sender, email_subject,
                 file_name, confidence_score, vendor_approval_status,
                 overall_risk_level, full_json, processed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                result.id,
                result.status.value,
                e.vendor_name if e else None,
                e.contract_type.value if e and e.contract_type else None,
                e.contract_value_usd if e else None,
                e.start_date if e else None,
                e.end_date if e else None,
                e.payment_terms_days if e else None,
                e.governing_law if e else None,
                e.sla_uptime_percent if e else None,
                int(e.auto_renewal) if e and e.auto_renewal is not None else None,
                result.email_sender,
                result.email_subject,
                result.file_name,
                e.confidence_score if e else None,
                r.vendor_approval_status if r else None,
                r.overall_risk_level if r else None,
                full_json,
                result.processed_at.isoformat(),
            ))
        else:
            conn.execute("""
                INSERT OR REPLACE INTO review_queue
                (id, vendor_name, email_sender, email_subject, file_name,
                 review_reasons, confidence_score, overall_risk_level, full_json, processed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                result.id,
                e.vendor_name if e else None,
                result.email_sender,
                result.email_subject,
                result.file_name,
                json.dumps(result.review_reasons),
                e.confidence_score if e else None,
                r.overall_risk_level if r else None,
                full_json,
                result.processed_at.isoformat(),
            ))


def get_contracts(limit: int = 50) -> List[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contracts ORDER BY processed_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_review_queue(resolved: bool = False, limit: int = 50) -> List[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM review_queue WHERE resolved=? ORDER BY processed_at DESC LIMIT ?",
            (int(resolved), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    with _get_conn() as conn:
        total_contracts = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        pending_review = conn.execute(
            "SELECT COUNT(*) FROM review_queue WHERE resolved=0"
        ).fetchone()[0]
        resolved_review = conn.execute(
            "SELECT COUNT(*) FROM review_queue WHERE resolved=1"
        ).fetchone()[0]
        total_value = conn.execute(
            "SELECT COALESCE(SUM(contract_value_usd), 0) FROM contracts"
        ).fetchone()[0]
    return {
        "auto_stored": total_contracts,
        "pending_review": pending_review,
        "resolved_review": resolved_review,
        "total_contract_value_usd": total_value,
    }
