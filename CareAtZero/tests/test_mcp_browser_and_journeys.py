import os
import sys
import json
import pytest
import subprocess

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from mcp_browser_server import handle_request, tool_test_health, tool_simulate_user_journey, tool_browser_navigate


def test_mcp_initialize_and_tools_list():
    """Verify MCP protocol initialization and tool listing."""
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    init_resp = handle_request(init_req)
    assert init_resp["result"]["serverInfo"]["name"] == "careatzero-browser-mcp"

    list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    list_resp = handle_request(list_req)
    tools = [t["name"] for t in list_resp["result"]["tools"]]
    assert "browser_navigate" in tools
    assert "browser_test_health" in tools
    assert "browser_simulate_journey" in tools


def test_mcp_browser_health_endpoint():
    """Verify Streamlit web server response via MCP tool."""
    health_result = tool_test_health("http://localhost:8501")
    assert health_result["base_url"] == "http://localhost:8501"
    if health_result["endpoints"]["/"].get("status") != 200:
        pytest.skip("the app isn't running on localhost:8501 (start it with: python -m streamlit run app.py)")
    # Streamlit root should respond
    assert "/" in health_result["endpoints"]
    assert health_result["endpoints"]["/"]["status"] == 200


def test_mcp_persona_1_uninsured_adult_dental():
    """
    Persona 1 Test (Uninsured Adult):
    Needs urgent dental care in Chapel Hill / Durham (27514), uninsured, this week.
    Expected: Finds free/low-cost dental options (e.g. SHAC Free Dental / RAM / Piedmont Dental).
    """
    res = tool_simulate_user_journey(
        persona="Uninsured Adult",
        service="Dental",
        location="27514",
        timing="This Week"
    )
    assert res["journey_success"] is True
    assert res["total_matches_found"] >= 5
    top = res["top_ranked_match"]
    assert top is not None
    assert top["care_access_score"] >= 75
    assert top["cost_class"] in ["Free", "Sliding Scale", "Very Low Cost"]
    assert len(top["reasons"]) > 0


def test_mcp_persona_2_low_income_parent_medical():
    """
    Persona 2 Test (Low-Income Parent):
    Needs same-day / weekly primary medical care for family near Raleigh (27601).
    Expected: Matches Advance Community Health, Alliance Medical Ministry, or Urban Ministries.
    """
    res = tool_simulate_user_journey(
        persona="Low-Income Parent",
        service="Medical",
        location="27601",
        timing="Today"
    )
    assert res["journey_success"] is True
    assert res["total_matches_found"] >= 10
    top = res["top_ranked_match"]
    assert top["care_access_score"] >= 80


def test_mcp_persona_3_counselor_mobile_vision_fair():
    """
    Persona 3 Test (School Counselor / Social Worker):
    Looking for free vision / eyeglass pop-up event or mental health crisis support.
    Expected: Surfaces upcoming Triangle Vision Initiative Pop-up / Alliance Crisis Center.
    """
    res_vision = tool_simulate_user_journey(
        persona="School Counselor",
        service="Vision",
        location="27514",
        timing="Flexible"
    )
    assert res_vision["journey_success"] is True
    top_vision = res_vision["top_ranked_match"]
    assert top_vision["cost_class"] in ["Free", "Very Low Cost"]

    res_bh = tool_simulate_user_journey(
        persona="Community Navigator",
        service="Behavioral Health",
        location="27610",
        timing="Today"
    )
    assert res_bh["journey_success"] is True
    top_bh = res_bh["top_ranked_match"]
    assert top_bh["care_access_score"] >= 80
