"""The app uses the real current date (or a pinned one for tests and demos)."""
import datetime
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils import dates
from database.db import get_all_events
from scoring.care_access_score import calculate_care_access_score


def test_pinned_date_is_used_when_set(monkeypatch):
    monkeypatch.setenv("CAREATZERO_TODAY", "2026-09-16")
    assert dates.today_str() == "2026-09-16"


def test_real_date_is_used_when_not_pinned(monkeypatch):
    monkeypatch.delenv("CAREATZERO_TODAY", raising=False)
    real = dates.today()
    assert abs((real - datetime.date.today()).days) <= 1, "Should be today's date (NC time)"


def test_bad_pinned_date_falls_back_to_real_date(monkeypatch):
    monkeypatch.setenv("CAREATZERO_TODAY", "not-a-date")
    assert abs((dates.today() - datetime.date.today()).days) <= 1


def test_past_events_are_hidden(monkeypatch):
    """An event that has ended must never show as upcoming."""
    monkeypatch.setenv("CAREATZERO_TODAY", "2026-09-16")
    upcoming_sep16 = get_all_events(include_expired=False, current_date_str=dates.today_str())
    monkeypatch.setenv("CAREATZERO_TODAY", "2026-12-31")
    upcoming_dec31 = get_all_events(include_expired=False, current_date_str=dates.today_str())
    assert len(upcoming_sep16) > 0
    assert all(e["date_end"] >= "2026-12-31" for e in upcoming_dec31)
    assert len(upcoming_dec31) < len(upcoming_sep16)


def test_event_countdown_uses_today(monkeypatch):
    event = {"record_type": "event", "date_start": "2026-09-19", "services": ["Dental"], "cost_class": "Free"}
    monkeypatch.setenv("CAREATZERO_TODAY", "2026-09-16")
    _, _, reasons = calculate_care_access_score(event, "Dental", 3.0)
    assert any("in 3 days" in r for r in reasons)
    monkeypatch.setenv("CAREATZERO_TODAY", "2026-09-19")
    _, _, reasons = calculate_care_access_score(event, "Dental", 3.0)
    assert any("TODAY" in r for r in reasons)


def test_checked_date_display():
    assert dates.format_checked_date("2026-09-05") == "Sep 5, 2026"
    assert dates.format_checked_date("") == "date not listed"


def test_live_fetch_time_shown_in_eastern_time():
    # 01:36 UTC on Oct 10 is 9:36 PM on Oct 9 in North Carolina (EDT)
    assert dates.checked_parts("2026-10-10T01:36:30+00:00") == ("Oct 9, 2026", "9:36 PM EDT")
    assert dates.format_checked("2026-10-10T01:36:30+00:00") == "Oct 9, 2026 at 9:36 PM EDT"
    assert dates.format_checked_date("2026-10-10T01:36:30+00:00") == "Oct 9, 2026"
    # winter: standard time
    assert dates.checked_parts("2026-12-01T17:05:00+00:00") == ("Dec 1, 2026", "12:05 PM EST")
    # hand-verified records have only a date
    assert dates.checked_parts("2026-09-16") == ("Sep 16, 2026", None)
    assert dates.format_checked("2026-09-16") == "Sep 16, 2026"


def test_times_follow_the_search_area_time_zone():
    fetched = "2026-10-10T01:36:30+00:00"
    assert dates.checked_parts(fetched, "America/Chicago") == ("Oct 9, 2026", "8:36 PM CDT")
    assert dates.checked_parts(fetched, "America/Phoenix") == ("Oct 9, 2026", "6:36 PM MST")
    assert dates.checked_parts(fetched, "America/Los_Angeles") == ("Oct 9, 2026", "6:36 PM PDT")
    assert dates.checked_parts(fetched, "Pacific/Honolulu") == ("Oct 9, 2026", "3:36 PM HST")
    assert dates.timezone_label("America/Chicago") == "Central Time"


def test_time_zone_found_from_map_position():
    from utils.timezones import timezone_for
    assert timezone_for(35.77, -78.63) == "America/New_York"     # Raleigh, NC
    assert timezone_for(36.16, -86.78) == "America/Chicago"      # Nashville, TN
    assert timezone_for(33.45, -112.07) == "America/Phoenix"     # Phoenix, AZ
    assert timezone_for(None, None) is None
