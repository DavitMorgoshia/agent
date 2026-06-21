# Contract Review Guidelines & Red Flags

**Policy ID:** LEGAL-CG-001 | **Version:** 4.2 | **Effective:** 2024-01-01
**Owner:** Legal & Compliance | **Approved by:** General Counsel

---

## 1. Auto-Renewal Clauses

### Policy
- Auto-renewal clauses are acceptable IF the notice period is at least **30 days**.
- Notice periods under 30 days must be renegotiated to minimum 30 days.
- Preferred: **60-day notice period** for contracts over $50,000/year.
- All auto-renewal contracts must be tracked in the contract management system with calendar alerts.

### Flag Criteria
- Auto-renewal with notice period < 30 days → **MUST NEGOTIATE**
- Auto-renewal with no notice period specified → **FLAG FOR LEGAL**
- Multi-year auto-renewal (renews for more than 1 year at a time) → **FLAG FOR REVIEW**

---

## 2. Liability and Indemnification

### Acceptable Liability Caps
- Liability cap equal to 12 months' contract fees: **Standard, acceptable**
- Liability cap equal to 6 months' fees: **Acceptable for low-risk services**
- Liability cap equal to 24+ months' fees or contract value: **Favorable — note as positive**
- **Uncapped liability on vendor side**: Favorable for us — note but don't flag
- **Uncapped liability on our side**: **FLAG IMMEDIATELY — legal review required**

### Mutual vs. One-Sided Indemnification
- Mutual indemnification for IP infringement: Standard, acceptable
- One-sided indemnification (we indemnify them, they don't indemnify us): **FLAG FOR LEGAL**

---

## 3. Intellectual Property

- Work product created under the contract should belong to the company, not the vendor.
- Vendor retains background IP; company gets license to use it: **Acceptable**
- Vendor retains ALL IP including work product: **FLAG FOR LEGAL — must negotiate**
- Open-source components must have OSS license compatibility review.

---

## 4. Data Handling

- GDPR-compliant Data Processing Agreement (DPA) required if vendor handles EU personal data.
- Data residency: EU data must stay in EU unless adequacy decision or SCCs in place.
- Data deletion on termination: Must be specified, within 30-90 days.
- No contract should allow vendor to use our data for their own purposes without explicit consent.

---

## 5. Termination Rights

### Acceptable Termination Clauses
- Termination for convenience with 30-60 day notice: **Standard**
- Termination for cause (material breach) with 30-day cure period: **Standard**

### Problem Clauses
- No termination for convenience: **FLAG — must negotiate in**
- Termination for convenience requires more than 90 days notice: **FLAG**
- No cure period for termination for cause: **FLAG FOR LEGAL**
- Termination fees / penalties: **FLAG — requires Finance approval**

---

## 6. Governing Law

- Preferred governing law: **State of Delaware (USA)** or jurisdiction where we operate
- International arbitration acceptable for multi-national vendors
- **Vendor's home jurisdiction only** (especially non-US): **FLAG FOR LEGAL**
- Mandatory arbitration clauses that waive class action: **FLAG FOR LEGAL**

---

## 7. Confidence Thresholds for Auto-Processing

Contracts should be AUTO-STORED (no human review needed) only if ALL of the following:
- Confidence score ≥ 0.75
- No critical red flags identified
- Vendor is in APPROVED status
- Payment terms are Net-30 or compliant
- SLA meets minimum requirements OR contract is not a service contract
- No policy violations identified

Everything else → FLAG FOR HUMAN REVIEW with specific reasons.
