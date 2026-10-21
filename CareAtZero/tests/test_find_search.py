"""
Find screen: a Search button next to the ZIP box, a summary line that names every
active choice (it changes as soon as the results do, with no pop-up), and Reset filters.
"""
from test_mobile_ui import run_page


def summary(at):
    return next(m.value for m in at.markdown if " within " in m.value and " mi of " in m.value)


def test_search_button_next_to_zip_box():
    at = run_page("find", search_loc="27601")
    assert at.button(key="find_search_btn").label == "Search"


def test_new_zip_and_search_updates_the_summary_without_a_popup():
    at = run_page("find", search_loc="27601")
    at.text_input(key="find_care_loc_input").input("27514")
    at.button(key="find_search_btn").click().run()
    assert not at.exception
    assert "Chapel Hill" in summary(at)
    assert len(at.toast) == 0


def test_changing_a_filter_shows_in_the_summary():
    at = run_page("find", search_loc="27601")
    at.selectbox(key="find_cost").select("Free Only ($0 Fee)").run()
    assert "Free only" in summary(at) and "within 35 mi" in summary(at)
    assert len(at.toast) == 0


def test_reset_filters_goes_back_to_defaults():
    at = run_page("find", search_loc="27601")
    at.selectbox(key="find_cost").select("Free Only ($0 Fee)").run()
    at.slider(key="find_dist").set_value(10).run()
    at.button(key="find_reset_btn").click().run()
    assert at.selectbox(key="find_cost").value == "All Low-Cost & Free"
    assert at.slider(key="find_dist").value == 35
