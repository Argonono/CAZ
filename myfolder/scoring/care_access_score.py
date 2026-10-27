import datetime
from typing import Dict, Any, List, Optional, Tuple

from utils.dates import format_checked, today_str


def calculate_care_access_score(
    record: Dict[str, Any],
    service_needed: str,
    distance_miles: float,
    timing_pref: str = "Flexible",
    user_insurance: str = "Uninsured",  # kept for older callers; the app is for uninsured users
    user_income_band: str = "Under $25k",
    reference_date_str: Optional[str] = None
) -> Tuple[int, Dict[str, int], List[str]]:
    """
    Calculates transparent 100-point Care Access Score and provides
    a structured list of reasons ('Why this matches').

    Signals & Weights:
    - Cost Fit: 35%
    - Time to care / availability: 25%
    - Service match: 15%
    - Eligibility confidence: 10%
    - Distance / travel burden: 10%
    - Information freshness & completeness: 5%
    """
    breakdown = {}
    reasons = []

    # -------------------------------------------------------------
    # 1. Cost Fit (35 Points)
    # -------------------------------------------------------------
    cost_class = record.get("cost_class", "Sliding Scale")
    if cost_class == "Free":
        cost_pts = 35
        reasons.append("100% Free care - $0 out-of-pocket cost for uninsured patients.")
    elif cost_class == "Very Low Cost":
        cost_pts = 25
        reasons.append("Very low fixed nominal fee ($5-$25 maximum) or charitable copay.")
    elif cost_class == "Sliding Scale":
        cost_pts = 18
        if "Under" in user_income_band or "$0" in user_income_band:
            cost_pts = 20
            reasons.append("Sliding-fee discount applies based on income; fees can scale to $0-$15 for lowest income bands.")
        else:
            reasons.append("Sliding-fee schedule adjusted based on household size and income.")
    else:
        cost_pts = 8
        reasons.append("Cost tier pending provider verification.")
    breakdown["Cost Fit (35%)"] = cost_pts

    # -------------------------------------------------------------
    # 2. Time to Care / Upcoming Availability (25 Points)
    # -------------------------------------------------------------
    is_event = record.get("record_type") == "event"
    appt_rule = record.get("appointment_rule", "").lower()
    time_pts = 15

    if is_event:
        event_start = record.get("date_start", "")
        if event_start:
            try:
                ref_dt = datetime.date.fromisoformat(reference_date_str or today_str())
                evt_dt = datetime.date.fromisoformat(event_start)
                evt_end = datetime.date.fromisoformat(record.get("date_end") or event_start)
                days_until = (evt_dt - ref_dt).days

                if evt_dt <= ref_dt <= evt_end:  # first day or a later day of a multi-day event
                    time_pts = 25
                    reasons.append("Pop-up care event is happening TODAY.")
                elif 1 <= days_until <= 3:
                    time_pts = 24
                    reasons.append(f"Upcoming mobile clinic happening in {days_until} days ({record.get('date_start')}).")
                elif 4 <= days_until <= 7:
                    time_pts = 22
                    reasons.append(f"Pop-up event happening this week ({record.get('date_start')}).")
                elif 8 <= days_until <= 21:
                    time_pts = 19
                    reasons.append(f"Scheduled upcoming mobile event on {record.get('date_start')}.")
                else:
                    time_pts = 14
                    reasons.append(f"Future event on {record.get('date_start')}.")
            except Exception:
                time_pts = 18
                reasons.append(f"Event date: {record.get('date_start')}.")
    else:
        # Permanent clinic
        if "walk-in" in appt_rule or "walk in" in appt_rule:
            if timing_pref == "Today":
                time_pts = 24
                reasons.append("Walk-ins welcome today without prior appointment.")
            elif timing_pref == "This Week":
                time_pts = 22
                reasons.append("Walk-in hours available during weekly operational schedule.")
            else:
                time_pts = 20
                reasons.append("Walk-ins accepted during regular clinic hours.")
        elif "same-day" in appt_rule or "same day" in appt_rule:
            time_pts = 18
            reasons.append("Same-day appointments available.")
        else:
            time_pts = 15
            reasons.append("Regular clinic appointments scheduled on intake.")
    breakdown["Timing & Availability (25%)"] = time_pts

    # -------------------------------------------------------------
    # 3. Service Match (15 Points)
    # -------------------------------------------------------------
    services = record.get("services", [])
    service_lower = [s.lower() for s in services]
    target_lower = service_needed.lower()

    if target_lower in service_lower:
        service_pts = 15
        reasons.append(f"Direct match for requested {service_needed} services.")
    elif any(target_lower in s for s in service_lower):
        service_pts = 14
        reasons.append(f"Matches requested service category ({service_needed}).")
    elif "medical" in target_lower and ("primary care" in service_lower or "clinic" in service_lower):
        service_pts = 14
        reasons.append("Comprehensive general medical and preventive care available.")
    else:
        service_pts = 10
        reasons.append(f"Offers safety-net health services (includes {', '.join(services[:2])}).")
    breakdown["Service Match (15%)"] = service_pts

    # -------------------------------------------------------------
    # 4. Eligibility Confidence (10 Points)
    # -------------------------------------------------------------
    eligibility = record.get("eligibility", "").lower()
    docs = record.get("documents_required", [])
    elig_pts = 7

    if "no id required" in eligibility or "no proof of income" in eligibility or len(docs) == 0 or "none" in [d.lower() for d in docs]:
        elig_pts = 10
        reasons.append("High eligibility confidence: No strict ID or income documentation barriers.")
    elif "uninsured" in eligibility or "all welcome" in record.get("uninsured_acceptance", "").lower():
        elig_pts = 9
        reasons.append("Open to all uninsured individuals residing in service coverage area.")
    elif "sliding" in eligibility or "proof of income" in eligibility:
        elig_pts = 8
        reasons.append("Standard safety-net income verification required for sliding discount.")
    else:
        elig_pts = 7
        reasons.append("Eligibility guidelines provided; review document checklist before visiting.")
    breakdown["Eligibility Confidence (10%)"] = elig_pts

    # -------------------------------------------------------------
    # 5. Distance / Travel Burden (10 Points)
    # -------------------------------------------------------------
    if distance_miles < 5.0:
        dist_pts = 10
        reasons.append(f"Very close proximity ({distance_miles:.1f} mi) minimizing transit burden.")
    elif distance_miles <= 12.0:
        dist_pts = 8
        reasons.append(f"Convenient local distance ({distance_miles:.1f} mi).")
    elif distance_miles <= 25.0:
        dist_pts = 6
        reasons.append(f"Regional proximity ({distance_miles:.1f} mi).")
    elif distance_miles <= 50.0:
        dist_pts = 4
        reasons.append(f"Extended driving distance ({distance_miles:.1f} mi).")
    else:
        dist_pts = 2
        reasons.append(f"Outside immediate vicinity ({distance_miles:.1f} mi).")
    breakdown["Distance Fit (10%)"] = dist_pts

    # -------------------------------------------------------------
    # 6. Information Freshness & Completeness (5 Points)
    # -------------------------------------------------------------
    source_status = record.get("source_status", "active")
    last_checked = record.get("last_checked", "")
    freshness_pts = 4

    try:
        checked_day = datetime.date.fromisoformat(str(last_checked)[:10])
        ref_day = datetime.date.fromisoformat(reference_date_str or today_str())
        recent = (ref_day - checked_day).days <= 60
    except ValueError:
        recent = False
    if source_status == "active":
        if recent:
            freshness_pts = 5
            reasons.append(f"Source checked recently ({format_checked(last_checked)}) from an official provider directory.")
        else:
            freshness_pts = 4
    elif source_status == "stale":
        freshness_pts = 2
        reasons.append("Notice: Provider info has not been updated within 60 days.")
    else:
        freshness_pts = 1
        reasons.append("Notice: Live directory source temporarily unreachable; using cached record.")
    breakdown["Data Freshness (5%)"] = freshness_pts

    # Calculate final score
    total_score = sum(breakdown.values())
    total_score = max(0, min(100, total_score))

    return total_score, breakdown, reasons
