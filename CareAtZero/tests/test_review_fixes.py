"""
Tests for the bugs found in the October 2026 code review, so they can't come back.
"""
import datetime

from live import sources
from scoring.care_access_score import calculate_care_access_score
from utils.calendar import generate_ics_calendar
from utils.geo import geocode_location
from test_mobile_ui import run_page


def test_unknown_places_are_not_guessed():
    assert geocode_location("Nashville, TN") is None
    assert geocode_location("00000") is None
    assert geocode_location("27514-1234")[2].startswith("Chapel Hill")  # ZIP+4 works


def test_event_already_underway_counts_as_today():
    event = {"record_type": "event", "date_start": "2027-03-13", "date_end": "2027-03-14",
             "services": ["Dental"], "cost_class": "Free"}
    _, breakdown, reasons = calculate_care_access_score(event, "Dental", 5, reference_date_str="2027-03-14")
    assert breakdown["Timing & Availability (25%)"] == 25
    assert "TODAY" in " ".join(reasons)


def test_freshness_uses_real_dates_not_the_year():
    rec = {"services": ["Medical"], "source_status": "active", "last_checked": "2027-01-20T10:00:00+00:00"}
    _, breakdown, _ = calculate_care_access_score(rec, "Medical", 5, reference_date_str="2027-02-01")
    assert breakdown["Data Freshness (5%)"] == 5          # 12 days old: recent, even in 2027
    _, breakdown, _ = calculate_care_access_score(rec, "Medical", 5, reference_date_str="2027-06-01")
    assert breakdown["Data Freshness (5%)"] == 4          # over 60 days old


def test_call_to_schedule_is_not_called_same_day():
    rec = {"services": ["Medical"], "appointment_rule": "Call to schedule an appointment"}
    _, _, reasons = calculate_care_access_score(rec, "Medical", 5, reference_date_str="2026-10-09")
    assert not any("Same-day" in r for r in reasons)


def test_duplicate_clinics_are_merged_not_dropped():
    hrsa_rec = {"name": "Stokes Dental Center", "zip_code": "27016", "services": ["Medical"],
                "cost_class": "Sliding Scale", "source_name": "HRSA"}
    state_rec = {"name": "STOKES DENTAL CENTER", "zip_code": "27016", "services": ["Dental"],
                 "cost_class": "Free", "eligibility": "Free", "documents_required": [], "source_name": "NC DHHS"}
    kept = dict(hrsa_rec)
    sources._merge_into(kept, state_rec)
    assert kept["services"] == ["Medical", "Dental"] and kept["cost_class"] == "Free"


def test_calendar_file_is_valid_and_escaped():
    ics = generate_ics_calendar({"id": "x", "name": "Clinic; Inc, Main", "address": "1 Main St",
                                 "city": "Raleigh", "state": "NC", "zip_code": "27601",
                                 "cost_class": "Free", "date_start": "2027-04-24", "date_end": "2027-04-25"})
    assert "\r\n" in ics and r"SUMMARY:[Free] Clinic\; Inc\, Main" in ics
    assert "DTSTART;VALUE=DATE:20270424" in ics and "DTEND;VALUE=DATE:20270426" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))


def test_feed_text_is_shown_as_text_not_page_code(monkeypatch):
    bad = {"id": "evil", "record_type": "site", "name": "<img src=x onerror=alert(1)>Clinic",
           "address": "1 Main", "city": "Raleigh", "state": "NC", "zip_code": "27601",
           "latitude": 35.77, "longitude": -78.63, "services": ["Medical"], "cost_class": "Free",
           "source_name": "Test", "last_checked": "2026-10-09"}
    monkeypatch.setattr(sources, "load_live_data", lambda *a, **k: sources.LiveData(sites=[bad]))
    at = run_page("find", search_loc="27601", selected_service="Medical")
    html = " ".join(m.value for m in at.markdown)
    assert "&lt;img src=x onerror=alert(1)&gt;Clinic" in html and "<img src=x" not in html


def test_when_do_you_need_care_filters_events(monkeypatch):
    soon = {"id": "soon", "record_type": "event", "title": "Soon Clinic", "services": ["Dental"],
            "cost_class": "Free", "latitude": 35.77, "longitude": -78.63, "date_start": "2026-09-17",
            "date_end": "2026-09-17", "source_name": "Test", "last_checked": "2026-09-16"}
    later = dict(soon, id="later", title="Later Clinic", date_start="2027-04-24", date_end="2027-04-25")
    monkeypatch.setattr(sources, "load_live_data", lambda *a, **k: sources.LiveData(events=[soon, later]))
    text = lambda at: " ".join(m.value for m in at.markdown)
    at = run_page("find", search_loc="27601", selected_service="Dental", search_timing="This Week")
    assert "Soon Clinic" in text(at) and "Later Clinic" not in text(at)
    at = run_page("find", search_loc="27601", selected_service="Dental", search_timing="Flexible (Upcoming)")
    assert "Later Clinic" in text(at)


def test_about_page_has_no_wide_tables_and_no_math_dollars():
    at = run_page("about", search_loc="27601")
    text = " ".join(m.value for m in at.markdown)
    assert "| Match Signal |" not in text and "| Source | Provides |" not in text  # cards, not tables
    assert "&#36;0" in text and "35 pts" in text
