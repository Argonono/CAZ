import os
import sys
import pytest
import folium

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def test_map_uses_open_street_map_tiles():
    """Verify that the Find Free Care page and folium map use OpenStreetMap without requiring an API key."""
    find_page_path = os.path.join(PROJECT_ROOT, "pages", "1_🔍_Find_Free_Care.py")
    with open(find_page_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Must not contain CartoDB positron which triggers 'API key required'
    assert "CartoDB positron" not in content, "Found obsolete CartoDB positron tiles which require an API key"
    assert "OpenStreetMap" in content, "Map should configure standard OpenStreetMap tiles"


def test_folium_map_generation_without_warnings():
    """Verify folium Map generates tile layers for OpenStreetMap without API key warnings."""
    import warnings
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        m = folium.Map(location=[35.9132, -79.0558], zoom_start=10, tiles="OpenStreetMap")
        
        # Verify no UserWarning about CartoDB or API keys
        carto_warnings = [
            w for w in recorded_warnings 
            if "API key" in str(w.message).lower() or "cartodb" in str(w.message).lower()
        ]
        assert len(carto_warnings) == 0, f"Unexpected API key warning: {carto_warnings}"

    # Verify OpenStreetMap tile URL is present in the rendered leaflet HTML
    html_repr = m._repr_html_()
    assert "tile.openstreetmap.org" in html_repr
    assert "carto.com" not in html_repr


def test_map_markers_and_popup_generation():
    """Verify provider markers and popups render properly on the OpenStreetMap basemap."""
    m = folium.Map(location=[35.9132, -79.0558], zoom_start=10, tiles="OpenStreetMap")
    
    # User marker
    folium.Marker(
        [35.9132, -79.0558],
        popup="Your Location: 27514",
        tooltip="Your Location",
        icon=folium.Icon(color="red", icon="user", prefix="fa")
    ).add_to(m)

    # Provider marker
    popup_html = "<b>Free Health Clinic</b><br/>Cost: <b>Free</b><br/>Score: <b>95/100</b>"
    folium.Marker(
        [35.95, -79.02],
        popup=folium.Popup(popup_html, max_width=250),
        tooltip="[Free] Free Health Clinic (3.2 mi)",
        icon=folium.Icon(color="green", icon="plus-square", prefix="fa")
    ).add_to(m)

    rendered = m._repr_html_()
    assert "tile.openstreetmap.org" in rendered
    assert "Free Health Clinic" in rendered
    assert "carto.com" not in rendered

