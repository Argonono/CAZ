from typing import Any, Dict

from utils.dates import format_checked, today


def generate_shareable_referral_text(record: Dict[str, Any], score: int, reasons: list) -> str:
    """
    Generates a cleanly formatted text referral summary that counselors,
    social workers, or patients can copy, text, or print.
    """
    name = record.get("title") or record.get("name", "Care Provider")
    cost_class = record.get("cost_class", "Sliding Scale")
    phone = record.get("phone", "N/A")
    address = f"{record.get('address', '')}, {record.get('city', '')}, {record.get('state', '')} {record.get('zip_code', '')}".strip(" ,")
    website = record.get("source_url") or record.get("website", "N/A")
    services = ", ".join(record.get("services", []))
    hours = record.get("hours_summary") or record.get("time_details", "Contact clinic for hours")
    appt_rule = record.get("appointment_rule", "Call ahead")
    eligibility = record.get("eligibility", "Open to community")
    docs = ", ".join(record.get("documents_required", [])) if record.get("documents_required") else "None specified"
    last_checked = format_checked(record.get("last_checked")) if record.get("last_checked") else "Recently verified"

    reasons_fmt = "\n".join([f"  • {r}" for r in reasons[:3]])

    referral = f"""====================================================
CareAtZero - Safety-Net Healthcare Referral Summary
Generated: {today():%B} {today().day}, {today().year}
====================================================

PROVIDER / CLINIC:
{name}
Cost Classification: [{cost_class.upper()}]
Care Access Score: {score}/100

LOCATION & CONTACT:
Address: {address}
Phone: {phone}
Website / Source: {website}

SERVICES OFFERED:
{services}

SCHEDULE & ADMISSION:
Hours/Timing: {hours}
Intake Policy: {appt_rule}

ELIGIBILITY & WHAT TO BRING:
Eligibility: {eligibility}
Documents Needed: {docs}

WHY THIS OPTION MATCHES:
{reasons_fmt}

DATA FRESHNESS:
Source verified: {last_checked}

----------------------------------------------------
DISCLAIMER: CareAtZero is a public resource navigation tool and does not provide medical advice, diagnosis, or capacity guarantees. In case of life-threatening medical emergencies, please call 911 or visit the nearest emergency room. For mental health crisis support, dial 988.
===================================================="""
    return referral
