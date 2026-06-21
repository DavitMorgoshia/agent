from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class ContractType(str, Enum):
    SOFTWARE_LICENSE = "software_license"
    SERVICES = "services"
    MAINTENANCE = "maintenance"
    NDA = "nda"
    PARTNERSHIP = "partnership"
    OTHER = "other"


class ContractExtraction(BaseModel):
    vendor_name: Optional[str] = None
    vendor_email: Optional[str] = None
    vendor_address: Optional[str] = None
    contract_type: Optional[ContractType] = None
    contract_value_usd: Optional[float] = None
    currency: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    payment_terms_days: Optional[int] = None
    payment_schedule: Optional[str] = None
    governing_law: Optional[str] = None
    auto_renewal: Optional[bool] = None
    termination_notice_days: Optional[int] = None
    liability_cap_usd: Optional[float] = None
    sla_uptime_percent: Optional[float] = None
    sla_response_time_hours: Optional[float] = None
    key_obligations: List[str] = []
    potential_red_flags: List[str] = []
    confidence_score: float = 0.0
    missing_critical_fields: List[str] = []
    raw_text_excerpt: Optional[str] = None


class RAGValidation(BaseModel):
    vendor_known: bool = False
    vendor_approval_status: Optional[str] = None
    vendor_category: Optional[str] = None
    payment_terms_compliant: bool = True
    payment_terms_issues: List[str] = []
    sla_compliant: bool = True
    sla_issues: List[str] = []
    auto_renewal_flagged: bool = False
    policy_violations: List[str] = []
    enrichment_notes: List[str] = []
    overall_risk_level: str = "unknown"
    matching_policy_excerpts: List[str] = []


class ProcessingStatus(str, Enum):
    AUTO_STORED = "auto_stored"
    FLAGGED_FOR_REVIEW = "flagged_for_review"
    EXTRACTION_FAILED = "extraction_failed"


class ProcessingResult(BaseModel):
    id: str
    status: ProcessingStatus
    extraction: Optional[ContractExtraction] = None
    rag_validation: Optional[RAGValidation] = None
    review_reasons: List[str] = []
    email_subject: Optional[str] = None
    email_sender: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    processed_at: datetime
    processing_notes: List[str] = []
