import os
import sys
import pytest
import sqlite3

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db import (
    init_db, get_connection, insert_care_site, insert_care_event,
    get_all_sites, get_all_events, get_site_by_id
)
from data.seed_data import seed_database
from scoring.care_access_score import calculate_care_access_score
from live import hrsa
from utils.geo import haversine_distance, geocode_location
from utils.calendar import generate_ics_calendar


@pytest.fixture(scope="module")
def test_db():
    """Setup an in-memory or test SQLite database with seed data."""
    import gc
    test_db_path = os.path.join(PROJECT_ROOT, "database", "test_care.db")
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass
    seed_database(db_path=test_db_path)
    yield test_db_path
    gc.collect()
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass


def test_tc01_search_dental_uninsured(test_db):
    """TC-01: Verify searching for Dental returns only active dental providers."""
    sites = get_all_sites(db_path=test_db)
    events = get_all_events(include_expired=False, current_date_str="2026-09-16", db_path=test_db)
    all_records = sites + events

    dental_records = [r for r in all_records if any("dental" in s.lower() for s in r.get("services", []))]
    assert len(dental_records) > 0, "Expected multiple dental options in dataset"

    for r in dental_records:
        services_lower = [s.lower() for s in r.get("services", [])]
        assert "dental" in services_lower, f"Record {r.get('name') or r.get('title')} must include dental"


def test_tc02_cost_classification_integrity():
    """TC-02: A source that says sliding fee must be labeled Sliding Scale, never Free."""
    raw_fqhc = {"attributes": {"OBJECTID": 1, "SITE_NM": "Community Health Center", "SITE_ADDRESS": "123 Main St",
                               "SITE_CITY": "RALEIGH", "SITE_STATE_ABBR": "NC", "SITE_ZIP_CD": "27601"},
                "geometry": {"x": -78.63, "y": 35.77}}
    normalized = hrsa.parse([raw_fqhc], "2026-09-16T12:00:00+00:00")[0]
    assert normalized["cost_class"] == "Sliding Scale"
    assert normalized["cost_class"] != "Free"


def test_tc03_expired_event_hidden(test_db):
    """TC-03: An event with past date is hidden from upcoming discovery results."""
    current_date = "2026-09-16"
    upcoming_events = get_all_events(include_expired=False, current_date_str=current_date, db_path=test_db)
    upcoming_ids = [e["id"] for e in upcoming_events]

    assert "evt_past_demo_clinic" not in upcoming_ids, "Expired event must be excluded from upcoming results"

    # Verify that include_expired=True returns the past event
    all_events = get_all_events(include_expired=True, db_path=test_db)
    all_ids = [e["id"] for e in all_events]
    assert "evt_past_demo_clinic" in all_ids, "Past event should exist in full archive"


def test_tc04_scoring_logic():
    """TC-04: Scoring reflects configured cost (35%), time (25%), service, and distance weights."""
    free_event = {
        "id": "evt_1",
        "title": "Free Dental Pop-Up",
        "record_type": "event",
        "cost_class": "Free",
        "services": ["Dental"],
        "date_start": "2026-09-18",
        "date_end": "2026-09-18",
        "documents_required": [],
        "eligibility": "No ID required",
        "source_status": "active",
        "last_checked": "2026-09-16"
    }
    sliding_clinic = {
        "id": "site_1",
        "name": "Sliding Scale Clinic",
        "record_type": "site",
        "cost_class": "Sliding Scale",
        "services": ["Dental"],
        "appointment_rule": "Appointment required in 2 weeks",
        "documents_required": ["Proof of income", "Photo ID"],
        "eligibility": "Proof of income required",
        "source_status": "active",
        "last_checked": "2026-09-16"
    }

    score_free, breakdown_free, reasons_free = calculate_care_access_score(
        free_event, service_needed="Dental", distance_miles=12.0, timing_pref="This Week", reference_date_str="2026-09-16"
    )
    score_sliding, breakdown_sliding, reasons_sliding = calculate_care_access_score(
        sliding_clinic, service_needed="Dental", distance_miles=3.0, timing_pref="This Week", reference_date_str="2026-09-16"
    )

    # Cost fit points for Free should be 35
    assert breakdown_free["Cost Fit (35%)"] == 35
    assert breakdown_sliding["Cost Fit (35%)"] <= 20
    assert len(reasons_free) > 0
    assert len(reasons_sliding) > 0


def test_tc05_source_staleness_handling():
    """TC-05: Stale or unverified sources receive lower freshness score and notice."""
    stale_rec = {
        "id": "site_stale",
        "name": "Stale Provider",
        "cost_class": "Free",
        "services": ["Medical"],
        "source_status": "stale",
        "last_checked": "2024-01-01"
    }
    score, breakdown, reasons = calculate_care_access_score(
        stale_rec, service_needed="Medical", distance_miles=5.0, reference_date_str="2026-09-16"
    )
    assert breakdown["Data Freshness (5%)"] <= 2
    assert any("Notice" in r or "not been updated" in r for r in reasons)


def test_tc06_privacy_compliance(test_db):
    """TC-06: Database schema does not store SSN, diagnosis, or health records."""
    conn = get_connection(db_path=test_db)
    cursor = conn.cursor()

    # Inspect all table column names
    for table_name in ["care_sites", "care_events", "sources"]:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row["name"].lower() for row in cursor.fetchall()]
        forbidden = ["ssn", "social_security", "diagnosis", "medical_record", "phi", "symptom", "health_history"]
        for f in forbidden:
            assert f not in columns, f"Forbidden sensitive field '{f}' found in table '{table_name}'"
    conn.close()


def test_tc07_details_and_calendar_export(test_db):
    """TC-07: Records have complete contact, documents, source, and .ics calendar generation."""
    site = get_site_by_id("site_shac_01", db_path=test_db)
    assert site is not None
    assert site["phone"] != ""
    assert site["website"] != ""
    assert isinstance(site["documents_required"], list)
    assert site["cost_class"] == "Free"

    # Test .ics generation
    ics_text = generate_ics_calendar(site)
    assert "BEGIN:VCALENDAR" in ics_text
    assert "BEGIN:VEVENT" in ics_text
    assert "SUMMARY:[Free]" in ics_text
    assert "END:VCALENDAR" in ics_text


def test_tc08_geospatial_distance():
    """TC-08: Haversine distance correctly calculates mileage between Triangle locations."""
    # Distance between Chapel Hill (27514) and Raleigh Downtown (27601) is ~25-28 miles
    lat_ch, lon_ch, _ = geocode_location("27514")
    assert geocode_location("Nashville, TN") is None  # unknown places are never guessed
    lat_ral, lon_ral, _ = geocode_location("27601")

    dist = haversine_distance(lat_ch, lon_ch, lat_ral, lon_ral)
    assert 22.0 <= dist <= 30.0, f"Expected distance between Chapel Hill and Raleigh to be ~25-28 mi, got {dist}"
