"""
SAMHSA FindTreatment.gov (federal) -> Mental health and substance use treatment.

Source: https://findtreatment.gov/locator/exportsAsJson/v2 (public, no key needed;
see the FindTreatment.gov developer guide). Searched in a radius around the user.

The feed has no single cost field. Cost is taken from what each facility reports
under "payment assistance": "Free" only if it reports free / no-charge care,
"Sliding Scale" only if it reports a sliding fee scale, otherwise "Unknown".
"""
from typing import List

from live.common import SourceUnavailable, clean_phone, fetched_at, http_get, stable_id
from live.records import make_site

QUERY_URL = "https://findtreatment.gov/locator/exportsAsJson/v2"
SOURCE_NAME = "SAMHSA FindTreatment.gov (U.S. Dept. of Health & Human Services)"
SOURCE_URL = "https://findtreatment.gov"
FACILITY_TYPES = {"MH": "Mental health treatment", "SA": "Substance use treatment",
                  "OTP": "Opioid treatment program"}


def _codes(services: list, group: str) -> str:
    return "; ".join(s.get("f3", "") for s in services if s.get("f2") == group and s.get("f3"))


def cost_class_from(services: list) -> str:
    assistance = _codes(services, "PYAS").lower()   # "Payment assistance available"
    accepted = _codes(services, "PAY").lower()      # "Payment / funding accepted"
    if "no charge" in assistance or "free care" in assistance or "free of charge" in assistance:
        return "Free"
    if "sliding" in assistance or "sliding" in accepted:
        return "Sliding Scale"
    return "Unknown"


def _query(s_addr: str, radius_miles: float, limit: int) -> List[dict]:
    params = {
        "sType": "both",                       # mental health and substance use
        "sAddr": f'"{s_addr}"',                # search center, in quotes as in the developer guide
        "limitType": 2,                        # search by distance
        "limitValue": int(radius_miles * 1609.34),  # meters
        "pageSize": limit,
        "page": 1,
        "sort": 0,                             # nearest first
    }
    try:
        return http_get(QUERY_URL, params=params).json().get("rows", []) or []
    except ValueError as e:
        raise SourceUnavailable(f"FindTreatment.gov returned unreadable data: {e}") from e


def fetch_raw(lat: float, lon: float, radius_miles: float = 60, limit: int = 200) -> List[dict]:
    """
    Facilities within radius_miles of (lat, lon), nearest first.
    The developer guide's text says longitude first but its example URLs put latitude
    first, so if one order finds nothing, the other is tried.
    """
    rows = _query(f"{lat},{lon}", radius_miles, limit)
    if not rows:
        rows = _query(f"{lon},{lat}", radius_miles, limit)
    return rows


def parse(rows: List[dict], checked: str) -> List[dict]:
    sites = []
    for row in rows:
        try:
            lat, lon = float(row.get("latitude")), float(row.get("longitude"))
        except (TypeError, ValueError):
            continue
        services = row.get("services") or []
        name = (row.get("name1") or "Treatment facility").strip()
        if row.get("name2"):
            name = f"{name} — {row['name2'].strip()}"
        street = ", ".join(p.strip() for p in (row.get("street1"), row.get("street2")) if p and p.strip())
        zip5 = str(row.get("zip") or "")[:5]
        ages = _codes(services, "AGE")
        payment = _codes(services, "PAY")
        eligibility_parts = []
        if ages:
            eligibility_parts.append(f"Ages served: {ages}")
        if payment:
            eligibility_parts.append(f"Payment accepted: {payment}")
        setting = _codes(services, "SET").lower()
        sites.append(make_site(
            id=stable_id("samhsa", name, street, zip5),
            name=name,
            site_type="behavioral_health",
            address=street,
            city=(row.get("city") or "").strip().title(),
            state=(row.get("state") or "").strip(),
            zip_code=zip5,
            latitude=lat,
            longitude=lon,
            phone=clean_phone(row.get("phone") or row.get("intake1") or ""),
            website=(row.get("website") or "").strip(),
            services=["Behavioral Health"],
            cost_class=cost_class_from(services),
            eligibility="; ".join(eligibility_parts) or "Contact the facility about eligibility",
            appointment_rule="Walk-in services offered" if "walk" in setting else "Contact the facility to schedule an intake",
            source_name=SOURCE_NAME,
            source_url=SOURCE_URL,
            last_checked=checked,
            notes=FACILITY_TYPES.get(row.get("type_facility", ""), ""),
        ))
    return sites


def fetch(lat: float, lon: float, radius_miles: float = 60) -> List[dict]:
    return parse(fetch_raw(lat, lon, radius_miles), fetched_at())
