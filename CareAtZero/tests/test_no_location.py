"""
When the user's location can't be detected, the app asks "Enter your ZIP code"
instead of quietly using a default ZIP (it is meant to work anywhere in the U.S.).
"""
import pytest

import utils.geo as geo
from test_mobile_ui import run_page


@pytest.fixture
def no_detected_location(monkeypatch):
    monkeypatch.setattr(geo, "detect_user_location", lambda *a, **k: {
        "zip": geo.DEFAULT_FALLBACK_ZIP, "city": "", "region": "", "country": "",
        "lat": None, "lon": None, "source": "fallback"})


def test_detection_failure_gives_no_zip(no_detected_location):
    assert geo.get_user_current_zip() == ""


def test_home_asks_for_zip(no_detected_location):
    at = run_page("home")
    assert any("Finding your location" in c.value for c in at.caption)  # browser check still running
    at = run_page("home", browser_location_checked=True)                # browser found nothing
    box = at.text_input(key="home_search_loc_input")
    assert box.value == "" and box.placeholder == "Enter your ZIP code"
    assert "search_loc" not in at.session_state
    assert any("Enter your ZIP code above" in i.value for i in at.info)
    assert any("couldn't detect your location" in c.value for c in at.caption)


def test_home_search_without_zip_shows_error(no_detected_location):
    at = run_page("home")
    at.button(key="home_find_care_submit_btn").click().run()
    assert any("Enter your ZIP code" in e.value for e in at.error)
    assert "search_loc" not in at.session_state


def test_find_asks_for_zip(no_detected_location):
    at = run_page("find")
    assert any("Enter your ZIP code" in i.value for i in at.info)


def test_details_asks_for_zip(no_detected_location):
    at = run_page("details", selected_care_id="site_shac_01", selected_care_type="site")
    assert any("Enter your ZIP code" in i.value for i in at.info)


def test_geocoder_never_guesses_an_empty_location():
    with pytest.raises(ValueError):
        geo.geocode_location("")


def test_browser_gps_result_becomes_a_zip(monkeypatch):
    from live import zip_centroids
    monkeypatch.setattr(zip_centroids, "_cache", {"27601": (35.773, -78.634), "37203": (36.15, -86.79)})
    loc = geo.location_from_browser({"lat": 35.78, "lon": -78.64, "source": "browser_gps"})
    assert loc["zip"] == "27601" and loc["source"] == "browser_gps"
    loc = geo.location_from_browser({"zip": "37203", "city": "Nashville", "lat": 36.15, "lon": -86.79,
                                     "source": "browser_ip"})
    assert loc["zip"] == "37203" and loc["city"] == "Nashville"
    assert geo.location_from_browser({"source": "none"}) is None
    # a cloud data center is never accepted as the user's location
    assert geo.location_from_browser({"zip": "97058", "city": "The Dalles", "source": "browser_ip"}) is None


def test_locations_are_not_shared_between_users():
    """Inside a user's session, the server-wide cache must never be read or written."""
    import inspect
    src = inspect.getsource(geo.detect_user_location)
    assert "not _in_streamlit_session() and _CACHED_USER_LOCATION is not None" in src
