"""
HRSA health centers (federal) -> Medical care, sliding scale.

Source: HRSA "Health Care Service Delivery Sites" map service (public, no key needed)
  https://gisportal.hrsa.gov/server/rest/services/HealthCareFacilities/PrimaryHealthCareFacilities_FS/MapServer/0

HRSA-funded health centers must offer a sliding fee scale and serve everyone
regardless of insurance or ability to pay, so they are labeled "Sliding Scale"
(never "Free"). The feed lists sites, not services, so the type of care comes
from the site's name ("... Dental Center" -> Dental, "... Behavioral Health" ->
Mental health), and Medical otherwise.
"""
from typing import List

from live.common import SourceUnavailable, clean_phone, fetched_at, http_get, stable_id
from live.nc_safety_net import services_for
from live.records import make_site

QUERY_URL = ("https://gisportal.hrsa.gov/server/rest/services/HealthCareFacilities/"
             "PrimaryHealthCareFacilities_FS/MapServer/0/query")
FIELDS = ["OBJECTID", "SITE_NM", "SITE_ADDRESS", "SITE_CITY", "SITE_STATE_ABBR", "SITE_ZIP_CD",
          "SITE_PHONE_NUM", "SITE_URL", "HCC_STATUS_DESC", "HCC_LOC_DESC", "HCC_LOC_SETTING_DESC",
          "HCC_TYP_DESC", "GRANTEE_NM"]
SOURCE_NAME = "HRSA Health Center Program (U.S. Dept. of Health & Human Services)"
SOURCE_URL = "https://findahealthcenter.hrsa.gov"
PAGE_SIZE = 1000
MAX_PAGES = 10


def fetch_raw(state: str = "NC") -> List[dict]:
    """All active HRSA sites in one state, as raw map-service features (several pages if needed)."""
    features: List[dict] = []
    for page in range(MAX_PAGES):
        params = {
            "where": f"SITE_STATE_ABBR='{state}' AND HCC_STATUS_DESC='Active'",
            "outFields": ",".join(FIELDS),
            "returnGeometry": "true",
            "outSR": "4326",  # plain latitude/longitude
            "f": "json",
            "resultOffset": page * PAGE_SIZE,
            "resultRecordCount": PAGE_SIZE,
        }
        try:
            data = http_get(QUERY_URL, params=params).json()
        except ValueError as e:
            raise SourceUnavailable(f"HRSA returned unreadable data: {e}") from e
        if "error" in data:
            raise SourceUnavailable(f"HRSA error: {data['error']}")
        batch = data.get("features", [])
        features.extend(batch)
        if not data.get("exceededTransferLimit") or not batch:
            break
    return features


def parse(features: List[dict], checked: str) -> List[dict]:
    sites = []
    for feature in features:
        a = feature.get("attributes", {}) or {}
        g = feature.get("geometry", {}) or {}
        lat, lon = g.get("y"), g.get("x")
        if lat is None or lon is None:
            continue
        setting = (a.get("HCC_LOC_SETTING_DESC") or "").strip()
        if "school" in setting.lower():
            continue  # school-based sites generally serve only enrolled students
        loc_desc = (a.get("HCC_LOC_DESC") or "").lower()
        site_type = "mobile" if "mobile" in loc_desc else "fqhc"
        name = (a.get("SITE_NM") or "").strip() or "HRSA Health Center"
        zip5 = str(a.get("SITE_ZIP_CD") or "")[:5]
        grantee = (a.get("GRANTEE_NM") or "").strip()
        sites.append(make_site(
            id=stable_id("hrsa", str(a.get("OBJECTID")), name, zip5),
            name=name,
            site_type=site_type,
            address=(a.get("SITE_ADDRESS") or "").strip(),
            city=(a.get("SITE_CITY") or "").strip().title(),
            state=(a.get("SITE_STATE_ABBR") or "").strip(),
            zip_code=zip5,
            latitude=float(lat),
            longitude=float(lon),
            phone=clean_phone(a.get("SITE_PHONE_NUM") or ""),
            website=(a.get("SITE_URL") or "").strip(),
            services=services_for("", name),
            cost_class="Sliding Scale",
            eligibility=("Federally required sliding fee scale based on income; "
                         "care provided regardless of insurance status or ability to pay"),
            appointment_rule="Appointment required (contact the clinic to schedule)",
            documents_required=["Photo ID (if available)", "Proof of income for the sliding fee discount"],
            source_name=SOURCE_NAME,
            source_url=SOURCE_URL,
            last_checked=checked,
            uninsured_acceptance="All welcome, regardless of ability to pay",
            notes=f"Operated by {grantee}." if grantee else "",
        ))
    return sites


def fetch(state: str = "NC") -> List[dict]:
    return parse(fetch_raw(state), fetched_at())
