"""
Mobile app layout tests (Streamlit AppTest, runs each screen headless).

Checks the redesigned screens: logo bar and 911/988 on Home, Medical as the
default care type, the bottom tab bar on every screen, the Help screen,
and Download info replacing Save on the clinic detail screen.
"""
import os
import sys

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PAGES = {
    "home": os.path.join(PROJECT_ROOT, "app.py"),
    "find": os.path.join(PROJECT_ROOT, "pages", "1_🔍_Find_Free_Care.py"),
    "details": os.path.join(PROJECT_ROOT, "pages", "2_📋_Care_Details.py"),
    "help": os.path.join(PROJECT_ROOT, "pages", "3_📞_Get_Help.py"),
    "about": os.path.join(PROJECT_ROOT, "pages", "4_ℹ️_About_&_Safety.py"),
}
TABS = ["Home", "Find", "Help", "About"]


def run_page(name, **state):
    at = AppTest.from_file(PAGES[name], default_timeout=30)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, f"{name} raised: {at.exception}"
    return at


def page_text(at):
    return " ".join(m.value for m in at.markdown)


def test_every_screen_has_the_bottom_tab_bar():
    for name in PAGES:
        at = run_page(name, search_loc="27514")
        labels = [b.label for b in at.button]
        for tab in TABS:
            assert tab in labels, f"'{tab}' tab missing on {name}"
        assert "Saved" not in labels, "Saved stays hidden until there are user accounts"


def test_home_shows_logo_bar_tagline_and_emergency_numbers():
    at = run_page("home", search_loc="27514")
    text = page_text(at)
    assert "cz-brand" in text
    assert "Free &amp; low-cost care. Know where to go." in text
    assert "tel:911" in text and "tel:988" in text


def test_home_defaults_to_medical_and_this_week():
    at = run_page("home", search_loc="27514")
    medical = [b for b in at.button if b.key == "care_card_Medical"][0]
    assert medical.proto.type == "primary", "Medical should be selected by default"
    timing = [sc for sc in at.segmented_control if sc.key == "home_timing"][0]
    assert timing.value == "This Week"
    assert at.text_input[0].label == "Where are you? (ZIP code or city)"


def test_choosing_a_care_card_carries_into_the_search():
    at = run_page("home", search_loc="27514")
    [b for b in at.button if b.key == "care_card_Dental"][0].click().run()
    assert at.session_state["home_service"] == "Dental"
    [b for b in at.button if b.key == "home_find_care_submit_btn"][0].click().run()
    assert at.session_state["selected_service"] == "Dental"
    assert at.session_state["search_timing"] == "This Week"


def test_find_defaults_to_medical_and_shows_results_with_actions():
    at = run_page("find", search_loc="27514")
    service = [sb for sb in at.selectbox if sb.label == "Type of care"][0]
    assert service.value == "Medical"
    labels = [b.label for b in at.button]
    assert "Details" in labels, "Each result should have a Details button"


def test_help_screen_has_call_buttons():
    at = run_page("help")
    text = page_text(at)
    assert "Get help now" in text
    assert 'href="tel:911"' in text and 'href="tel:988"' in text
    assert any("Find a free clinic" in b.label for b in at.button)


def test_detail_screen_offers_download_info_instead_of_save():
    at = run_page("details", search_loc="27514", selected_care_id="site_shac_01", selected_care_type="site")
    assert not [b for b in at.button if "Save" in b.label]
    assert "Copy this info to text or share" in [e.label for e in at.expander]
    assert len(at.code) == 1, "The shareable summary should be on the detail screen"


def test_about_privacy_no_longer_mentions_saved_bookmarks():
    at = run_page("about")
    text = page_text(at)
    assert "Download info" in text
    assert "Local Bookmarks" not in text
