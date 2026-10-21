import datetime
import os
import sys
from html import escape

import folium
import streamlit as st
from streamlit_folium import st_folium

# Ensure project root is strictly first in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not sys.path or sys.path[0] != PROJECT_ROOT:
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)

from scoring.care_access_score import calculate_care_access_score
from utils.geo import geocode_location, haversine_distance, get_directions_url, get_user_current_zip, in_nc_pilot
from utils.styles import inject_custom_css, render_header, LOGO_PATH
from utils.timezones import use_timezone_of
from utils.dates import today, today_str, format_event_dates, format_checked
from live.sources import load_live_data


st.set_page_config(
    page_title="Find Free & Low-Cost Care | CareAtZero",
    page_icon=LOGO_PATH,
    layout="wide"
)

inject_custom_css()
render_header("find_care")

# Header
st.markdown('<div class="cz-title">Find care</div>'
            '<div class="cz-sub">Free clinics, sliding-scale centers and upcoming pop-ups.</div>',
            unsafe_allow_html=True)

# Retrieve preset filters from session state if coming from Home page
user_detected_zip = get_user_current_zip()
default_service = st.session_state.get("selected_service", "Medical")
saved_loc = st.session_state.get("search_loc")
if saved_loc and str(saved_loc).strip():
    default_loc = str(saved_loc).strip()
else:
    default_loc = user_detected_zip  # "" if the location couldn't be detected
    if user_detected_zip:
        st.session_state["search_loc"] = user_detected_zip
        st.session_state["search_loc_auto"] = True
default_timing = st.session_state.get("search_timing", "This Week")
INCOME_OPTIONS = ["Under $25,000 / $0", "$25,000 - $45,000", "$45,000+", "Prefer not to say"]
default_income = st.session_state.get("income_band", INCOME_OPTIONS[0])

# --- FILTER SECTION ---
FILTER_KEYS = ("find_income", "find_cost", "find_dist", "find_sort")
COST_OPTIONS = ["All Low-Cost & Free", "Free Only ($0 Fee)", "Free & Very Low Cost", "Sliding Scale Included"]
SORT_OPTIONS = ["Care Access Score (Best realistic match)", "Closest Distance"]
if st.session_state.pop("reset_filters", False):  # "Reset filters" was tapped: back to the defaults
    for k in FILTER_KEYS:
        st.session_state.pop(k, None)
    st.session_state["income_band"] = INCOME_OPTIONS[0]
    default_income = INCOME_OPTIONS[0]

# Where: ZIP code box with its own Search button (people expect a button after typing)
with st.container(key="row_find_loc"):
    loc_col, btn_col = st.columns([3, 1], vertical_alignment="bottom")
    with loc_col:
        location_input = st.text_input(
            "Your Location (ZIP code or city)",
            value=default_loc,
            key="find_care_loc_input",
            placeholder="Enter your ZIP code",
            help=(f"Defaulted to your location ({user_detected_zip}). Enter any ZIP code or city."
                  if user_detected_zip else "Enter a ZIP code or city anywhere in the U.S.")
        )
    with btn_col:
        # Tapping Search applies the typed ZIP and refreshes the results below
        st.button("Search", icon=":material/search:", type="primary", key="find_search_btn", width="stretch")
if location_input and location_input.strip() != st.session_state.get("search_loc"):
    st.session_state["search_loc"] = location_input.strip()
    st.session_state["search_loc_auto"] = False  # typed by the user

with st.container():
    col1, col3 = st.columns(2)

    with col1:
        service_options = ["Medical", "Dental", "Vision", "Behavioral Health"]
        s_idx = service_options.index(default_service) if default_service in service_options else 0
        service_needed = st.selectbox("Type of care", service_options, index=s_idx,
                                      format_func=lambda s: "Mental health" if s == "Behavioral Health" else s)

    with col3:
        timing_options = ["This Week", "Today", "Flexible (Upcoming)"]
        t_idx = timing_options.index(default_timing) if default_timing in timing_options else 0
        timing_pref = st.selectbox("When do you need care?", timing_options, index=t_idx,
                                   format_func=lambda t: "Any time" if t.startswith("Flexible") else t)

    with st.expander("More filters: income, cost, distance", expanded=False):
        exp1, exp2 = st.columns(2)
        with exp1:
            income_band = st.selectbox("💵 **Household Income**", INCOME_OPTIONS, key="find_income",
                                       index=INCOME_OPTIONS.index(default_income) if default_income in INCOME_OPTIONS else 0,
                                       help="Used only to estimate sliding-scale fee tier. Never saved.")
        with exp2:
            cost_filter = st.selectbox("🏷️ **Cost Preference**", COST_OPTIONS, key="find_cost")

        col_dist, col_sort = st.columns(2)
        with col_dist:
            max_dist = st.slider("🚗 **Maximum Distance (miles)**", min_value=5, max_value=60, value=35, step=5,
                                 key="find_dist")
        with col_sort:
            sort_by = st.radio("📊 **Sort Results By**", SORT_OPTIONS, horizontal=True, key="find_sort")
        if st.button("Reset filters", icon=":material/restart_alt:", type="tertiary", key="find_reset_btn"):
            st.session_state["reset_filters"] = True
            st.rerun()

# Remember the choices, so Details scores the same way and "Back to results" keeps them
st.session_state["selected_service"] = service_needed
st.session_state["search_timing"] = timing_pref
st.session_state["income_band"] = income_band

# No location yet: ask for one instead of guessing
if not (location_input and location_input.strip()):
    st.info("Enter your ZIP code (or city) above to see free and low-cost care near you.")
    st.stop()

# Geocode location
place = geocode_location(location_input)
if place is None:
    st.error(f"We couldn't find \"{location_input.strip()}\". Try a 5-digit ZIP code, like 27601.")
    st.stop()
user_lat, user_lon, loc_label = place
use_timezone_of(user_lat, user_lon)

# Live data: HRSA, NC DHHS, SAMHSA and RAM (fetched together, kept for a few hours)
current_date_ref = today_str()
with st.spinner("Getting the latest clinics from HRSA, NC DHHS, SAMHSA and Remote Area Medical..."):
    live = load_live_data(user_lat, user_lon)
sites = live.sites
events = live.events
all_records = sites + events

if live.using_saved_directory:
    st.warning("The live data sources can't be reached right now, so these results come from the saved "
               "CareAtZero directory (last verified September 2026). Call ahead to confirm details.")
else:
    saved = [s.name for s in live.statuses if not s.ok and s.saved_copy_from]
    down = [s.name for s in live.statuses if not s.ok and not s.saved_copy_from]
    if saved:
        st.caption("Using a saved copy for " + ", ".join(saved) + " because the live site isn't available "
                   "to the app (marked on each result). Call ahead to confirm.")
    if down:
        st.caption("Temporarily unavailable, so not included: " + ", ".join(down) + ". Try again in a few minutes.")

if not in_nc_pilot(user_lat, user_lon):
    st.info("Clinic listings cover North Carolina in this version. Mental-health services and free pop-up "
            "clinics are shown anywhere in the U.S.")

# "When do you need care?" decides which pop-up events count
day = today()
window_end = {"Today": day, "This Week": day + datetime.timedelta(days=7)}.get(timing_pref)


def event_in_window(rec):
    try:
        start = datetime.date.fromisoformat(str(rec.get("date_start"))[:10])
        end = datetime.date.fromisoformat(str(rec.get("date_end") or rec.get("date_start"))[:10])
    except ValueError:
        return False
    return end >= day and (window_end is None or start <= window_end)

# Filter and score records
scored_records = []

for rec in all_records:
    # 1. Service Filter Check
    services = rec.get("services", [])
    service_match = any(service_needed.lower() in s.lower() for s in services)
    if not service_match:
        continue
    if rec.get("record_type") == "event" and not event_in_window(rec):
        continue

    # 2. Cost Filter Check
    cost_class = rec.get("cost_class", "Sliding Scale")
    if cost_filter == "Free Only ($0 Fee)" and cost_class != "Free":
        continue
    elif cost_filter == "Free & Very Low Cost" and cost_class not in ["Free", "Very Low Cost"]:
        continue

    # 3. Calculate distance
    rec_lat = rec.get("latitude")
    rec_lon = rec.get("longitude")
    if rec_lat is None or rec_lon is None:
        continue  # no location, so no honest distance: leave it out rather than guess
    dist = haversine_distance(user_lat, user_lon, rec_lat, rec_lon)

    if dist > max_dist:
        continue

    # 4. Calculate 100-point Care Access Score
    score, breakdown, reasons = calculate_care_access_score(
        record=rec,
        service_needed=service_needed,
        distance_miles=dist,
        timing_pref=timing_pref,
        user_income_band=income_band,
        reference_date_str=current_date_ref
    )

    rec_entry = {
        "record": rec,
        "distance": dist,
        "score": score,
        "breakdown": breakdown,
        "reasons": reasons
    }
    scored_records.append(rec_entry)

# Sort records
if "Closest Distance" in sort_by:
    scored_records.sort(key=lambda x: x["distance"])
else:
    scored_records.sort(key=lambda x: (x["score"], -x["distance"]), reverse=True)

st.markdown("---")

# Results Header
res_col1, res_col2 = st.columns([3, 1])
with res_col1:
    # Say exactly what the list is based on, so a change is easy to see
    care_label = "Mental health" if service_needed == "Behavioral Health" else service_needed
    when_label = {"Today": "Today", "This Week": "This week"}.get(timing_pref, "Any time")
    cost_label = {"Free Only ($0 Fee)": " · Free only", "Free & Very Low Cost": " · Free & very low cost"}.get(cost_filter, "")
    count = len(scored_records)
    st.markdown(f"**{count} {care_label} option{'s' if count != 1 else ''}** within {max_dist} mi of "
                f"{escape(loc_label)} · {when_label}{cost_label}")
with res_col2:
    view_mode = st.radio("View as:", ["📋 List View", "🗺️ Map View"], horizontal=True, label_visibility="collapsed")

# Map View Rendering
if view_mode == "🗺️ Map View":
    st.markdown("#### 🗺️ Interactive Clinic & Pop-Up Event Map")
    m = folium.Map(location=[user_lat, user_lon], zoom_start=10, tiles="OpenStreetMap")

    # User search location marker
    folium.Marker(
        [user_lat, user_lon],
        popup=folium.Popup(escape(f"Your Location: {loc_label}"), parse_html=True),
        tooltip="Your Location",
        icon=folium.Icon(color="red", icon="user", prefix="fa")
    ).add_to(m)

    # Provider markers
    for item in scored_records:
        rec = item["record"]
        lat = rec.get("latitude")
        lon = rec.get("longitude")
        if not lat or not lon:
            continue

        cost = rec.get("cost_class", "Sliding Scale")
        is_evt = rec.get("record_type") == "event"
        title = rec.get("title") or rec.get("name")

        color = "green" if cost == "Free" else ("blue" if cost == "Sliding Scale" else "orange")
        icon_name = "calendar" if is_evt else "plus-square"

        popup_html = (f"<b>{escape(str(title))}</b><br/>Cost: <b>{escape(cost)}</b><br/>"
                      f"Score: <b>{item['score']}/100</b><br/>Distance: {item['distance']} mi<br/>"
                      f"Phone: {escape(rec.get('phone') or 'N/A')}")

        folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=escape(f"[{cost}] {title} ({item['distance']} mi)").replace("`", "'"),
            icon=folium.Icon(color=color, icon=icon_name, prefix="fa")
        ).add_to(m)

    st_folium(m, width=None, height=450, returned_objects=[])  # don't rerun the page on every pan/zoom
    st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)

# List View of Results
PAGE_SIZE = 25
search_key = (service_needed, location_input, timing_pref)
if st.session_state.get("results_search_key") != search_key:
    st.session_state["results_search_key"] = search_key
    st.session_state["results_shown"] = PAGE_SIZE
shown = st.session_state.get("results_shown", PAGE_SIZE)

if not scored_records:
    st.warning(f"No {service_needed} care options found within {max_dist} miles of {loc_label} matching your criteria. Try expanding the distance slider or choosing 'All Low-Cost & Free'.")
else:
    for idx, item in enumerate(scored_records[:shown]):
        rec = item["record"]
        score = item["score"]
        dist = item["distance"]
        reasons = item["reasons"]

        is_event = rec.get("record_type") == "event"
        cost_class = rec.get("cost_class", "Sliding Scale")
        # Text from outside sources is escaped, so it is always shown as text, never as page code
        e = lambda key, default="": escape(str(rec.get(key) or default))
        title = escape(str(rec.get("title") or rec.get("name") or ""))

        # Badge styling
        if cost_class == "Free":
            cost_badge = "<span class='badge-free'>FREE ($0)</span>"
        elif cost_class == "Very Low Cost":
            cost_badge = "<span class='badge-lowcost'>VERY LOW COST</span>"
        elif cost_class == "Sliding Scale":
            cost_badge = "<span class='badge-sliding'>SLIDING SCALE</span>"
        else:
            cost_badge = "<span class='badge-sliding'>COST: ASK THE CLINIC</span>"

        type_badge = "<span class='badge-event'>🚐 POP-UP EVENT</span>" if is_event else "<span class='badge-lowcost'>🏥 PERMANENT CLINIC</span>"

        timing_text = (f"📅 <strong>{format_event_dates(rec.get('date_start'), rec.get('date_end'))}</strong> ({e('time_details')})"
                       if is_event else f"⏰ Hours: {e('hours_summary')}")
        appt_text = f"📋 Rule: {e('appointment_rule')}"
        docs_text = f"📄 What to bring: {escape(', '.join(rec.get('documents_required') or ['Photo ID']))}"

        # Render custom styled care card
        card_html = f"""
        <div class="care-card">
            <div class="care-card-header">
                <div>
                    {cost_badge} {type_badge}
                    <h3 class="care-card-title" style="margin-top: 6px;">{title}</h3>
                </div>
                <div class="score-badge">
                    ⭐ Care Access Score: <strong>{score}/100</strong>
                </div>
            </div>
            <div class="card-meta">📍 <strong>{e('address')}, {e('city')}, {e('state', 'NC')}</strong> • <span style="color:#2563EB; font-weight:600;">{dist} miles away</span></div>
            <div class="card-meta">🩺 <strong>Services:</strong> {escape(', '.join(rec.get('services', [])))}</div>
            <div class="card-meta">{timing_text}</div>
            <div class="card-meta">{appt_text}</div>
            <div class="card-meta">{docs_text}</div>
            <div class="reasons-box">
                <strong>Why this matches:</strong>
                <ul>
                    {''.join([f'<li>{escape(r)}</li>' for r in reasons[:3]])}
                </ul>
            </div>
            <div class="source-meta">
                Source: {e('source_name', 'Verified Safety Net Directory')} • Last checked: {format_checked(rec.get('last_checked'))}
            </div>
        </div>
        """
        # "&#36;" is a dollar sign: a plain "$...$" pair would be shown as a math formula
        st.markdown(card_html.replace("$", "&#36;"), unsafe_allow_html=True)

        # Action Buttons Row (kept side by side on phones)
        row = st.container(key=f"row_res_{idx}")
        btn_c1, btn_c2, btn_c3 = row.columns(3)

        with btn_c1:
            if st.button("Details", key=f"btn_det_{rec.get('id')}_{idx}", type="primary", width="stretch"):
                st.session_state["selected_care_id"] = rec.get("id")
                st.session_state["selected_care_type"] = rec.get("record_type")
                st.switch_page("pages/2_📋_Care_Details.py")

        with btn_c2:
            phone_num = rec.get("phone", "")
            if phone_num:
                clean_phone = phone_num.replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
                st.link_button("Call", f"tel:{clean_phone}", icon=":material/call:", width="stretch")
            else:
                st.button("Call", icon=":material/call:", disabled=True, key=f"call_dis_{idx}", width="stretch")

        with btn_c3:
            addr = f"{rec.get('address')}, {rec.get('city')}, {rec.get('state') or 'NC'} {rec.get('zip_code') or ''}".strip()
            maps_url = get_directions_url(addr, rec.get("latitude"), rec.get("longitude"))
            st.link_button("Directions", maps_url, width="stretch")

        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    if len(scored_records) > shown:
        if st.button(f"Show more ({len(scored_records) - shown} more)", key="btn_show_more", width="stretch"):
            st.session_state["results_shown"] = shown + PAGE_SIZE
            st.rerun()
