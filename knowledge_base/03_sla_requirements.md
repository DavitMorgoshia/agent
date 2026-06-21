# Minimum SLA Requirements for Vendor Contracts

**Policy ID:** OPS-SLA-005 | **Version:** 2.0 | **Effective:** 2024-03-01
**Owner:** IT Operations | **Approved by:** CTO

---

## 1. Uptime Requirements by Service Tier

### Tier 1 — Mission-Critical Systems
Services that directly affect production, customer-facing operations, or revenue.
- **Minimum uptime SLA: 99.9%** (allows ~8.7 hrs downtime/year)
- **Incident response: P1 within 1 hour**, P2 within 4 hours
- **RTO (Recovery Time Objective): 4 hours max**
- **RPO (Recovery Point Objective): 1 hour max**
- Examples: Core infrastructure, payment systems, authentication services

### Tier 2 — Business-Critical Systems
Internal tools, analytics, secondary integrations.
- **Minimum uptime SLA: 99.5%** (allows ~43.8 hrs downtime/year)
- **Incident response: P1 within 4 hours**, P2 within 8 hours
- **RTO: 8 hours max**
- Examples: CRM, analytics platforms, internal portals

### Tier 3 — Non-Critical Systems
Development tools, nice-to-have services.
- **Minimum uptime SLA: 99.0%** (allows ~87.6 hrs downtime/year)
- **Incident response: Next business day acceptable**
- Examples: Developer tools, supplementary reporting

---

## 2. SLA Penalty / Credit Requirements
- Contracts must include **SLA credits** for downtime below guaranteed uptime.
- Minimum credit structure: 10% monthly fee credit per 0.1% below SLA threshold.
- Contracts with **no SLA credits defined** must be flagged for negotiation.
- Credits should be automatic (no claim required) or easily claimable.

---

## 3. Monitoring and Reporting
- Vendor must provide **monthly uptime reports**.
- Incident post-mortems required for outages over 1 hour.
- Third-party monitoring (e.g., StatusPage, Pingdom) preferred over self-reported uptime.

---

## 4. Data and Security SLAs
- **Data breach notification: Within 72 hours** (GDPR/compliance requirement).
- **Security patch response: Critical within 24 hours**, High within 7 days.
- Vendors handling PII must be GDPR-compliant and document it.

---

## 5. Support SLA Requirements
- Business hours support minimum for all vendor contracts.
- 24/7 support required for Tier 1 services.
- Dedicated account manager required for contracts over $100,000/year.
- Escalation path must be defined and documented in contract.

---

## 6. Contract Flags — When to Escalate
- Uptime SLA below minimum for tier → **Flag for IT Operations**
- No SLA credit mechanism defined → **Flag for negotiation**
- Breach notification over 72 hours → **Flag for Legal/Compliance**
- No incident reporting process → **Flag for IT Operations**
