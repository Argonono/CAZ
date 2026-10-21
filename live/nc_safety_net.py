"""
NC DHHS Safety Net list (state) -> Free & charitable clinics, dental clinics, health departments.

Source: NC Department of Health and Human Services, Office of Rural Health
"Safety Net" sites list (public CSV). The state republishes this file from time
to time at a new address; if the download starts failing, find the current link on
  https://www.dph.ncdhhs.gov/programs/oral-health/services-individuals-and-families/safety-net-dental-clinics/safety-net-dental-clinic-locations
and update CSV_URL below.

Cost labels come only from the state's own facility category:
  "Free and Charitable Clinic"        -> Free (the category itself says free)
  health centers, health departments  -> Sliding Scale (required to offer one)
  everything else                     -> Unknown (ask the clinic)
Hospitals and school-based centers are left out: hospitals aren't free/low-cost
clinics, and school-based centers generally serve only their students.
The file has no map coordinates, so each site is placed at its ZIP code's center.
"""
import csv
import io
from typing import List

from live import zip_centroids
from live.common import clean_phone, fetched_at, http_get, stable_id
from live.records import make_site

CSV_URL = "https://files.nc.gov/dhhs/2024-10/SafetyNetList_2024_05_29.csv?VersionId=RZ.SzREUlMozjDHiVvZ..WFWoArNAWHu"
SOURCE_NAME = "NC DHHS Safety Net Sites list (NC Office of Rural Health)"
SOURCE_URL = ("https://www.dph.ncdhhs.gov/programs/oral-health/services-individuals-and-families/"
              "safety-net-dental-clinics/safety-net-dental-clinic-locations")

FREE_TYPES = {"Free and Charitable Clinic", "Free and Charitable Clinic (mobile)"}
SLIDING_TYPES = {
    "Federally Qualified Health Center",
    "Federally Qualified Health Center/Health Department",
    "Health Department",
    "ORH Supported Rural Health Center",
    "Dental Clinic (stand alone)",
    "Dental Clinic (mobile)",
}
SKIP_TYPES = {"Critical Access Hospital", "Small Rural Hospital"}


def services_for(facility_type: str, name: str) -> List[str]:
    text = f"{facility_type} {name}".lower()
    if "dental" in text:
        return ["Dental"]
    if "behavioral" in text or "mental health" in text:
        return ["Behavioral Health"]
    return ["Medical"]


def cost_class_for(facility_type: str) -> str:
    if facility_type in FREE_TYPES:
        return "Free"
    if facility_type in SLIDING_TYPES:
        return "Sliding Scale"
    return "Unknown"


def fetch_raw() -> str:
    resp = http_get(CSV_URL)
    # The state's file is UTF-8 with a byte-order mark; decode it explicitly, since
    # the server doesn't say which encoding it uses.
    return resp.content.decode("utf-8-sig", errors="replace")


def parse(csv_text: str, checked: str) -> List[dict]:
    sites = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        row = {(k or "").replace("\ufeff", "").replace("ï»¿", "").strip(): (v or "").strip()
               for k, v in row.items()}
        name = row.get("Site Name", "")
        facility_type = row.get("Facility Type", "")
        zip5 = row.get("Zip_Code", "")[:5]
        if not name or not zip5 or facility_type in SKIP_TYPES or facility_type.startswith("School Based"):
            continue
        coords = zip_centroids.coords_for_zip(zip5)
        if coords is None:
            continue  # can't place it on the map, so leave it out rather than guess
        cost = cost_class_for(facility_type)
        if cost == "Free":
            eligibility = "Free care for uninsured patients who qualify; call to confirm eligibility"
            docs = ["Call to confirm (some free clinics ask for proof of income or residence)"]
        elif cost == "Sliding Scale":
            eligibility = "Sliding fee scale based on household income"
            docs = ["Photo ID (if available)", "Proof of income for the sliding fee discount"]
        else:
            eligibility = "Ask the clinic about cost and financial assistance before your visit"
            docs = ["Call to confirm what to bring"]
        street = ", ".join(p for p in (row.get("Street_Address", ""), row.get("Street_Address_2", "")) if p)
        is_mobile = "mobile" in facility_type.lower()
        sites.append(make_site(
            id=stable_id("ncdhhs", name, street, zip5),
            name=name,
            site_type="free_clinic" if cost == "Free" else ("mobile" if is_mobile else (facility_type or "clinic")),
            address=street,
            city=row.get("City", "").title(),
            state=row.get("State", "NC") or "NC",
            zip_code=zip5,
            latitude=coords[0],
            longitude=coords[1],
            phone=clean_phone(row.get("phone_number1", "")),
            website="",
            services=services_for(facility_type, name),
            cost_class=cost,
            eligibility=eligibility,
            appointment_rule="Appointment required (contact the clinic to schedule)",
            documents_required=docs,
            source_name=SOURCE_NAME,
            source_url=SOURCE_URL,
            last_checked=checked,
            notes=f"State category: {facility_type}." if facility_type else "",
        ))
    return sites


def fetch() -> List[dict]:
    return parse(fetch_raw(), fetched_at())
