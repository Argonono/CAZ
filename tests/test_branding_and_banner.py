import os
import sys
import base64
import pytest
from PIL import Image

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.styles import LOGO_PATH, MARK_PATH, WORDMARK_PATH, TAGLINE, render_brand_header


def test_logo_asset_integrity():
    """Verify that the brand logo file exists and generates base64."""
    assert os.path.exists(LOGO_PATH)
    with open(LOGO_PATH, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_brand_mark_and_wordmark_assets():
    """Verify the logo mark and wordmark used in the Home logo bar exist and are transparent PNGs."""
    for path in (MARK_PATH, WORDMARK_PATH):
        assert os.path.exists(path), f"Missing brand asset: {path}"
        with Image.open(path) as img:
            assert img.format == "PNG"
            assert img.mode == "RGBA", "Brand images should have a transparent background"


def test_tagline_is_one_honest_line():
    """The tagline promises free AND low-cost care (results include sliding-scale clinics)."""
    assert TAGLINE == "Free & low-cost care. Know where to go."
    assert len(TAGLINE) <= 45, "Tagline should fit on one line on a phone"


def test_brand_header_rendering(monkeypatch):
    """Verify render_brand_header produces the logo bar: mark, wordmark and tagline."""
    rendered_markdowns = []

    def mock_markdown(body, unsafe_allow_html=False):
        rendered_markdowns.append(body)

    import streamlit as st
    monkeypatch.setattr(st, "markdown", mock_markdown)

    render_brand_header()
    assert len(rendered_markdowns) == 1
    content = rendered_markdowns[0]

    assert "cz-brand" in content
    assert "Free &amp; low-cost care. Know where to go." in content
    assert content.count("data:image/png;base64,") == 2, "Expected the mark and the wordmark images"
    assert 'alt="CareAtZero"' in content


def test_brand_header_fallback_rendering(monkeypatch):
    """Verify the logo bar falls back to text when the brand images are unavailable."""
    rendered_markdowns = []

    def mock_markdown(body, unsafe_allow_html=False):
        rendered_markdowns.append(body)

    import streamlit as st
    monkeypatch.setattr(st, "markdown", mock_markdown)
    import utils.styles as styles_mod
    monkeypatch.setattr(styles_mod, "_file_base64", lambda path: "")

    render_brand_header()
    assert len(rendered_markdowns) == 1
    content = rendered_markdowns[0]

    assert "cz-brand" in content
    assert "Free &amp; low-cost care. Know where to go." in content
    assert "CareAt" in content
    assert "Zero" in content
    assert "data:image/png;base64," not in content
