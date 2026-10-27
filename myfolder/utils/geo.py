import math
import re
import urllib.request
import json
import os
from typing import Tuple, Optional, Dict, Any

_CACHED_USER_LOCATION: Optional[Dict[str, Any]] = None
DEFAULT_FALLBACK_ZIP = "27514"

# Pre-configured US Location simulation IPs
US_SIMULATION_PRESETS: Dict[str, str] = {
    "Raleigh, NC": "152.1.0.1",
    "Chapel Hill, NC": "152.2.0.1",
    "New York, NY": "128.122.1.1",
    "Pasadena / Los Angeles, CA": "131.215.1.1",
    "Mountain View, CA": "66.249.66.1",
    "Pittsburgh, PA": "128.2.0.1",
}


def _in_streamlit_session() -> bool:
    """True while running a user's Streamlit session (each user has their own)."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


def safe_city_name(city: str) -> str:
    """Sanitizes city names to prevent unicode encoding errors on various platforms."""
    if not city:
        return ""
    import unicodedata
    normalized = unicodedata.normalize('NFKD', str(city))
    cleaned = normalized.encode('ascii', 'ignore').decode('ascii').strip()
    return cleaned or str(city)


def is_valid_public_ip(ip: str) -> bool:
    """Checks whether an IP address is a valid public, routable IP."""
    try:
        import ipaddress
        obj = ipaddress.ip_address(ip.strip())
        return not (obj.is_private or obj.is_loopback or obj.is_reserved or obj.is_link_local or obj.is_multicast)
    except Exception:
        return False


def get_client_ip() -> Optional[str]:
    """
    Extracts the user's real client IP from Streamlit context headers.
    Checks Cloudflare (cf-connecting-ip), X-Real-IP, X-Forwarded-For,
    and Streamlit's context.ip_address.
    """
    try:
        import streamlit as st
        if hasattr(st, "context"):
            headers = getattr(st.context, "headers", None)
            if headers:
                for h in ["cf-connecting-ip", "x-real-ip", "x-forwarded-for"]:
                    val = headers.get(h)
                    if val:
                        parts = [p.strip() for p in val.split(",") if p.strip()]
                        for candidate in parts:
                            if is_valid_public_ip(candidate):
                                return candidate

            st_ip = getattr(st.context, "ip_address", None)
            if st_ip and is_valid_public_ip(st_ip):
                return st_ip.strip()
    except Exception:
        pass
    return None


def is_cloud_environment() -> bool:
    """Detects if running on Streamlit Cloud, container, or cloud host."""
    if os.path.exists("/mount/src"):
        return True
    if os.getenv("STREAMLIT_SHARING_MODE") is not None:
        return True
    if os.getenv("STREAMLIT_SERVER_BASE_URL_PATH") is not None:
        return True
    return False


def is_datacenter_location(loc: Dict[str, Any]) -> bool:
    """Detects if the detected location belongs to a cloud hosting datacenter instead of a real user."""
    city = str(loc.get("city", "")).lower()
    zip_code = str(loc.get("zip", "")).strip()

    # Google Cloud Oregon datacenter (The Dalles, Wasco County, OR 97058)
    if zip_code == "97058" or "the dalles" in city:
        return True
    # AWS / GCP Boardman OR
    if zip_code == "97818" or "boardman" in city:
        return True
    # Ashburn / Sterling VA AWS datacenter clusters
    if zip_code in ("20147", "20166", "20149") and ("ashburn" in city or "sterling" in city):
        return True
    return False


BROWSER_SOURCES = ("browser_gps", "browser_ip", "client_browser")
_geo_component = None


def _browser_geo_component():
    global _geo_component
    if _geo_component is None:
        import streamlit.components.v1 as components
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "components", "geo_detector")
        _geo_component = components.declare_component("careatzero_geo", path=path)
    return _geo_component


def location_from_browser(found: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Turn what the browser detector sent back into a location dict, or None if it found nothing usable."""
    if not isinstance(found, dict) or found.get("source") not in ("browser_gps", "browser_ip"):
        return None
    lat, lon = found.get("lat"), found.get("lon")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None
    zip_code = str(found.get("zip") or "").strip()[:5]
    if not zip_code and lat is not None and lon is not None:
        try:  # GPS gives coordinates only: find the nearest ZIP code offline
            from live.zip_centroids import nearest_zip
            zip_code = nearest_zip(lat, lon) or ""
        except Exception:
            zip_code = ""
    if not (len(zip_code) == 5 and zip_code.isdigit()):
        return None
    city = safe_city_name(found.get("city") or "")
    if not city and zip_code in NC_ZIP_COORDINATES:  # GPS gives no city name; use the known area name
        city = NC_ZIP_COORDINATES[zip_code][2]
    loc = {"zip": zip_code, "city": city, "region": found.get("region") or "",
           "country": "US", "lat": lat, "lon": lon, "source": found["source"]}
    # A cloud data center can only be a mistake for internet-address lookups, never for GPS
    if found["source"] == "browser_ip" and is_datacenter_location(loc):
        return None
    return loc


def inject_client_geo_detector():
    """
    Finds the user's location in their own browser (GPS if allowed, otherwise their
    internet connection's location) and returns it to THIS session through a small
    Streamlit component (components/geo_detector). No page reloads.

    Runs once per session (again after "Use my location"). When the result arrives:
    - it is saved as this session's detected location (never shared with other users);
    - if the search box was filled automatically (not typed by the user), it is updated
      to the more accurate ZIP code and the screen refreshes.
    """
    try:
        import streamlit as st
        if not _in_streamlit_session():
            return
        state = st.session_state
        loc = state.get("detected_user_location")
        if (loc and loc.get("source") in BROWSER_SOURCES) or state.get("browser_location_checked"):
            return
        attempt = state.get("geo_attempt", 0)
        found = _browser_geo_component()(key=f"geo_detect_{attempt}", default=None)
        if found is None:
            return  # still detecting
        state["browser_location_checked"] = True
        browser_loc = location_from_browser(found)
        if not browser_loc:
            return
        state["detected_user_location"] = browser_loc
        if not state.get("search_loc") or state.get("search_loc_auto", True):
            if state.get("search_loc") != browser_loc["zip"]:
                state["search_loc"] = browser_loc["zip"]
                state["search_loc_auto"] = True
                state["home_search_loc_input"] = browser_loc["zip"]  # show the new ZIP in the box
                st.rerun()
    except Exception as e:
        if type(e).__name__ in ("RerunException", "StopException"):
            raise
        return

def set_simulated_location(ip_or_preset: Optional[str] = None, force_zip: Optional[str] = None) -> Dict[str, Any]:
    """
    Overrides the current user location with a simulated US location/IP.
    Clears cache and forces immediate refresh.
    """
    global _CACHED_USER_LOCATION
    _CACHED_USER_LOCATION = None

    sim_ip = US_SIMULATION_PRESETS.get(ip_or_preset, ip_or_preset) if ip_or_preset else None

    try:
        import streamlit as st
        if hasattr(st, "session_state"):
            if sim_ip:
                st.session_state["simulated_ip"] = sim_ip
            else:
                st.session_state.pop("simulated_ip", None)

            if force_zip:
                st.session_state["simulated_zip"] = force_zip
            else:
                st.session_state.pop("simulated_zip", None)

            st.session_state.pop("detected_user_location", None)
            st.session_state.pop("search_loc", None)
    except Exception:
        pass

    return detect_user_location(force_refresh=True, simulated_ip=sim_ip)


def detect_user_location(force_refresh: bool = False, simulated_ip: Optional[str] = None) -> Dict[str, Any]:
    """
    Detects the user's current geographic location and postal/ZIP code via client browser or IP geolocation.
    Supports client browser query params, client IP headers, simulated US IPs,
    and automatic rejection of cloud datacenter locations (e.g. The Dalles, OR 97058).
    Returns a dictionary with 'zip', 'city', 'region', 'country', 'lat', 'lon', 'source'.
    """
    global _CACHED_USER_LOCATION

    # Resolve simulation parameters
    target_ip = simulated_ip or os.getenv("CARE_SIMULATED_IP")
    target_zip = os.getenv("CARE_SIMULATED_ZIP")

    try:
        import streamlit as st
        # 1. First priority: Check if client browser passed its directly detected ZIP code
        if hasattr(st, "query_params") and not target_ip and not target_zip:
            if "client_zip" in st.query_params:
                c_zip = str(st.query_params["client_zip"]).strip()
                c_city = safe_city_name(st.query_params.get("client_city", ""))
                c_lat = None
                c_lon = None
                if "client_lat" in st.query_params and "client_lon" in st.query_params:
                    try:
                        c_lat = float(st.query_params["client_lat"])
                        c_lon = float(st.query_params["client_lon"])
                    except Exception:
                        pass
                client_loc = {
                    "zip": c_zip,
                    "city": c_city or "Current Location",
                    "region": "",
                    "country": "",
                    "lat": c_lat,
                    "lon": c_lon,
                    "source": "client_browser"
                }
                if hasattr(st, "session_state"):
                    st.session_state["detected_user_location"] = client_loc
                if not _in_streamlit_session():
                    _CACHED_USER_LOCATION = client_loc
                # Remove client_zip from query_params to keep the URL clean and avoid overriding user searches
                st.query_params.pop("client_zip", None)
                st.query_params.pop("client_city", None)
                st.query_params.pop("client_lat", None)
                st.query_params.pop("client_lon", None)
                return client_loc

            if os.environ.get("CAREATZERO_DEBUG") == "1":  # testing tool, off on the live site
                if "simulated_ip" in st.query_params:
                    target_ip = st.query_params["simulated_ip"]
                if "simulated_zip" in st.query_params:
                    target_zip = st.query_params["simulated_zip"]

        if hasattr(st, "session_state"):
            if not target_ip and "simulated_ip" in st.session_state:
                target_ip = st.session_state["simulated_ip"]
            if not target_zip and "simulated_zip" in st.session_state:
                target_zip = st.session_state["simulated_zip"]

            # Per-session caching check (isolated per user)
            if not force_refresh and not target_ip and not target_zip:
                sess_loc = st.session_state.get("detected_user_location")
                if sess_loc and sess_loc.get("source") != "fallback" and not is_datacenter_location(sess_loc):
                    return sess_loc
    except Exception:
        pass

    # Outside Streamlit (e.g. pytest): check global cache if valid.
    # Never inside a user's session: this cache is shared by everyone on the server,
    # so using it there could show one user another user's location.
    if not _in_streamlit_session() and _CACHED_USER_LOCATION is not None and _CACHED_USER_LOCATION.get("source") != "fallback" and not force_refresh and not target_ip and not target_zip and not is_datacenter_location(_CACHED_USER_LOCATION):
        return _CACHED_USER_LOCATION

    # If target_zip is directly specified
    if target_zip:
        loc = {
            "zip": str(target_zip).strip(),
            "city": "Simulated City",
            "region": "US",
            "country": "United States",
            "lat": 35.7721,
            "lon": -78.6386,
            "source": "simulated_zip"
        }
        if not _in_streamlit_session():
            _CACHED_USER_LOCATION = loc
        try:
            import streamlit as st
            if hasattr(st, "session_state"):
                st.session_state["detected_user_location"] = loc
        except Exception:
            pass
        return loc

    # A server-side lookup already failed in this session: don't wait on it again on every screen
    # (the browser detector or the user's own ZIP takes over; "Use my location" retries).
    try:
        import streamlit as st
        if (_in_streamlit_session() and not force_refresh and not target_ip and not target_zip
                and st.session_state.get("server_location_lookup_failed")):
            return {"zip": DEFAULT_FALLBACK_ZIP, "city": "", "region": "", "country": "",
                    "lat": None, "lon": None, "source": "fallback"}
    except Exception:
        pass

    # If target_ip not explicitly set, extract real client IP from incoming request
    if not target_ip:
        client_ip = get_client_ip()
        if client_ip:
            target_ip = client_ip

    # If we are in a cloud environment and target_ip is STILL None:
    # Do NOT query https://ipinfo.io/json with no IP, because that will resolve
    # the server container IP in The Dalles, Oregon!
    if is_cloud_environment() and not target_ip:
        fallback = {
            "zip": DEFAULT_FALLBACK_ZIP,
            "city": "Chapel Hill",
            "region": "NC",
            "country": "US",
            "lat": 35.9333,
            "lon": -79.0333,
            "source": "fallback"
        }
        return fallback

    # Determine services endpoints
    if target_ip:
        services = [
            (f"https://freeipapi.com/api/json/{target_ip}", "zipCode", "cityName", "regionName", "countryName"),
            (f"https://ipinfo.io/{target_ip}/json", "postal", "city", "region", "country"),
        ]
    else:
        # Local development on developer's machine: query own IP
        services = [
            ("https://ipinfo.io/json", "postal", "city", "region", "country"),
            ("https://freeipapi.com/api/json", "zipCode", "cityName", "regionName", "countryName"),
        ]

    detected = None
    for url, zip_k, city_k, reg_k, cntry_k in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.88.1 (CareAtZero/1.0)"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                z = data.get(zip_k)
                if z:
                    z_clean = str(z).strip()
                    lat = data.get("latitude")
                    lon = data.get("longitude")
                    if lat is None and "loc" in data:
                        parts = data["loc"].split(",")
                        if len(parts) == 2:
                            lat = float(parts[0])
                            lon = float(parts[1])

                    loc_candidate = {
                        "zip": z_clean,
                        "city": safe_city_name(str(data.get(city_k) or "")),
                        "region": safe_city_name(str(data.get(reg_k) or "")),
                        "country": str(data.get(cntry_k) or "").strip(),
                        "lat": float(lat) if lat is not None else None,
                        "lon": float(lon) if lon is not None else None,
                        "source": url
                    }

                    # Verify candidate is NOT a cloud datacenter
                    if not is_datacenter_location(loc_candidate):
                        detected = loc_candidate
                        break
        except Exception:
            continue

    if detected:
        if not _in_streamlit_session():
            _CACHED_USER_LOCATION = detected
        try:
            import streamlit as st
            if hasattr(st, "session_state"):
                st.session_state["detected_user_location"] = detected
        except Exception:
            pass
        return detected

    try:
        import streamlit as st
        if _in_streamlit_session():
            st.session_state["server_location_lookup_failed"] = True
    except Exception:
        pass

    # Return fallback without poisoning cache
    fallback = {
        "zip": DEFAULT_FALLBACK_ZIP,
        "city": "Chapel Hill",
        "region": "NC",
        "country": "US",
        "lat": 35.9333,
        "lon": -79.0333,
        "source": "fallback"
    }
    return fallback


def get_user_current_zip() -> str:
    """
    Returns the user's detected ZIP/postal code, or "" if their location couldn't be
    detected. The app then asks "Enter your ZIP code" instead of guessing a location,
    since it is meant to work anywhere in the U.S.
    """
    loc = detect_user_location()
    if not loc or loc.get("source") == "fallback":
        return ""
    return str(loc.get("zip") or "").strip()


# Pre-compiled coordinate reference for NC Research Triangle & regional ZIP codes
NC_ZIP_COORDINATES: Dict[str, Tuple[float, float, str]] = {
    # Wake County (Raleigh, Cary, Apex, Garner, Wake Forest, Morrisville)
    "27601": (35.7721, -78.63861, "Raleigh Downtown, NC"),
    "27603": (35.7369, -78.6475, "South Raleigh, NC"),
    "27604": (35.8105, -78.5833, "East Raleigh, NC"),
    "27605": (35.7891, -78.6575, "Central Raleigh, NC"),
    "27606": (35.7533, -78.7056, "West Raleigh, NC"),
    "27607": (35.8014, -78.6947, "Northwest Raleigh / Blue Ridge, NC"),
    "27608": (35.8078, -78.6417, "Five Points Raleigh, NC"),
    "27609": (35.8453, -78.6253, "North Raleigh, NC"),
    "27610": (35.7678, -78.5683, "Southeast Raleigh, NC"),
    "27611": (35.7796, -78.6382, "Raleigh, NC"),
    "27612": (35.8492, -78.7003, "Crabtree Raleigh, NC"),
    "27613": (35.8892, -78.7183, "Leesville Raleigh, NC"),
    "27614": (35.9186, -78.5997, "North Raleigh / Wakefield, NC"),
    "27615": (35.8753, -78.6253, "North Raleigh / Six Forks, NC"),
    "27616": (35.8833, -78.5417, "Northeast Raleigh, NC"),
    "27617": (35.9083, -78.7667, "Brier Creek Raleigh, NC"),
    "27511": (35.7611, -78.7811, "Cary, NC"),
    "27513": (35.8011, -78.7983, "North Cary, NC"),
    "27518": (35.7231, -78.8028, "South Cary, NC"),
    "27519": (35.8183, -78.8833, "West Cary, NC"),
    "27502": (35.7322, -78.8503, "Apex, NC"),
    "27529": (35.7114, -78.6142, "Garner, NC"),
    "27539": (35.6547, -78.7456, "Apex / Holly Springs, NC"),
    "27540": (35.6514, -78.8336, "Holly Springs, NC"),
    "27545": (35.7761, -78.4892, "Knightdale, NC"),
    "27560": (35.8419, -78.8286, "Morrisville, NC"),
    "27587": (35.9797, -78.5097, "Wake Forest, NC"),
    "27591": (35.8236, -78.3639, "Wendell, NC"),
    "27592": (35.5892, -78.6256, "Willow Spring, NC"),
    "27597": (35.8458, -78.2917, "Zebulon, NC"),

    # Durham County (Durham, RTP)
    "27701": (35.9967, -78.8986, "Downtown Durham, NC"),
    "27702": (35.9940, -78.8986, "Durham Central, NC"),
    "27703": (35.9556, -78.8167, "East Durham, NC"),
    "27704": (36.0389, -78.8833, "North Durham, NC"),
    "27705": (36.0167, -78.9667, "West Durham / Duke, NC"),
    "27707": (35.9667, -78.9333, "Southwest Durham, NC"),
    "27709": (35.9167, -78.8667, "Research Triangle Park (RTP), NC"),
    "27712": (36.1167, -78.9167, "North Durham / Bahama, NC"),
    "27713": (35.9000, -78.9333, "South Durham / Southpoint, NC"),

    # Orange County (Chapel Hill, Carrboro, Hillsborough)
    "27514": (35.9333, -79.0333, "Chapel Hill / East, NC"),
    "27515": (35.9132, -79.0558, "UNC Campus Chapel Hill, NC"),
    "27516": (35.9000, -79.1167, "Chapel Hill / Carrboro, NC"),
    "27517": (35.8667, -79.0333, "South Chapel Hill, NC"),
    "27278": (36.0750, -79.1000, "Hillsborough, NC"),

    # Alamance & Chatham & Johnston (Burlington, Pittsboro, Siler City, Smithfield, Clayton)
    "27215": (36.0833, -79.4333, "Burlington, NC"),
    "27217": (36.1167, -79.4000, "East Burlington, NC"),
    "27312": (35.7167, -79.1833, "Pittsboro, NC"),
    "27344": (35.7250, -79.4611, "Siler City, NC"),
    "27520": (35.6500, -78.4500, "Clayton, NC"),
    "27577": (35.5167, -78.3333, "Smithfield, NC"),

    # Piedmont & State anchors (Greensboro, Winston-Salem, Charlotte, Fayetteville, Wilmington)
    "27401": (36.0726, -79.7920, "Greensboro Downtown, NC"),
    "27101": (36.0999, -80.2442, "Winston-Salem Downtown, NC"),
    "28202": (35.2271, -80.8431, "Charlotte Center City, NC"),
    "28301": (35.0527, -78.8784, "Fayetteville, NC"),
    "28401": (34.2257, -77.9447, "Wilmington, NC"),
}

# Default anchor: Research Triangle centroid


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth in miles.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999.0

    R = 3958.8  # Earth radius in miles

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return round(distance, 1)


def geocode_location(location_query: str) -> Optional[Tuple[float, float, str]]:
    """
    Turns what the user typed (a ZIP code like '27514' or '27514-1234', or a city
    like 'Raleigh') into (lat, lon, label). Returns None if the place isn't known,
    so the screen can say so; it never guesses a location.
    """
    cleaned = (location_query or "").strip().upper()
    if not cleaned:
        # Never guess a location: the screens ask "Enter your ZIP code" before calling this.
        raise ValueError("No location given; ask the user for a ZIP code or city.")
    zip_match = re.fullmatch(r"(\d{5})(?:-\d{4})?", cleaned)
    zip5 = zip_match.group(1) if zip_match else None

    # ZIP code in the known NC table
    if zip5 and zip5 in NC_ZIP_COORDINATES:
        return NC_ZIP_COORDINATES[zip5]

    # The user's own detected location (has exact coordinates; may be a non-U.S. postal code)
    user_loc = detect_user_location()
    detected = str(user_loc.get("zip", "")).upper()
    if detected and (zip5 or cleaned) == detected and user_loc.get("source") != "fallback":
        if user_loc.get("lat") is not None and user_loc.get("lon") is not None:
            city_str = user_loc.get("city") or "Current Location"
            label = f"{city_str} ({detected})" if detected not in city_str else city_str
            return user_loc["lat"], user_loc["lon"], label

    # Any other U.S. ZIP: its center from the U.S. Census ZIP list
    if zip5:
        try:
            from live.zip_centroids import coords_for_zip
            coords = coords_for_zip(zip5)
        except Exception:
            coords = None
        return (coords[0], coords[1], f"ZIP {zip5}") if coords else None

    # City name: match whole words against the known NC areas ("Cary", "Chapel Hill, NC")
    city = re.sub(r",?\s*(NC|NORTH CAROLINA)\s*$", "", cleaned).strip()
    if len(city) >= 3:
        for zip_code, (lat, lon, label) in NC_ZIP_COORDINATES.items():
            words = re.split(r"[^A-Z]+", label.upper())
            name = " ".join(w for w in words if w)
            if re.search(rf"(^| ){re.escape(city)}( |$)", name):
                return lat, lon, label
    return None


def in_nc_pilot(lat: float, lon: float) -> bool:
    """True if the location is in North Carolina (ZIP codes 27xxx-28xxx), where clinic listings are covered."""
    if any(abs(lat - la) < 1e-6 and abs(lon - lo) < 1e-6 for la, lo, _ in NC_ZIP_COORDINATES.values()):
        return True
    try:
        from live.zip_centroids import nearest_zip
        z = nearest_zip(lat, lon)
    except Exception:
        return True  # can't tell: don't show a warning
    return z is None or z[:2] in ("27", "28")


def get_directions_url(address: str, destination_lat: Optional[float] = None, destination_lon: Optional[float] = None) -> str:
    """Generates Google Maps / OpenStreetMap directions link."""
    clean_addr = address.replace(" ", "+")
    if destination_lat and destination_lon:
        return f"https://www.google.com/maps/dir/?api=1&destination={destination_lat},{destination_lon}"
    return f"https://www.google.com/maps/search/?api=1&query={clean_addr}"
