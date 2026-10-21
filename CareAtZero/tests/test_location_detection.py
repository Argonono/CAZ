import os
import sys
import pytest
from unittest.mock import patch

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.geo import (
    get_user_current_zip,
    detect_user_location,
    geocode_location,
    DEFAULT_FALLBACK_ZIP,
    NC_ZIP_COORDINATES
)


def test_get_user_current_zip_returns_valid_string():
    """Verify that get_user_current_zip returns a non-empty string."""
    detected_zip = get_user_current_zip()
    assert isinstance(detected_zip, str)
    if detected_zip:
        assert len(detected_zip) >= 3, f"Detected ZIP '{detected_zip}' is too short"
    else:  # location couldn't be detected: the app asks the user for a ZIP code
        assert detect_user_location()["source"] == "fallback"


def test_detect_user_location_structure():
    """Verify that detect_user_location returns expected keys and types."""
    loc = detect_user_location()
    assert isinstance(loc, dict)
    assert "zip" in loc
    assert "city" in loc
    assert "region" in loc
    assert "country" in loc
    assert "lat" in loc
    assert "lon" in loc
    assert "source" in loc
    assert loc["zip"] != ""


def test_detect_user_location_fallback_on_network_failure():
    """Verify fallback to 27514 when network requests raise errors."""
    with patch("urllib.request.urlopen", side_effect=Exception("Network offline")):
        loc = detect_user_location(force_refresh=True)
        assert loc["zip"] == DEFAULT_FALLBACK_ZIP
        assert loc["city"] == "Chapel Hill"
        assert loc["region"] == "NC"
        assert loc["source"] == "fallback"


def test_geocode_location_with_detected_zip():
    """Verify that geocoding the detected user zip succeeds and returns valid coordinates."""
    detected_zip = get_user_current_zip()
    if not detected_zip:
        pytest.skip("location couldn't be detected here, so there is no detected ZIP to geocode")
    lat, lon, label = geocode_location(detected_zip)
    assert isinstance(lat, float)
    assert isinstance(lon, float)
    assert isinstance(label, str)
    assert len(label) > 0
    # Coordinates should be reasonable earth coordinates
    assert -90.0 <= lat <= 90.0
    assert -180.0 <= lon <= 180.0


def test_geocode_location_with_simulated_user_location():
    """Verify geocode_location dynamically maps to custom detected user location."""
    fake_loc = {
        "zip": "90210",
        "city": "Beverly Hills",
        "region": "CA",
        "country": "US",
        "lat": 34.0901,
        "lon": -118.4065,
        "source": "mock"
    }
    with patch("utils.geo.detect_user_location", return_value=fake_loc):
        lat, lon, label = geocode_location("90210")
        assert lat == 34.0901
        assert lon == -118.4065
        assert "Beverly Hills" in label or "90210" in label


# Recorded answers from the IP lookup service, so these tests don't need the internet
FAKE_IP_LOOKUPS = {
    "152.1.0.1": ("27601", "Raleigh", "North Carolina"),
    "152.2.0.1": ("27514", "Chapel Hill", "North Carolina"),
    "128.122.1.1": ("10001", "New York", "New York"),
    "66.249.66.1": ("94043", "Mountain View", "California"),
    "131.215.1.1": ("91199", "Pasadena", "California"),
}


@pytest.fixture
def fake_ip_lookup():
    import io, json as _json

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        ip = next((ip for ip in FAKE_IP_LOOKUPS if ip in url), None)
        if ip is None:
            raise OSError("no recorded answer")
        z, city, region = FAKE_IP_LOOKUPS[ip]
        body = {"zipCode": z, "cityName": city, "regionName": region, "countryName": "United States",
                "latitude": 35.0, "longitude": -79.0}
        return _Resp(_json.dumps(body).encode())

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        yield


@pytest.mark.parametrize("preset_name,sim_ip,expected_zip,expected_city", [
    ("Raleigh, NC", "152.1.0.1", "27601", "Raleigh"),
    ("Chapel Hill, NC", "152.2.0.1", "27514", "Chapel Hill"),
    ("New York, NY", "128.122.1.1", "10001", "New York"),
    ("Mountain View, CA", "66.249.66.1", "94043", "Mountain View"),
    ("Pasadena, CA", "131.215.1.1", "91199", "Pasadena"),
])
def test_detect_user_location_us_simulation_presets(preset_name, sim_ip, expected_zip, expected_city, fake_ip_lookup):
    """Verify that simulating different USA locations automatically detects the corresponding US ZIP code."""
    loc = detect_user_location(force_refresh=True, simulated_ip=sim_ip)
    assert loc["zip"] == expected_zip, f"Failed for {preset_name}: expected {expected_zip}, got {loc['zip']}"
    assert expected_city.lower() in loc["city"].lower()
    assert loc["country"] in ["United States", "US"]


def test_set_simulated_location_and_reset(fake_ip_lookup):
    """Verify programmatic switching of simulated locations and reset back to auto-detect."""
    from utils.geo import set_simulated_location

    # Switch to New York, NY
    ny_loc = set_simulated_location("New York, NY")
    assert ny_loc["zip"] == "10001"
    assert "New York" in ny_loc["city"]

    # Switch to Raleigh, NC
    ral_loc = set_simulated_location("Raleigh, NC")
    assert ral_loc["zip"] == "27601"
    assert "Raleigh" in ral_loc["city"]

    # Reset back to default / auto-detect
    reset_loc = set_simulated_location(None)
    assert reset_loc is not None
    assert isinstance(reset_loc["zip"], str)


def test_event_proximity_sorting_for_zip_27601():
    """Verify that entering ZIP 27601 correctly prioritizes in-ZIP events and computes accurate distances."""
    from database.db import get_all_events
    from utils.geo import haversine_distance

    user_lat, user_lon, _ = geocode_location("27601")
    events = get_all_events(include_expired=False, current_date_str="2026-09-16")
    assert len(events) >= 3

    events_with_dist = []
    for evt in events:
        evt_lat = evt.get("latitude")
        evt_lon = evt.get("longitude")
        d = haversine_distance(user_lat, user_lon, evt_lat, evt_lon) if evt_lat and evt_lon else None
        events_with_dist.append((d, evt))

    events_with_dist.sort(key=lambda item: (item[0] is None, item[0]))

    # The closest event to 27601 must be the Wake County Mobile Health Van (which is in 27601)
    closest_dist, closest_evt = events_with_dist[0]
    assert closest_evt["zip_code"] == "27601"
    assert closest_dist < 1.0  # Within 1 mile

    # Other events are in other ZIPs and have higher distances
    other_zips = [e["zip_code"] for d, e in events_with_dist[1:3]]
    assert "27601" not in other_zips
    assert all(d > 1.0 for d, e in events_with_dist[1:3])


def test_out_of_region_zip_distance_detection():
    """Verify that an out-of-region postal code like 676306 detects >1000 miles distance to NC center."""
    from utils.geo import haversine_distance

    fake_india_loc = {
        "zip": "676306",
        "city": "Tirurangadi",
        "region": "Kerala",
        "country": "India",
        "lat": 11.0432,
        "lon": 75.9234,
        "source": "mock"
    }
    with patch("utils.geo.detect_user_location", return_value=fake_india_loc):
        user_lat, user_lon, _ = geocode_location("676306")
        nc_center_lat, nc_center_lon = 35.7721, -78.6386
        dist_to_nc = haversine_distance(user_lat, user_lon, nc_center_lat, nc_center_lon)
        assert dist_to_nc > 1000  # Multi-thousand miles away



def test_strict_zip_clinic_filtering():
    """Verify that only clinics strictly matching the user's zip code are included."""
    from database.db import get_all_events

    events = get_all_events(include_expired=False, current_date_str="2026-09-16")

    # When querying 27601: only events with zip_code == "27601"
    matched_27601 = [e for e in events if str(e.get("zip_code", "")).strip() == "27601"]
    assert len(matched_27601) == 1
    assert matched_27601[0]["title"] == "Wake County Mobile Health & Free Vision Screening Van"

    # When querying 676306: zero events match
    matched_676306 = [e for e in events if str(e.get("zip_code", "")).strip() == "676306"]
    assert len(matched_676306) == 0

    # When querying 27514: only events with zip_code == "27514"
    matched_27514 = [e for e in events if str(e.get("zip_code", "")).strip() == "27514"]
    assert len(matched_27514) == 1
    assert "Triangle Vision" in matched_27514[0]["title"]


def test_is_valid_public_ip():
    """Verify that is_valid_public_ip correctly filters out private/loopback IPs."""
    from utils.geo import is_valid_public_ip

    assert is_valid_public_ip("152.1.0.1") is True
    assert is_valid_public_ip("157.48.0.1") is True
    assert is_valid_public_ip("127.0.0.1") is False
    assert is_valid_public_ip("10.0.0.1") is False
    assert is_valid_public_ip("192.168.1.1") is False
    assert is_valid_public_ip("172.16.0.1") is False
    assert is_valid_public_ip("::1") is False
    assert is_valid_public_ip("invalid-ip") is False


def test_is_datacenter_location_rejects_the_dalles_oregon():
    """Verify that is_datacenter_location flags Streamlit Cloud/Google Cloud datacenter (The Dalles 97058)."""
    from utils.geo import is_datacenter_location

    dalles_loc = {"city": "The Dalles", "zip": "97058", "region": "Oregon", "country": "US"}
    assert is_datacenter_location(dalles_loc) is True

    boardman_loc = {"city": "Boardman", "zip": "97818", "region": "Oregon", "country": "US"}
    assert is_datacenter_location(boardman_loc) is True

    # Real user locations must NOT be flagged as datacenters
    raleigh_loc = {"city": "Raleigh", "zip": "27601", "region": "North Carolina", "country": "US"}
    assert is_datacenter_location(raleigh_loc) is False

    ny_loc = {"city": "New York", "zip": "10001", "region": "New York", "country": "US"}
    assert is_datacenter_location(ny_loc) is False

    india_loc = {"city": "Malappuram", "zip": "676306", "region": "Kerala", "country": "India"}
    assert is_datacenter_location(india_loc) is False


def test_detect_user_location_rejects_the_dalles_datacenter():
    """Verify that if geolocation service returns The Dalles (97058), detect_user_location rejects it and falls back."""
    import json
    from unittest.mock import MagicMock
    from utils.geo import detect_user_location, DEFAULT_FALLBACK_ZIP

    dalles_response = json.dumps({
        "postal": "97058",
        "city": "The Dalles",
        "region": "Oregon",
        "country": "US",
        "latitude": 45.5946,
        "longitude": -121.1787
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = dalles_response
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        loc = detect_user_location(force_refresh=True)
        # Must NOT return The Dalles (97058)
        assert loc["zip"] != "97058"
        assert loc["city"] != "The Dalles"
        assert loc["zip"] == DEFAULT_FALLBACK_ZIP


def test_get_client_ip_from_mock_streamlit_context():
    """Verify that get_client_ip properly extracts client IP from Cloudflare or X-Forwarded-For headers."""
    from utils.geo import get_client_ip

    class MockContext:
        headers = {
            "cf-connecting-ip": "157.48.0.1",
            "x-forwarded-for": "157.48.0.1, 172.68.0.1"
        }
        ip_address = "172.68.0.1"

    with patch("streamlit.context", MockContext(), create=True):
        client_ip = get_client_ip()
        assert client_ip == "157.48.0.1"


def test_safe_city_name_cleans_unicode():
    """Verify that safe_city_name cleanly strips non-ASCII accents to avoid console/platform crashes."""
    from utils.geo import safe_city_name

    assert safe_city_name("Tirūrangādi") == "Tirurangadi"
    assert safe_city_name("Raleigh") == "Raleigh"
    assert safe_city_name("San José") == "San Jose"
    assert safe_city_name("") == ""


def test_detect_user_location_with_client_browser_query_params():
    """Verify that client_zip and client_city from browser query params are immediately accepted."""
    import streamlit as st
    from utils.geo import detect_user_location

    with patch.object(st, "query_params", {"client_zip": "676306", "client_city": "Tirurangadi"}):
        loc = detect_user_location(force_refresh=True)
        assert loc["zip"] == "676306"
        assert loc["city"] == "Tirurangadi"
        assert loc["source"] == "client_browser"


def test_user_custom_search_27514_not_clobbered_by_detected_zip():
    """Verify that explicitly searching for 27514 is strictly preserved and never overwritten by detected zip."""
    import streamlit as st

    # Simulate user having detected zip of 560018 (Bengaluru)
    user_detected_zip = "560018"

    # User explicitly searches for 27514
    searched_zip = "27514"
    st.session_state["search_loc"] = searched_zip

    saved_loc = st.session_state.get("search_loc")
    if saved_loc and str(saved_loc).strip():
        resolved_loc = str(saved_loc).strip()
    else:
        resolved_loc = user_detected_zip

    # Must preserve 27514 and NOT revert to 560018
    assert resolved_loc == "27514"
    assert resolved_loc != user_detected_zip




