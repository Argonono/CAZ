import os
import sys
from html import escape

import streamlit as st

# Ensure project root is strictly first in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if not sys.path or sys.path[0] != PROJECT_ROOT:
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)

from database.db import DB_PATH
from data.seed_data import seed_database
from utils.styles import inject_custom_css, render_header, render_emergency_banner, LOGO_PATH
from utils.timezones import use_timezone_of
from utils.dates import format_checked, format_event_dates
from live.sources import load_live_data, warm_up
from utils.geo import (
    get_user_current_zip, detect_user_location,
    set_simulated_location, US_SIMULATION_PRESETS, geocode_location, haversine_distance,
    inject_client_geo_detector, safe_city_name
)


# Set page configuration
st.set_page_config(
    page_title="CareAtZero | Free & low-cost care. Know where to go.",
    page_icon=LOGO_PATH,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize database if needed
if not os.path.exists(DB_PATH):
    seed_database()

# Inject styling
inject_custom_css()

# Logo bar + bottom tab bar
render_header("home")

# Find the user's location in their browser (GPS if allowed, else internet connection);
# the result comes back to this session without reloading the page
inject_client_geo_detector()


st.markdown('<div class="cz-title">Find free care near you</div>'
            '<div class="cz-sub">No insurance needed. Pick what you need below.</div>',
            unsafe_allow_html=True)
render_emergency_banner()

# Care type: 2x2 cards, tap one to select it (Medical by default)
st.markdown("**What do you need?**")

care_cards = [
    ("Medical", ":material/stethoscope:", "Check-ups, sick visits"),
    ("Dental", ":material/dentistry:", "Cleanings, extractions"),
    ("Vision", ":material/visibility:", "Eye exams, glasses"),
    ("Behavioral Health", ":material/psychology:", "Counseling, crisis care"),
]
if "home_service" not in st.session_state:
    st.session_state["home_service"] = st.session_state.get("selected_service", "Medical")

for row_start in (0, 2):
    with st.container(key=f"row_care_{row_start}"):
        card_cols = st.columns(2)
        for col, (service, icon, desc) in zip(card_cols, care_cards[row_start:row_start + 2]):
            with col:
                with st.container(key=f"svc_{service.replace(' ', '_').lower()}"):
                    label = "Mental health" if service == "Behavioral Health" else service
                    if st.button(f"{label}  \n:gray[{desc}]", icon=icon, key=f"care_card_{service}",
                                 width="stretch",
                                 type="primary" if st.session_state["home_service"] == service else "secondary"):
                        st.session_state["home_service"] = service
                        st.rerun()

# Quick Location Search Box
user_detected_zip = get_user_current_zip()

saved_loc = st.session_state.get("search_loc")
if saved_loc and str(saved_loc).strip():
    default_loc = str(saved_loc).strip()
else:
    default_loc = user_detected_zip  # "" if the location couldn't be detected
    if user_detected_zip:
        st.session_state["search_loc"] = user_detected_zip
        st.session_state["search_loc_auto"] = True  # filled in for the user, not typed

loc_info = detect_user_location()
city_label = safe_city_name(loc_info.get("city", "")) if user_detected_zip else ""
location_desc = f"{city_label} ({user_detected_zip})" if city_label else user_detected_zip

timing_labels = {"Today": "Today", "This Week": "This week", "Flexible (Upcoming)": "Any time"}

# The box's text lives in session state, so a location found after the screen first
# appears (the browser's answer arrives a moment later) really shows up in the box.
# An empty box is filled in; anything the user typed is left alone.
if default_loc and not str(st.session_state.get("home_search_loc_input") or "").strip():
    st.session_state["home_search_loc_input"] = default_loc

with st.form(key="home_quick_search_form", clear_on_submit=False, border=False):
    quick_loc = st.text_input(
        "Where are you? (ZIP code or city)",
        placeholder="Enter your ZIP code",
        help=(f"Detected location: {location_desc}. You can type any ZIP code or city."
              if user_detected_zip else "Enter a ZIP code or city anywhere in the U.S."),
        key="home_search_loc_input"
    )
    quick_timing = st.segmented_control(
        "When do you need care?", list(timing_labels), format_func=timing_labels.get,
        default="This Week", key="home_timing"
    ) or "This Week"
    search_submitted = st.form_submit_button("Find free care", icon=":material/search:", type="primary",
                                             width="stretch", key="home_find_care_submit_btn")

if search_submitted and not (quick_loc and str(quick_loc).strip()):
    st.error("Enter your ZIP code (or city) to find care near you.")
elif search_submitted:
    target_search = str(quick_loc).strip()
    st.session_state["selected_service"] = st.session_state["home_service"]
    st.session_state["search_loc"] = target_search
    st.session_state["search_loc_auto"] = False  # the user chose this location
    st.session_state["search_timing"] = quick_timing
    if hasattr(st, "query_params"):
        st.query_params.pop("client_zip", None)
        st.query_params.pop("client_city", None)
        st.query_params.pop("client_lat", None)
        st.query_params.pop("client_lon", None)
    st.switch_page("pages/1_🔍_Find_Free_Care.py")

loc_col_a = st.container()
with loc_col_a:
    if user_detected_zip:
        st.caption(f"Detected location: {location_desc}")
    elif not st.session_state.get("browser_location_checked"):
        st.caption("Finding your location... or enter your ZIP code above.")
    else:
        st.caption("We couldn't detect your location. Enter your ZIP code above, "
                   "or tap **Use my location** and allow location access.")
    if st.button("Use my location", icon=":material/my_location:", key="btn_redetect_loc", help="Re-detect location using your device"):
        for k in ("search_loc", "detected_user_location", "browser_location_checked",
                  "server_location_lookup_failed", "home_search_loc_input"):
            st.session_state.pop(k, None)
        st.session_state["search_loc_auto"] = True
        st.session_state["geo_attempt"] = st.session_state.get("geo_attempt", 0) + 1
        if hasattr(st, "query_params"):
            st.query_params.pop("geo_checked", None)
            st.query_params.pop("client_zip", None)
            st.query_params.pop("client_city", None)
        st.rerun()

# Developer tool for testing location detection: only when CAREATZERO_DEBUG=1 is set
if os.environ.get("CAREATZERO_DEBUG") == "1" and st.query_params.get("test_geo") == "true":
    with st.expander("📍 **Simulate / Test USA Geolocation (Auto-detect Testing)**", expanded=True):
        st.caption("Change simulated US location to test automatic ZIP code detection across different regions.")
        sim_col1, sim_col2 = st.columns([3, 1])
        with sim_col1:
            sim_options = ["Auto-Detect (Current IP)"] + list(US_SIMULATION_PRESETS.keys())
            current_active = "Auto-Detect (Current IP)"
            if "simulated_ip" in st.session_state:
                for k, v in US_SIMULATION_PRESETS.items():
                    if v == st.session_state["simulated_ip"]:
                        current_active = k
                        break
            chosen_sim = st.selectbox(
                "Select USA location to simulate:",
                sim_options,
                index=sim_options.index(current_active) if current_active in sim_options else 0,
                key="sim_loc_dropdown"
            )
        with sim_col2:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Apply Location", key="btn_apply_sim", width="stretch"):
                if chosen_sim == "Auto-Detect (Current IP)":
                    set_simulated_location(None)
                else:
                    set_simulated_location(chosen_sim)
                st.rerun()

st.markdown("---")

def render_popup_card(evt, miles):
    # Text from RAM's calendar is escaped, so it is always shown as text, never as page code
    e = lambda key: escape(str(evt.get(key) or ""))
    when = format_event_dates(evt.get("date_start"), evt.get("date_end"))
    cost_badge = "<span class='badge-free'>FREE</span>" if evt.get("cost_class") == "Free" else ""
    st.markdown(f"""
    <div class="care-card">
        <div style="margin-bottom: 8px;"><span class='badge-event'>📅 {when}</span> {cost_badge}</div>
        <h4 style="margin: 4px 0; color: #0E2A5C;">{e('title')}</h4>
        <div class="card-meta">📍 {e('location_name')}, {e('city')}, {e('state')} {e('zip_code')} • {miles:.0f} mi away</div>
        <div class="card-meta">🩺 <strong>Services:</strong> {escape(', '.join(evt.get('services', [])))}</div>
        <div class="card-meta">⏰ {e('time_details')}</div>
        <div class="source-meta">Source: {e('source_name')} • Checked {format_checked(evt.get('last_checked'))}</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("View event details", key=f"btn_evt_home_{evt.get('id')}", width="stretch"):
        st.session_state["selected_care_id"] = evt.get("id")
        st.session_state["selected_care_type"] = "event"
        st.session_state["search_loc"] = clean_loc
        st.switch_page("pages/2_📋_Care_Details.py")


# Live pop-up events: RAM's calendar + hand-verified community events, nearest date first
POPUP_RADIUS_MILES = 50   # "near you" = within a reasonable drive
NEAREST_FALLBACK_COUNT = 2  # if none are that close, show the nearest few, clearly labeled
clean_loc = str(quick_loc or "").strip() or default_loc
matching_events, nearest_events, ram_status = [], [], None
place = geocode_location(clean_loc) if clean_loc else None
if clean_loc and place is None:
    st.warning(f"We couldn't find \"{escape(clean_loc)}\". Try a 5-digit ZIP code, like 27601.")
    clean_loc = ""
if place:  # no location yet -> ask for a ZIP code instead of guessing one
    home_lat, home_lon, home_label = place
    use_timezone_of(home_lat, home_lon)
    with st.spinner("Checking upcoming free pop-up clinics..."):
        live_events = load_live_data(home_lat, home_lon, include_sites=False)
    ram_status = next((s for s in live_events.statuses if s.key == "ram"), None)
    warm_up(home_lat, home_lon)  # start loading clinics now, so the Find screen opens instantly
    all_events = []
    for evt in live_events.events:
        if evt.get("latitude") is None or evt.get("longitude") is None:
            continue
        miles = haversine_distance(home_lat, home_lon, evt["latitude"], evt["longitude"])
        all_events.append((evt, miles))
        if miles <= POPUP_RADIUS_MILES:
            matching_events.append((evt, miles))
    if not matching_events:
        nearest_events = sorted(all_events, key=lambda pair: pair[1])[:NEAREST_FALLBACK_COUNT]

st.subheader("Upcoming free pop-up clinics")
st.markdown("Pop-up clinics give **free care for a day or two**, usually with no insurance, ID or income proof needed. "
            "*Arrive early for a ticket.*")

if ram_status is not None and ram_status.saved_copy_from:
    if "web page instead" in (ram_status.error or ""):
        why = "RAM's website doesn't allow automatic downloads from our server"
    else:
        why = "RAM's live calendar couldn't be reached just now"
    st.caption(f"{why}, so these come from a copy of RAM's calendar saved "
               f"{format_checked(ram_status.saved_copy_from)}. "
               "Confirm on [ramusa.org/schedule](https://www.ramusa.org/schedule/) before you go.")

if not clean_loc:
    st.info("Enter your ZIP code above to see free pop-up clinics near you.")
elif matching_events:
    st.markdown(f"**{len(matching_events)} within {POPUP_RADIUS_MILES} miles of {home_label}:**")
    for evt, miles in matching_events[:3]:
        render_popup_card(evt, miles)
elif ram_status is not None and not ram_status.ok and not ram_status.saved_copy_from:
    st.warning("The pop-up clinic calendar couldn't be reached just now. Please try again in a few minutes.")
else:
    st.info(f"No free pop-up clinics are scheduled within {POPUP_RADIUS_MILES} miles of {home_label} right now. "
            "Tap **Find free care** to see clinics near you that are open all year.")
    if nearest_events:
        st.markdown("**Nearest upcoming pop-up clinics** (farther away):")
        for evt, miles in nearest_events:
            render_popup_card(evt, miles)
    st.caption("This list updates automatically from Remote Area Medical's live calendar "
               "([full schedule](https://www.ramusa.org/schedule/)).")

# Footer
st.markdown("---")
st.markdown("<div style='text-align: center; font-size: 0.85rem; color: #64748B; padding: 10px 0;'><span style='color: #0E2A5C; font-weight: 700;'>CareAt</span><span style='color: #0A7C74; font-weight: 700;'>Zero</span> • Free &amp; low-cost care. Know where to go. • Research Triangle Pilot • Version 1.0</div>", unsafe_allow_html=True)



