"""
Notifications via Slack webhook and console logging.
Gracefully degrades when SLACK_WEBHOOK_URL is not configured.
"""

import logging
import os
from typing import List, Optional

import httpx

from .models import ProcessingResult, ProcessingStatus

logger = logging.getLogger(__name__)


def _slack_webhook_url() -> Optional[str]:
    return os.getenv("SLACK_WEBHOOK_URL")


def _format_currency(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    return f"${val:,.0f}"


def send_notification(result: ProcessingResult) -> None:
    """Send Slack notification (or log to console if no webhook configured)."""
    message = _build_message(result)
    url = _slack_webhook_url()

    if url:
        _send_slack(url, message)
    else:
        _log_console(result, message)


def _build_message(result: ProcessingResult) -> dict:
    e = result.extraction
    r = result.rag_validation

    vendor = e.vendor_name if e else "Unknown Vendor"
    value = _format_currency(e.contract_value_usd if e else None)
    confidence = f"{e.confidence_score:.0%}" if e else "N/A"
    risk = r.overall_risk_level if r else "unknown"

    if result.status == ProcessingStatus.AUTO_STORED:
        color = "#2ecc71"
        title = f"Contract Auto-Stored: {vendor}"
        summary = (
            f"A vendor contract has been automatically stored.\n"
            f"*Vendor:* {vendor} ({r.vendor_approval_status if r else 'unknown'})\n"
            f"*Value:* {value} | *Confidence:* {confidence} | *Risk:* {risk}"
        )
        if e:
            summary += (
                f"\n*Type:* {e.contract_type.value if e.contract_type else 'N/A'}"
                f" | *Dates:* {e.start_date or 'N/A'} → {e.end_date or 'N/A'}"
                f"\n*Payment Terms:* Net-{e.payment_terms_days or '?'}"
                f" | *Governing Law:* {e.governing_law or 'N/A'}"
            )
        actions_text = "✅ Stored in database. No action required."

    elif result.status == ProcessingStatus.FLAGGED_FOR_REVIEW:
        color = "#e74c3c"
        title = f"Contract Flagged for Review: {vendor}"
        summary = (
            f"A vendor contract requires human review before processing.\n"
            f"*Vendor:* {vendor}\n"
            f"*File:* {result.file_name or 'N/A'} | *From:* {result.email_sender or 'N/A'}\n"
            f"*Confidence:* {confidence} | *Risk:* {risk}"
        )
        reasons_text = "\n".join(f"• {r}" for r in result.review_reasons[:5])
        if len(result.review_reasons) > 5:
            reasons_text += f"\n• ... and {len(result.review_reasons) - 5} more"
        summary += f"\n\n*Review Reasons:*\n{reasons_text}"
        actions_text = "⚠️ Manual review required. Check the review queue."

    else:
        color = "#95a5a6"
        title = f"Contract Extraction Failed"
        summary = (
            f"Failed to extract contract data from attached file.\n"
            f"*File:* {result.file_name or 'N/A'} | *From:* {result.email_sender or 'N/A'}\n"
            f"*Reasons:* {'; '.join(result.review_reasons[:3])}"
        )
        actions_text = "❌ Manual processing required."

    return {
        "attachments": [{
            "color": color,
            "title": title,
            "text": summary,
            "footer": actions_text,
            "footer_icon": "https://platform.slack-edge.com/img/default_application_icon.png",
            "fields": [
                {"title": "Processing ID", "value": result.id[:8], "short": True},
                {"title": "Subject", "value": result.email_subject or "N/A", "short": True},
            ],
        }]
    }


def _send_slack(webhook_url: str, message: dict) -> None:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(webhook_url, json=message)
            if resp.status_code != 200:
                logger.warning("Slack webhook returned %d: %s", resp.status_code, resp.text)
            else:
                logger.info("Slack notification sent")
    except Exception as e:
        logger.error("Failed to send Slack notification: %s", e)


def _log_console(result: ProcessingResult, message: dict) -> None:
    attachment = message["attachments"][0]
    border = "=" * 60
    logger.info("\n%s\n[NOTIFICATION] %s\n%s\n%s\n%s",
                border, attachment["title"], border,
                attachment["text"], attachment["footer"])
