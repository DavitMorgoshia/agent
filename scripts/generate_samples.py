#!/usr/bin/env python3.9
"""
Generate 3 sample vendor contract PDFs for demo purposes.

  1. clean_contract.pdf   — TechNova Solutions, well-formatted, should AUTO-STORE
  2. messy_contract.pdf   — Poor scan quality simulation, missing fields, should FLAG
  3. risky_contract.pdf   — Unknown vendor, Net-60 terms, auto-renewal issues, should FLAG
"""

import sys
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    print("fpdf2 not installed. Run: pip3.9 install fpdf2")
    sys.exit(1)

OUTPUT_DIR = Path(__file__).parent.parent / "sample_contracts"
OUTPUT_DIR.mkdir(exist_ok=True)


def make_pdf(filename: str, title: str, sections: list) -> None:
    from fpdf.enums import XPos, YPos

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    usable_w = pdf.w - pdf.l_margin - pdf.r_margin

    # Header
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(usable_w, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(3)
    pdf.set_draw_color(100, 100, 100)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(5)

    for section_title, lines in sections:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(usable_w, 6, section_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        for line in lines:
            if line == "":
                pdf.ln(2)
            else:
                pdf.multi_cell(usable_w, 5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)

    path = OUTPUT_DIR / filename
    pdf.output(str(path))
    print(f"Generated: {path}")


def generate_clean_contract():
    """
    Sample 1: Clean contract from an approved vendor.
    Expected result: AUTO_STORED
    """
    sections = [
        ("PARTIES", [
            "This Software License and Services Agreement ('Agreement') is entered into as of",
            "January 15, 2025, by and between:",
            "",
            "VENDOR: TechNova Solutions, Inc.",
            "Address: 1200 Innovation Drive, Suite 400, Austin, TX 78701",
            "Contact: contracts@technovasolutions.com",
            "Represented by: Sarah Chen, VP of Enterprise Sales",
            "",
            "CLIENT: Acme Corporation ('Client')",
            "Address: 500 Main Street, Atlanta, GA 30301",
        ]),
        ("CONTRACT DETAILS", [
            "Contract Type: Software License & Professional Services",
            "Contract ID: TNS-2025-0042",
            "Effective Date: February 1, 2025",
            "Expiration Date: January 31, 2026",
            "Total Contract Value: USD $95,000",
            "",
            "Breakdown:",
            "  - Annual Software License Fee: $70,000",
            "  - Implementation Services: $15,000 (one-time)",
            "  - Annual Support & Maintenance: $10,000",
        ]),
        ("PAYMENT TERMS", [
            "Payment Schedule: Annual (12-month billing cycle)",
            "Payment Terms: Net-30 from date of invoice",
            "Currency: United States Dollar (USD)",
            "",
            "Invoice Schedule:",
            "  - Implementation fee invoiced upon contract signature",
            "  - Annual license fee invoiced on February 1, 2025",
            "  - Support fee invoiced on February 1, 2025",
        ]),
        ("SERVICE LEVEL AGREEMENT", [
            "Uptime Guarantee: 99.95% measured monthly",
            "Scheduled Maintenance: Sundays 2:00 AM - 4:00 AM ET (excluded from SLA)",
            "",
            "Incident Response Times:",
            "  - Priority 1 (Critical): Response within 1 hour, resolution within 4 hours",
            "  - Priority 2 (High): Response within 4 hours, resolution within 8 hours",
            "  - Priority 3 (Medium): Response within 1 business day",
            "",
            "SLA Credits: If uptime falls below 99.95%, Client receives credit equal to",
            "10% of monthly fee for each 0.1% below SLA, up to 50% monthly fee.",
            "",
            "Support Hours: 24/7 for P1 incidents; business hours (9am-6pm ET) for others.",
        ]),
        ("TERM AND TERMINATION", [
            "Initial Term: 12 months from Effective Date",
            "Renewal: This Agreement will automatically renew for successive 1-year terms",
            "unless either party provides 60 days written notice of non-renewal.",
            "",
            "Termination for Convenience: Either party may terminate with 30 days notice.",
            "Termination for Cause: Either party may terminate immediately upon material",
            "breach that remains uncured after 30 days written notice.",
        ]),
        ("LIABILITY AND INDEMNIFICATION", [
            "Limitation of Liability: Each party's total liability shall not exceed the",
            "aggregate fees paid in the 12 months preceding the claim.",
            "",
            "Indemnification: Mutual indemnification for IP infringement claims.",
            "TechNova indemnifies Client against third-party IP infringement claims",
            "arising from use of the licensed software.",
        ]),
        ("GOVERNING LAW", [
            "This Agreement is governed by the laws of the State of Delaware, USA.",
            "Disputes shall be resolved through binding arbitration in Delaware,",
            "under JAMS Comprehensive Arbitration Rules.",
        ]),
        ("SIGNATURES", [
            "IN WITNESS WHEREOF, the parties have executed this Agreement.",
            "",
            "TechNova Solutions, Inc.:",
            "Signature: ___________________  Date: January 15, 2025",
            "Name: Sarah Chen, VP Enterprise Sales",
            "",
            "Acme Corporation:",
            "Signature: ___________________  Date: January 15, 2025",
            "Name: Michael Torres, CFO",
        ]),
    ]

    make_pdf("01_clean_contract.pdf",
             "SOFTWARE LICENSE AND SERVICES AGREEMENT",
             sections)


def generate_messy_contract():
    """
    Sample 2: Poorly formatted contract with missing fields.
    Simulates a scanned or handwritten contract.
    Expected result: FLAGGED (low confidence + missing fields + unknown vendor)
    """
    sections = [
        ("VENDOR SERVICES AGREEMENT", [
            "This agreement is between Quantum Dynamics Ltd. and the undersigned client.",
            "Date: sometime in Q1 2025 (exact date TBD upon signature)",
            "",
            "Services: Data analytics platform subscription and consulting",
            "Note: Exact scope to be defined in separate Statement of Work",
        ]),
        ("FEES AND BILLING", [
            "Monthly subscription: $8,500 per month",
            "NOTE: Price subject to change with 30 days notice",
            "",
            "Payment: Net 60 days from invoice receipt",
            "Late payment fee: 2% per month on outstanding balance",
            "",
            "Setup/onboarding fee: $25,000 due upon contract signing (non-refundable)",
        ]),
        ("SERVICE LEVELS", [
            "Vendor will use commercially reasonable efforts to maintain service availability.",
            "Target uptime: approximately 99% but not guaranteed.",
            "No SLA credits are provided under this agreement.",
            "Support provided during business hours. Emergency contact available.",
        ]),
        ("TERM", [
            "Initial term: 24 months",
            "Auto-renews for 12-month periods unless either party provides written notice",
            "of non-renewal at least 15 days prior to expiration.",
            "",
            "Early termination: Client may terminate with 90 days notice.",
            "Early termination fee: 3 months remaining fees.",
        ]),
        ("INTELLECTUAL PROPERTY", [
            "All work product, customizations, and modifications created by Vendor",
            "shall remain the sole and exclusive property of Quantum Dynamics Ltd.",
            "Client receives a non-exclusive, non-transferable license to use deliverables.",
        ]),
        ("GOVERNING LAW", [
            "This agreement shall be governed by the laws of England and Wales.",
            "All disputes shall be subject to exclusive jurisdiction of English courts.",
        ]),
        ("MISCELLANEOUS", [
            "This agreement contains the entire understanding. Amendments must be in writing.",
            "If any provision is found invalid, the remainder continues in effect.",
        ]),
    ]

    make_pdf("02_messy_contract.pdf",
             "VENDOR SERVICES AGREEMENT",
             sections)


def generate_risky_contract():
    """
    Sample 3: Contract from restricted vendor with multiple red flags.
    Expected result: FLAGGED (multiple violations)
    """
    sections = [
        ("MASTER SERVICES AGREEMENT", [
            "This Master Services Agreement ('MSA') is effective March 1, 2025",
            "",
            "SERVICE PROVIDER: GlobalSync Solutions, LLC",
            "Address: 888 Commerce Way, Miami, FL 33101",
            "Contact: contracts@globalsync.io",
            "",
            "CLIENT: Acme Corporation",
        ]),
        ("SERVICES AND FEES", [
            "Service: Enterprise Data Integration Platform",
            "Annual License Fee: $320,000 USD",
            "Professional Services: $80,000 USD",
            "Total Year 1: $400,000 USD",
            "",
            "Pricing escalation: 8% per year for years 2 and 3.",
        ]),
        ("PAYMENT TERMS", [
            "Invoice terms: Net-60 from invoice date",
            "All fees for the full contract year are due upfront upon contract signing.",
            "No refunds for any reason including early termination.",
            "Currency: USD. No foreign currency accepted.",
            "",
            "If payment is not received within Net-60 terms, GlobalSync may",
            "immediately suspend services without additional notice.",
        ]),
        ("TERM AND AUTO-RENEWAL", [
            "Initial Term: 3 years (March 1, 2025 - February 28, 2028)",
            "Automatic Renewal: This agreement automatically renews for 3-year periods.",
            "Non-renewal notice must be delivered no later than 10 days before expiration.",
            "",
            "Early termination: No right to terminate for convenience during initial term.",
            "Termination for cause requires 90-day cure period.",
        ]),
        ("LIMITATION OF LIABILITY", [
            "GLOBALSYNC'S TOTAL LIABILITY IS LIMITED TO $500 (FIVE HUNDRED DOLLARS).",
            "GLOBALSYNC IS NOT LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, OR",
            "CONSEQUENTIAL DAMAGES UNDER ANY CIRCUMSTANCES.",
            "",
            "CLIENT SHALL INDEMNIFY AND HOLD HARMLESS GLOBALSYNC AGAINST ALL CLAIMS,",
            "DAMAGES, AND LOSSES INCLUDING LEGAL FEES, ARISING FROM CLIENT'S USE.",
            "THIS INDEMNIFICATION IS UNLIMITED IN SCOPE.",
        ]),
        ("DATA AND PRIVACY", [
            "GlobalSync may use anonymized client data to improve its services and",
            "for benchmarking, research, and marketing purposes without additional consent.",
            "Data deletion upon termination: within 2 years after contract end.",
        ]),
        ("GOVERNING LAW", [
            "This agreement is governed exclusively by the laws of the Republic of Panama.",
            "All disputes shall be resolved by arbitration in Panama City, Panama.",
            "Client waives any right to bring claims in Client's local courts.",
            "Class action waiver: Client waives right to participate in any class action.",
        ]),
    ]

    make_pdf("03_risky_contract.pdf",
             "MASTER SERVICES AGREEMENT - ENTERPRISE DATA PLATFORM",
             sections)


if __name__ == "__main__":
    print("Generating sample contracts...")
    generate_clean_contract()
    generate_messy_contract()
    generate_risky_contract()
    print("\nDone! Files in sample_contracts/")
    print("\nExpected routing:")
    print("  01_clean_contract.pdf  → AUTO_STORED (approved vendor, clean terms)")
    print("  02_messy_contract.pdf  → FLAGGED (Net-60, unknown vendor, missing SLA credits, bad IP clause)")
    print("  03_risky_contract.pdf  → FLAGGED (restricted vendor, many violations)")
