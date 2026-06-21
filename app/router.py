"""
Routing logic: decide whether a processed contract goes to auto-storage
or gets flagged for human review, with specific reasons.
"""

from typing import List, Tuple

from .models import ContractExtraction, ProcessingStatus, RAGValidation

# Thresholds
MIN_CONFIDENCE_FOR_AUTO = 0.75
CRITICAL_FIELDS = ["vendor_name", "contract_value_usd", "start_date", "end_date", "payment_terms_days"]


def decide_routing(
    extraction: ContractExtraction,
    rag: RAGValidation,
) -> Tuple[ProcessingStatus, List[str]]:
    """
    Evaluate extraction + RAG results and return (status, reasons).

    Auto-storage requires ALL of:
      - confidence >= 0.75
      - no critical fields missing
      - vendor APPROVED (not unknown/restricted/on-hold)
      - payment terms compliant
      - SLA compliant (or non-applicable)
      - no policy violations
      - no high-severity red flags
    """
    reasons = []

    # 1. Confidence check
    if extraction.confidence_score < MIN_CONFIDENCE_FOR_AUTO:
        reasons.append(
            f"Low extraction confidence ({extraction.confidence_score:.0%}) — document may be unclear or incomplete"
        )

    # 2. Missing critical fields
    missing = [f for f in CRITICAL_FIELDS if f in extraction.missing_critical_fields]
    if missing:
        reasons.append(f"Missing critical fields: {', '.join(missing)}")

    # 3. Vendor status
    status = rag.vendor_approval_status
    if not rag.vendor_known or status == "UNKNOWN":
        reasons.append(
            f"Vendor '{extraction.vendor_name or 'unknown'}' not found in approved vendor registry — "
            "vendor onboarding required before contract execution"
        )
    elif status == "ON_HOLD":
        reasons.append(
            f"Vendor '{extraction.vendor_name}' is ON HOLD — pending compliance audit. Do not process."
        )
    elif status == "RESTRICTED":
        reasons.append(
            f"Vendor '{extraction.vendor_name}' is RESTRICTED — requires C-level approval."
        )
    elif status == "PROBATIONARY":
        reasons.append(
            f"Vendor '{extraction.vendor_name}' is PROBATIONARY — legal sign-off required."
        )

    # 4. Payment terms
    if not rag.payment_terms_compliant:
        for issue in rag.payment_terms_issues:
            reasons.append(f"Payment terms: {issue}")

    # 5. SLA compliance
    if not rag.sla_compliant:
        for issue in rag.sla_issues:
            reasons.append(f"SLA: {issue}")

    # 6. Policy violations
    for violation in rag.policy_violations:
        reasons.append(f"Policy violation: {violation}")

    # 7. Auto-renewal check
    if rag.auto_renewal_flagged:
        notice = extraction.termination_notice_days
        if notice is not None and notice < 30:
            reasons.append(
                f"Auto-renewal notice period ({notice} days) is below minimum 30 days"
            )
        elif notice is None:
            reasons.append("Auto-renewal clause present but notice period not specified")

    # 8. Red flags from extraction
    high_severity_keywords = [
        "unlimited liability", "waive", "indemnify", "perpetual", "irrevocable",
        "no termination", "no refund", "binding arbitration", "class action waiver"
    ]
    for flag in extraction.potential_red_flags:
        flag_lower = flag.lower()
        if any(kw in flag_lower for kw in high_severity_keywords):
            reasons.append(f"Red flag (legal review needed): {flag}")

    # 9. High risk rating from RAG
    if rag.overall_risk_level == "high" and not reasons:
        reasons.append("RAG assessment rated this contract as HIGH RISK — manual review required")

    # Determine status
    if reasons:
        return ProcessingStatus.FLAGGED_FOR_REVIEW, reasons
    return ProcessingStatus.AUTO_STORED, []
