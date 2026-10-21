import streamlit as st
import os
import sys

# Ensure project root is strictly first in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not sys.path or sys.path[0] != PROJECT_ROOT:
    if PROJECT_ROOT in sys.path:
        sys.path.remove(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)

from live.sources import load_live_data
from utils.timezones import use_timezone_of
from utils.dates import format_checked, timezone_label
from utils.geo import geocode_location
from utils.styles import inject_custom_css, render_header, LOGO_PATH


st.set_page_config(
    page_title="About & Trust Principles | CareAtZero",
    page_icon=LOGO_PATH,
    layout="wide"
)

inject_custom_css()
render_header("about")

st.markdown('<div class="cz-title">About CareAtZero</div>'
            '<div class="cz-sub">Our mission, sources, scoring and privacy.</div>', unsafe_allow_html=True)

t1, t2, t3, t4 = st.tabs(["Mission", "Scoring", "Sources", "Privacy"])

with t1:
    st.subheader("Our Mission")
    st.markdown("""
    **CareAtZero** is a free, mobile-first web application designed to help uninsured and low-income individuals and families find **genuinely free or very-low-cost medical, dental, vision, and behavioral healthcare** they can realistically access soon.

    ### The Problem We Solve
    Free and safety-net healthcare exists, but the information is fragmented across federal directories, charitable clinic networks, mobile clinic calendars, and local public health feeds.

    An uninsured person often faces:
    - Calling clinics only to find out they are not free or require insurance.
    - Missing time-sensitive pop-up events (like RAM or mobile dental buses).
    - Arriving without required income or residency documents.
    - Searching directories that rank by distance rather than the realistic time to care.

    **CareAtZero bridges this gap** by normalizing safety-net data, verifying cost tiers, scoring realistic accessibility, and giving patients a clear document checklist before they travel.
    """)

with t2:
    st.subheader("Care Access Score Methodology")
    st.markdown("""
    Rather than relying on opaque AI or simple distance sorting, CareAtZero uses an open, transparent **100-Point Care Access Scoring Model**:
    """)

    # One card per signal (not a table), so it fits a phone screen without sideways scrolling.
    # "&#36;" is a dollar sign: a plain "$...$" pair would be shown as a math formula.
    signals = [
        ("Cost fit", 35, "<b>Free (&#36;0)</b>: 35 points. <b>Very low cost (&#36;5–&#36;25)</b>: 25. "
                         "<b>Sliding scale</b>: 18–20, depending on income."),
        ("How soon you can go", 25, "Pop-up event <b>today</b>: 25. <b>This week</b>: 22–24. "
                                    "Walk-in clinics: 20–24. Same-day appointments: 18."),
        ("Right type of care", 15, "An exact match for the care you picked (medical, dental, vision or mental health): 15."),
        ("Easy to get in", 10, "No ID or income papers needed: 10. Open to all uninsured people: 9. "
                               "Income check for the sliding scale: 8."),
        ("Distance", 10, "Under 5 miles: 10. 5–12 mi: 8. 12–25 mi: 6. 25–50 mi: 4. Over 50 mi: 2."),
        ("Fresh information", 5, "Checked from an official source in the last 60 days: 5. Older: fewer points."),
    ]
    for name, points, how in signals:
        st.markdown(f"""
<div class="care-card" style="padding:14px 16px; margin-bottom:10px;">
  <div style="display:flex; justify-content:space-between; gap:8px; align-items:baseline;">
    <strong style="color:#0E2A5C; font-size:1.02rem;">{name}</strong>
    <span class="score-badge" style="white-space:nowrap;">{points} pts</span>
  </div>
  <div class="card-meta" style="margin-top:6px;">{how}</div>
</div>""", unsafe_allow_html=True)

    st.info("💡 **Strict Business Rule:** A provider is **never labeled Free** unless the underlying source explicitly verifies a \\$0 patient charge for that service.")

with t3:
    st.subheader("Live data sources")
    st.markdown("Every search uses records from these official public sources. The app fetches them "
                "automatically, keeps them in memory, and refreshes them in the background every 6 hours, "
                "so searches are instant:")

    search_loc = st.session_state.get("search_loc")
    a_lat = a_lon = None
    place = geocode_location(search_loc) if search_loc else None
    if place:
        a_lat, a_lon, _ = place
        use_timezone_of(a_lat, a_lon)
    with st.spinner("Checking the live sources..."):
        live = load_live_data(a_lat, a_lon)
    if not place:
        st.caption("SAMHSA's mental health listings are searched around your location, "
                   "so their status appears after you search a ZIP code.")

    # One card per source (not a table), so it fits a phone screen without sideways scrolling
    zone = timezone_label()
    for src in live.statuses:
        if src.ok:
            status, color = f"Live · {src.count} records", "#0A7C74"
        elif src.saved_copy_from:
            status, color = f"Saved copy · {src.count} records (live site unavailable)", "#B45309"
        else:
            status, color = "Unavailable right now", "#B45309"
        when = src.checked or src.saved_copy_from
        checked = f"{format_checked(when)} ({zone})" if when else "not yet"
        st.markdown(f"""
<div class="care-card" style="padding:14px 16px; margin-bottom:10px;">
  <a href="{src.url}" target="_blank" style="font-weight:700; color:#0E2A5C; font-size:1.02rem;">{src.name}</a>
  <div class="card-meta" style="margin-top:4px;">{src.provides}</div>
  <div class="card-meta"><span style="color:{color}; font-weight:600;">{status}</span></div>
  <div class="source-meta">Checked: {checked}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("""
**Also used**
- **U.S. Census Bureau ZIP code list**, to place any U.S. ZIP code on the map.

**If a source is down**, the app keeps showing the last copy it fetched, with that copy's real date and time.
If the app has just restarted and a source can't be reached, it uses a saved copy of that source kept with the
app, labeled "saved copy" with its date. It never makes up data, and it never shows an old copy as live.
    """)
    down = [s for s in live.statuses if not s.ok]
    if down:
        with st.expander("Why is a source unavailable?"):
            for s in down:
                st.markdown(f"- **{s.name}:** {s.error or 'no answer'}")
    if live.using_saved_directory:
        st.warning("Right now the live clinic sources can't be reached, so searches use the saved directory.")

with t4:
    st.subheader("Privacy, Safety & Medical Disclaimers")
    st.markdown("""
    ### 🔒 Privacy Guarantee
    - **No Protected Health Information (PHI) Stored:** CareAtZero never asks for or stores your medical history, diagnosis, Social Security Number, or payment info.
    - **No User Account Required:** Search freely without creating a login.
    - **Nothing Saved About You:** Searches are not stored. To keep a clinic's details, use **Download info** or copy the text on its detail screen. It stays on your phone, not on a server.

    ### ⚠️ Medical Advice & Emergency Disclaimer
    CareAtZero is an informational resource navigation directory and **does not provide medical diagnosis, treatment advice, or triage**. 

    - **Life-Threatening Emergency:** Call **911** immediately or go to the nearest emergency department.
    - **Suicide & Crisis Lifeline:** Call or text **988** (Free, confidential 24/7 mental health support).
    """)



