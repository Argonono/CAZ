import os
import sys
import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_search_location_preservation_from_home_to_find_page():
    """
    Test that entering a custom ZIP like 27514 on the home page
    is preserved on the Find Free Care page and never clobbered by detected ZIP.
    """
    # 1. Run app.py
    app_path = os.path.join(PROJECT_ROOT, "app.py")
    at = AppTest.from_file(app_path)
    at.run()
    assert len(at.text_input) > 0, "No text_input found on home page"

    # 2. Simulate user typing 27514 and submitting
    at.text_input[0].input("27514")
    submit_btn = [b for b in at.button if b.key == "home_find_care_submit_btn"][0]
    submit_btn.click().run()

    assert at.session_state["search_loc"] == "27514", (
        f"Expected search_loc 27514, got {at.session_state.get('search_loc')}"
    )

    # 3. Transition to Find Free Care page with that session state
    find_page_path = os.path.join(PROJECT_ROOT, "pages", "1_🔍_Find_Free_Care.py")
    at_find = AppTest.from_file(find_page_path)
    for k, v in at.session_state.to_dict().items():
        at_find.session_state[k] = v

    at_find.run()
    assert at_find.session_state["search_loc"] == "27514", (
        f"search_loc was overwritten to {at_find.session_state.get('search_loc')}"
    )

    # Find the location text input on Find page
    loc_inputs = [w for w in at_find.text_input if w.key == "find_care_loc_input" or "Location" in w.label]
    assert len(loc_inputs) > 0, "No location input on Find page"
    assert loc_inputs[0].value == "27514", f"Expected input value 27514, got {loc_inputs[0].value}"


def test_changing_zip_on_find_page_updates_search():
    """
    Test that editing the ZIP code directly on the Find Free Care page
    updates the search location and does not revert to detected zip.
    """
    find_page_path = os.path.join(PROJECT_ROOT, "pages", "1_🔍_Find_Free_Care.py")
    at_find = AppTest.from_file(find_page_path)
    at_find.session_state["search_loc"] = "27514"
    at_find.session_state["selected_service"] = "Medical"
    at_find.run()

    loc_inputs = [w for w in at_find.text_input if w.key == "find_care_loc_input" or "Location" in w.label]
    assert len(loc_inputs) > 0
    assert loc_inputs[0].value == "27514"

    # Change to 27601
    loc_inputs[0].input("27601").run()
    assert at_find.session_state["search_loc"] == "27601"
