import os
import re
import sys
from html import escape

import streamlit as st

# Ensure project root is strictly first in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not sys.path or sys.path[0] != PROJECT_ROOT:
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)

from scoring.care_access_score import calculate_care_access_score
from utils.calendar import generate_ics_calendar
from utils.export import generate_shareable_referral_text
from utils.geo import get_directions_url, geocode_location, haversine_distance, get_user_current_zip
from utils.styles import inject_custom_css, render_header, LOGO_PATH
from utils.timezones import use_timezone_of
from utils.dates import today_str, checked_parts, format_event_dates, timezone_label
from live.sources import find_record


st.set_page_config(
    page_title="Care Details | CareAtZero",
    page_icon=LOGO_PATH,
    layout="wide"
)

inject_custom_css()
render_header("details")

# Check if a care option is selected in session state
selected_id = st.session_state.get("selected_care_id")
if not selected_id:
    # Default fallback: pick first site or event
    st.info("No specific care option selected. Showing default safety-net option.")
    selected_id = "site_shac_01"

# Where the user searched from (also used to find the live record and its distance)
user_loc = st.session_state.get("search_loc") or get_user_current_zip()
if not user_loc:
    st.info("Enter your ZIP code on the Home or Find screen first, so we can show distance and directions.")
    if st.button("Go to Find care", type="primary"):
        st.switch_page("pages/1_🔍_Find_Free_Care.py")
    st.stop()
place = geocode_location(user_loc)
if place is None:
    st.error(f"We couldn't find \"{user_loc}\". Go back and try a 5-digit ZIP code.")
    if st.button("Go to Find care", type="primary", key="btn_bad_loc"):
        st.switch_page("pages/1_🔍_Find_Free_Care.py")
    st.stop()
u_lat, u_lon, loc_label = place
use_timezone_of(u_lat, u_lon)

# Fetch record: live data first, then the saved directory
record = find_record(selected_id, u_lat, u_lon)

if not record:
    st.error(f"Care option with ID '{selected_id}' not found.")
    if st.button("⬅️ Return to Search"):
        st.switch_page("pages/1_🔍_Find_Free_Care.py")
    st.stop()

FACILITY_LABELS = {
    "fqhc": "Federally funded community health center",
    "free_clinic": "Free & charitable clinic",
    "behavioral_health": "Behavioral health treatment facility",
    "mobile": "Mobile clinic",
}

# Basic fields
title = escape(str(record.get("title") or record.get("name") or ""))
cost_class = record.get("cost_class", "Sliding Scale")
is_event = record.get("record_type") == "event"
full_addr = f"{record.get('address')}, {record.get('city')}, {record.get('state')} {record.get('zip_code')}".strip(" ,")

# Calculate score breakdown for details (for the type of care the user searched for)
has_location = record.get("latitude") is not None and record.get("longitude") is not None
dist = haversine_distance(u_lat, u_lon, record.get("latitude"), record.get("longitude")) if has_location else 0.0
score, breakdown, reasons = calculate_care_access_score(
    record=record,
    service_needed=st.session_state.get("selected_service", "Medical"),
    distance_miles=dist,
    timing_pref=st.session_state.get("search_timing", "This Week"),
    user_income_band=st.session_state.get("income_band", "Under $25,000 / $0"),
    reference_date_str=today_str()
)

# Back button & Breadcrumb
if st.button("Back to results", icon=":material/arrow_back:", type="tertiary"):
    st.switch_page("pages/1_🔍_Find_Free_Care.py")

# Title Header & Badges
cost_badge = {
    "Free": "<span class='badge-free'>100% FREE CARE (&#36;0)</span>",
    "Very Low Cost": "<span class='badge-lowcost'>VERY LOW COST (&#36;5-&#36;25)</span>",
    "Sliding Scale": "<span class='badge-sliding'>SLIDING SCALE DISCOUNT</span>",
}.get(cost_class, "<span class='badge-sliding'>COST: ASK THE CLINIC</span>")
type_badge = "<span class='badge-event'>🚐 MOBILE / POP-UP EVENT</span>" if is_event else "<span class='badge-lowcost'>🏥 PERMANENT SAFETY-NET CLINIC</span>"

st.markdown(f"""
<div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 18px; padding: 16px; margin-bottom: 14px;">
    <div style="margin-bottom: 8px;">{cost_badge} {type_badge}</div>
    <div class="cz-title" style="font-size: 24px; margin: 6px 0 6px 0;">{title}</div>
    <div style="font-size: 0.95rem; color: #475569; margin-bottom: 12px;">
        📍 <strong>{escape(full_addr)}</strong> • <span style="color:#2563EB; font-weight:600;">{dist} miles from {escape(str(user_loc))}</span>
    </div>
    <div style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center;">
        <span class="score-badge" style="font-size: 0.95rem;">
            ⭐ Care Access Score: <strong>{score}/100</strong>
        </span>
        <span class="trust-pill">
            🛡️ Uninsured Acceptance: {escape(str(record.get('uninsured_acceptance') or 'All Welcome'))}
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# Main actions: directions first, then call / calendar / take the info along
maps_url = get_directions_url(full_addr, record.get("latitude"), record.get("longitude"))
st.link_button("Get directions", maps_url, icon=":material/directions:", type="primary", width="stretch")

act1, act2 = st.container(key="row_detail_actions").columns(2)
with act1:
    phone_num = record.get("phone", "")
    if phone_num:
        clean_phone = phone_num.replace("(", "").replace(")", "").replace(" ", "").replace("-", "")
        st.link_button("Call", f"tel:{clean_phone}", icon=":material/call:", width="stretch")
    else:
        st.button("No phone listed", disabled=True, width="stretch")

with act2:
    # Add to Calendar (.ics download)
    ics_data = generate_ics_calendar(record)
    file_name = f"careatzero_{record.get('id')}.ics"
    st.download_button(
        label="Add to calendar",
        data=ics_data,
        file_name=file_name,
        mime="text/calendar",
        icon=":material/calendar_add_on:",
        width="stretch"
    )

# Take the details along (no account needed): download or copy to text someone
referral_text = generate_shareable_referral_text(record, score, reasons)
st.download_button(
    label="Download info",
    data=referral_text,
    file_name=f"referral_{record.get('id')}.txt",
    mime="text/plain",
    icon=":material/download:",
    width="stretch"
)
with st.expander("Copy this info to text or share"):
    st.code(referral_text, language="text", wrap_lines=True)  # wraps on phones instead of scrolling sideways

st.markdown("---")

# Two Column Detailed Information
left_col, right_col = st.columns([1.6, 1.4])

with left_col:
    # 1. What to Bring & Readiness Checklist
    st.subheader("What to bring")
    st.markdown("*Review and prepare these items before your visit:*")

    docs = record.get("documents_required", [])
    if not docs or "None" in docs[0]:
        st.success("✅ **No ID or income documentation required** for this care event/clinic! (Bring a list of any current prescription medications if taking them).")
    else:
        for doc in docs:
            st.checkbox(f"**{doc}**", key=f"chk_{doc}")

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    # 2. Timing & Appointment Policy
    st.subheader("When to go")
    if is_event:
        st.markdown(f"""
        - **Dates:** {format_event_dates(record.get('date_start'), record.get('date_end'))}
        - **Hours:** {record.get('time_details')}
        - **Intake Rule:** {record.get('appointment_rule')}
        - **Organizer:** {record.get('organizer_name')}
        """)
    else:
        st.markdown(f"""
        - **Operating Hours:** {record.get('hours_summary')}
        - **Appointment Rule:** {record.get('appointment_rule')}
        - **Facility type:** {FACILITY_LABELS.get(record.get('type') or '', (record.get('type') or 'Clinic').replace('_', ' ').title())}
        """)

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    # 3. Services Offered
    st.subheader("Services")
    services = record.get("services", [])
    st.markdown(" ".join(f"<span class='trust-pill'>{escape(s)}</span>" for s in services), unsafe_allow_html=True)

    if record.get("notes"):
        st.markdown(f"**Special Notes:** {record.get('notes')}")

with right_col:
    # 4. Care Access Score Breakdown
    st.subheader("Care Access Score")
    st.markdown(f"Care Access Score: **{score}/100** *(Transparent 100-Point Model)*")

    # Score breakdown metric cards
    for signal, pts in breakdown.items():
        max_pts = int(re.search(r"\((\d+)%\)", signal).group(1))  # e.g. "Cost Fit (35%)" -> 35 points max
        st.progress(min(1.0, pts / max_pts), text=f"{signal}: **{pts} of {max_pts} pts**")

    st.markdown("**Why this matches:**")
    for r in reasons:
        st.markdown("- " + r.replace("$", "\\$"))  # "\$" keeps "$0-$15" from turning into a math formula

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

    # 5. Verified Source & Freshness
    st.subheader("Where this comes from")
    source_name = record.get("source_name", "Official Directory Feed")
    source_url = record.get("source_url", "https://careatzero.org")
    checked_date, checked_time = checked_parts(record.get("last_checked"))
    if record.get("is_live"):
        status_label, status_color = "LIVE — from the official source", "green"
    elif "saved copy" in source_name:
        status_label, status_color = "Saved copy — the live source couldn't be reached", "orange"
    elif "manually verified" in source_name:
        status_label, status_color = "Verified by hand from the organizer", "orange"
    else:
        status_label = (record.get("source_status") or "active").upper()
        status_color = "green" if status_label == "ACTIVE" else "orange"
    website = record.get("website") or source_url
    if not str(website).startswith(("http://", "https://")):
        website = f"https://{website}" if website and "." in str(website) and ":" not in str(website) else source_url
    source_name = escape(source_name)

    st.markdown(f"""
    - **Primary Source:** [{source_name}]({source_url})
    - **Last checked (date):** {checked_date}
    - **Last checked (time):** {f"{checked_time} ({timezone_label()}, the time zone of your search area)" if checked_time else "not recorded"}
    - **Data status:** <span style="color: {status_color}; font-weight: 600;">{status_label}</span>
    - **Website:** [{website}]({website})
    """, unsafe_allow_html=True)




