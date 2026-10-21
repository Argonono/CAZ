import os
import sys
import pytest

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db import get_all_sites, get_all_events
from mcp_browser_server import tool_simulate_user_journey

CARE_OPTIONS = [
    "🩺 Medical Care",
    "🦷 Dental Care",
    "👁️ Vision Care",
    "🧠 Behavioral Health"
]

CARE_MAPPING = {
    "🩺 Medical Care": "Medical",
    "🦷 Dental Care": "Dental",
    "👁️ Vision Care": "Vision",
    "🧠 Behavioral Health": "Behavioral Health"
}


def test_care_dropdown_options_integrity():
    """Verify that all 4 dropdown options exist and correctly map to recognized service types."""
    assert len(CARE_OPTIONS) == 4
    for opt in CARE_OPTIONS:
        assert opt in CARE_MAPPING
        service_target = CARE_MAPPING[opt]
        assert service_target in ["Medical", "Dental", "Vision", "Behavioral Health"]


@pytest.mark.parametrize("option_label,expected_service", [
    ("🩺 Medical Care", "Medical"),
    ("🦷 Dental Care", "Dental"),
    ("👁️ Vision Care", "Vision"),
    ("🧠 Behavioral Health", "Behavioral Health"),
])
def test_care_dropdown_options_yield_active_providers(option_label, expected_service):
    """Verify that choosing any dropdown option reliably finds matching safety net providers."""
    service = CARE_MAPPING[option_label]
    assert service == expected_service

    sites = get_all_sites()
    events = get_all_events(include_expired=False, current_date_str="2026-09-16")
    all_recs = sites + events

    matches = [
        r for r in all_recs
        if any(service.lower() in s.lower() for s in r.get("services", []))
    ]
    assert len(matches) > 0, f"Expected matching providers for service {service} from dropdown {option_label}"


@pytest.mark.parametrize("service_name", ["Medical", "Dental", "Vision", "Behavioral Health"])
def test_care_dropdown_journey_simulation(service_name):
    """Simulate end-to-end user navigation initiated from dropdown selection."""
    res = tool_simulate_user_journey(
        persona=f"User selecting {service_name} dropdown",
        service=service_name,
        location="27514",
        timing="This Week"
    )
    assert res["journey_success"] is True
    assert res["total_matches_found"] > 0
    top = res["top_ranked_match"]
    assert top is not None
    assert top["care_access_score"] >= 60
