import streamlit as st
import os
import sys

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import base64

LOGO_PATH = os.path.join(PROJECT_ROOT, "assets", "logo.png")
MARK_PATH = os.path.join(PROJECT_ROOT, "assets", "brand_mark.png")          # the "CO" mark, transparent
WORDMARK_PATH = os.path.join(PROJECT_ROOT, "assets", "brand_wordmark.png")  # "CareAtZero" in the logo's lettering

# One line under the logo. "Free & low-cost" because results include sliding-scale
# clinics, and the app only labels something Free when the source says so.
TAGLINE = "Free & low-cost care. Know where to go."

# Bottom tab bar: (label, Material icon, page key, page file)
NAV_TABS = [
    ("Home", ":material/home:", "home", "app.py"),
    ("Find", ":material/search:", "find_care", "pages/1_🔍_Find_Free_Care.py"),
    ("Help", ":material/call:", "help", "pages/3_📞_Get_Help.py"),
    ("About", ":material/info:", "about", "pages/4_ℹ️_About_&_Safety.py"),
]


def _file_base64(path: str) -> str:
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return ""
    return ""


def inject_custom_css():
    """
    Mobile app styling. The whole app is a phone-width column (so it also looks like
    a phone app on a laptop), Streamlit's own menus are hidden, and a tab bar is
    pinned to the bottom.

    Layout rule: columns always stack into one column, like on a phone. To keep a
    row of buttons side by side, put it in st.container(key="row_...").
    """
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap');
    :root {
        --navy: #0E2A5C; --blue: #0B5FD6; --blue-50: #E6F0FD; --teal: #0A7C74; --teal-50: #E2F4F1;
        --red: #B42318; --red-50: #FDECEC; --ink: #0E2A5C; --ink-soft: #3D4B61; --ink-faint: #55637A;
        --line: #E2E8F0; --bg: #F4F7FA;
    }
    html, body, [class*="st-"], button, input, textarea, select {
        font-family: 'Figtree', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-tap-highlight-color: transparent;
    }
    .material-symbols-rounded, [data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }

    /* ---- phone-width app column; Streamlit's own chrome hidden ---- */
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
    #MainMenu, footer, .stDeployButton, [class*="viewerBadge"],
    section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
    button[data-testid="stSidebarCollapseButton"] { display: none !important; }
    [data-testid="stAppViewContainer"] { background: #DDE4EC; }
    .block-container, [data-testid="stMainBlockContainer"] {
        max-width: 440px !important; min-height: 100vh; background: var(--bg);
        padding: 14px 16px 110px !important; box-shadow: 0 0 40px rgba(14,42,92,0.12);
        flex: 0 0 auto !important;  /* don't shrink to screen height; keeps the end of the page clear of the tab bar */
    }
    @media (max-width: 480px) {
        [data-testid="stAppViewContainer"] { background: var(--bg); }
        .block-container, [data-testid="stMainBlockContainer"] { box-shadow: none; }
    }
    h1, h2, h3, h4 { color: var(--ink); letter-spacing: -0.01em; }
    h3 { font-size: 20px !important; font-weight: 800 !important; }
    h4 { font-size: 16px !important; font-weight: 800 !important; }
    [data-testid="stHeaderActionElements"] { display: none !important; }

    /* ---- every row of columns stacks, like on a phone ... ---- */
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    [data-testid="stColumn"] { flex: 1 1 100% !important; min-width: 100% !important; width: 100% !important; }
    /* ... except rows put in st.container(key="row_...") */
    [class*="st-key-row"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important; }
    [class*="st-key-row"] [data-testid="stColumn"] { flex: 1 1 0 !important; min-width: 0 !important; width: auto !important; }

    /* ---- brand bar (Home) ---- */
    .cz-brand { display: flex; align-items: center; gap: 10px; padding: 2px 0 12px; }
    .cz-brand-mark { height: 46px; width: auto; }
    .cz-brand-text { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
    .cz-brand-word { height: 23px; width: auto; align-self: flex-start; }
    .cz-brand-name { font-size: 24px; font-weight: 800; color: var(--navy); line-height: 1; }
    .cz-brand-name span { color: var(--teal); }
    .cz-tagline { font-size: 12.5px; font-weight: 600; color: var(--ink-soft); white-space: nowrap; }
    .cz-title { font-size: 28px; font-weight: 800; line-height: 1.12; letter-spacing: -0.5px; margin: 4px 0 4px; color: var(--ink); }
    .cz-sub { font-size: 15px; color: var(--ink-faint); margin-bottom: 10px; }

    /* ---- 911 / 988 quick-call buttons ---- */
    .emergency-banner { display: flex; gap: 8px; margin: 4px 0 14px; }
    .emergency-banner a { flex: 1; text-align: center; text-decoration: none !important; border-radius: 12px;
                          padding: 10px 6px; font-size: 14px; font-weight: 800; }
    .cz-em-red { background: var(--red-50); color: var(--red) !important; }
    .cz-em-blue { background: var(--blue-50); color: #0A3D91 !important; }

    /* ---- bottom tab bar ---- */
    .st-key-cz_nav {
        position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); z-index: 1000;
        width: 100%; max-width: 440px; background: #FFFFFF; border-top: 1px solid var(--line);
        padding: 6px 6px calc(14px + env(safe-area-inset-bottom, 0px)); box-sizing: border-box;
    }
    .st-key-cz_nav [data-testid="stHorizontalBlock"] { gap: 0 !important; }
    .st-key-cz_nav button {
        border: none !important; background: transparent !important; color: var(--ink-faint) !important;
        min-height: 54px !important; padding: 4px 0 !important; box-shadow: none !important;
    }
    .st-key-cz_nav button p { font-size: 12px !important; font-weight: 600; }
    .st-key-cz_nav [data-testid="stIconMaterial"] { font-size: 24px !important; }

    /* ---- care-type cards (2x2) ---- */
    [class*="st-key-svc_"] button {
        min-height: 78px; justify-content: flex-start !important; text-align: left; border-radius: 14px !important;
        background: #FFFFFF !important; border: 1px solid var(--line) !important; color: var(--ink) !important;
        padding: 8px 12px !important;
    }
    [class*="st-key-svc_"] button[data-testid="stBaseButton-primary"] {
        background: var(--teal-50) !important; border: 2px solid var(--teal) !important;
    }
    [class*="st-key-svc_"] button p { font-size: 15px !important; font-weight: 700 !important; text-align: left; line-height: 1.25; }
    [class*="st-key-svc_"] [data-testid="stIconMaterial"] { color: var(--teal) !important; font-size: 24px !important; }

    /* ---- buttons and inputs ---- */
    .stButton button, .stDownloadButton button, .stLinkButton a, .stFormSubmitButton button {
        border-radius: 12px !important; min-height: 44px !important; font-weight: 700 !important;
    }
    .stFormSubmitButton button { min-height: 54px !important; box-shadow: 0 6px 16px rgba(10,124,116,0.25); }
    .stFormSubmitButton button p { font-size: 17px !important; font-weight: 800 !important; }
    [data-testid="stTextInput"] input { font-size: 17px; font-weight: 600; }
    div[data-testid="stForm"] { border: none; padding: 0; }

    /* ---- badges ---- */
    .badge-free, .badge-lowcost, .badge-sliding, .badge-event {
        display: inline-block; padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 800;
        letter-spacing: 0.02em; text-transform: uppercase; margin: 0 4px 4px 0;
    }
    .badge-free { background: #E2F4F1; color: #075E57; }
    .badge-lowcost { background: #E6F0FD; color: #0A4BAA; }
    .badge-sliding { background: #FFF2DE; color: #8A4B00; }
    .badge-event { background: #FEF3C7; color: #92400E; }

    /* ---- result and event cards ---- */
    .care-card {
        background: #FFFFFF; border: 1px solid var(--line); border-radius: 18px;
        padding: 14px 16px; margin-bottom: 8px;
    }
    .care-card-header { display: flex; flex-direction: column; gap: 6px; margin-bottom: 6px; }
    .care-card-title { font-size: 18px; font-weight: 800; color: var(--ink); margin: 0; line-height: 1.25; }
    .score-badge {
        background: var(--blue-50); padding: 4px 10px; border-radius: 8px; font-size: 13px;
        font-weight: 700; color: #0A4BAA; display: inline-flex; align-items: center; gap: 4px; align-self: flex-start;
    }
    .card-meta { font-size: 14px; color: var(--ink-soft); margin: 4px 0; line-height: 1.4; }
    .reasons-box {
        background: var(--bg); padding: 8px 12px; border-radius: 10px; margin-top: 8px;
        font-size: 13.5px; color: var(--ink-soft);
    }
    .reasons-box ul { margin: 3px 0 0 0; padding-left: 16px; }
    .source-meta { font-size: 12.5px; color: var(--ink-faint); margin-top: 8px; }
    .trust-pill {
        display: inline-flex; align-items: center; gap: 5px; background: var(--bg); color: var(--ink-soft);
        padding: 4px 10px; border-radius: 8px; font-size: 13px; font-weight: 600;
    }

    /* ---- Help screen ---- */
    .cz-help { border-radius: 18px; padding: 16px; margin-bottom: 12px; }
    .cz-help h4 { margin: 0 0 4px !important; padding: 0 !important; }
    .cz-help p { margin: 0 0 12px; font-size: 14px; }
    .cz-help a { display: block; text-align: center; text-decoration: none !important; border-radius: 14px;
                 padding: 15px; font-size: 18px; font-weight: 800; color: #FFFFFF !important; }
    </style>
    """, unsafe_allow_html=True)


def render_brand_header():
    """Home-screen logo bar: the CO mark and CareAtZero lettering from the logo, tagline underneath."""
    mark_b64 = _file_base64(MARK_PATH)
    word_b64 = _file_base64(WORDMARK_PATH)
    mark_html = (f'<img class="cz-brand-mark" src="data:image/png;base64,{mark_b64}" alt="">'
                 if mark_b64 else "")
    word_html = (f'<img class="cz-brand-word" src="data:image/png;base64,{word_b64}" alt="CareAtZero">'
                 if word_b64 else '<div class="cz-brand-name">CareAt<span>Zero</span></div>')
    st.markdown(f"""
    <div class="cz-brand">
        {mark_html}
        <div class="cz-brand-text">
            {word_html}
            <div class="cz-tagline">{TAGLINE.replace('&', '&amp;')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_emergency_banner():
    """911 and 988 as two tap-to-call buttons (they dial directly on a phone)."""
    st.markdown("""
    <div class="emergency-banner">
        <a class="cz-em-red" href="tel:911">Emergency · 911</a>
        <a class="cz-em-blue" href="tel:988">Crisis line · 988</a>
    </div>
    """, unsafe_allow_html=True)


def render_header(active_page: str = "home"):
    """
    Renders the shared parts of every page:
    - Home: the logo bar and the 911 / 988 buttons
    - Every page: the bottom tab bar (Home, Find, Help, About)
    Other pages start with their own title, the way most phone apps do.
    """
    if active_page == "home":
        render_brand_header()
    render_bottom_nav(active_page)


def render_bottom_nav(active_page: str = "home"):
    """
    Fixed tab bar at the bottom of the screen. The Detail screen belongs to Find,
    so Find stays highlighted there. (Saved care is hidden until there are user accounts.)
    """
    active = "find_care" if active_page == "details" else active_page
    st.markdown(f"<style>.st-key-nav_{active} button {{ color: var(--teal) !important; }}"
                f".st-key-nav_{active} button p {{ font-weight: 800 !important; }}</style>",
                unsafe_allow_html=True)
    with st.container(key="cz_nav"):
        with st.container(key="row_nav"):
            cols = st.columns(len(NAV_TABS))
            for col, (label, icon, page_key, page_file) in zip(cols, NAV_TABS):
                with col:
                    if st.button(label, icon=icon, key=f"nav_{page_key}", type="tertiary", width="stretch"):
                        if page_key != active_page:
                            st.switch_page(page_file)
