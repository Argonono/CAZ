"""
Which time zone to show times in.

CareAtZero is meant to work anywhere in the U.S., so times follow the place being
searched: "today" (which pop-up clinics have already ended) and "last checked"
times are shown in that area's local time, e.g. Raleigh -> Eastern,
Nashville -> Central, Phoenix -> Arizona time (no daylight saving).

Order used:
  1. the time zone of the searched ZIP code / city (set by each screen after it
     finds the search location), found from its map position with the
     timezonefinder package, which works offline;
  2. otherwise the time zone of the user's own phone or computer (from the browser);
  3. otherwise Eastern Time, where the pilot area (North Carolina) is.

The choice is kept per user session, so two people searching different states
at the same time each see their own local time.
"""
from functools import lru_cache
from typing import Optional

DEFAULT_TIMEZONE = "America/New_York"
SESSION_KEY = "display_timezone"

FRIENDLY_NAMES = {
    "America/New_York": "Eastern Time", "America/Detroit": "Eastern Time",
    "America/Indiana/Indianapolis": "Eastern Time", "America/Kentucky/Louisville": "Eastern Time",
    "America/Chicago": "Central Time", "America/Indiana/Knox": "Central Time",
    "America/Menominee": "Central Time", "America/North_Dakota/Center": "Central Time",
    "America/Denver": "Mountain Time", "America/Boise": "Mountain Time",
    "America/Phoenix": "Arizona Time (no daylight saving)",
    "America/Los_Angeles": "Pacific Time",
    "America/Anchorage": "Alaska Time", "America/Juneau": "Alaska Time",
    "Pacific/Honolulu": "Hawaii Time",
    "America/Puerto_Rico": "Atlantic Time",
}


@lru_cache(maxsize=1)
def _finder():
    from timezonefinder import TimezoneFinder
    return TimezoneFinder()


@lru_cache(maxsize=4096)
def timezone_for(lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    """IANA time zone name (e.g. 'America/Chicago') for a map position, or None if unknown."""
    if lat is None or lon is None:
        return None
    try:
        return _finder().timezone_at(lat=float(lat), lng=float(lon))
    except Exception:  # package missing or position outside any zone (ocean)
        return None


def _session_state():
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return st.session_state if get_script_run_ctx() is not None else None
    except Exception:
        return None


def use_timezone_of(lat: Optional[float], lon: Optional[float]) -> None:
    """Called by each screen after it finds the search location."""
    tz = timezone_for(lat, lon)
    state = _session_state()
    if tz and state is not None:
        state[SESSION_KEY] = tz


def current_timezone_name() -> str:
    """The time zone to show times in for this user right now (see the order above)."""
    state = _session_state()
    if state is not None:
        if state.get(SESSION_KEY):
            return state[SESSION_KEY]
        try:
            import streamlit as st
            browser_tz = st.context.timezone
            if browser_tz:
                return browser_tz
        except Exception:
            pass
    return DEFAULT_TIMEZONE


def friendly_name(tz_name: str) -> str:
    """'America/Chicago' -> 'Central Time'; unlisted zones -> their city, e.g. 'Guam time'."""
    if tz_name in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[tz_name]
    return tz_name.split("/")[-1].replace("_", " ") + " time"
