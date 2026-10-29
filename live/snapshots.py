"""
Saved copies of the live sources, kept in the repo (data/snapshots/).

The app keeps live data in memory, which is wiped whenever the app restarts
(Streamlit Cloud puts idle apps to sleep). If a source can't be reached right
after a restart, the app shows its saved copy instead, always labeled
"saved copy" with the date it was saved, never as live data.

tools/check_live_sources.py refreshes these files from the real sources;
commit them so the deployed app has them. Each file holds the source's raw
download (exactly what the source sent), so it goes through the same parser
as live data.
"""
import json
import os
from typing import Any, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# CAREATZERO_SNAPSHOT_DIR lets the tests use their own folder
SNAPSHOT_DIR = os.environ.get("CAREATZERO_SNAPSHOT_DIR") or os.path.join(PROJECT_ROOT, "data", "snapshots")


def path_for(key: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{key}.json")


def save(key: str, raw: Any, saved_at: str, source_url: str = "") -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    path = path_for(key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"saved_at": saved_at, "source": source_url, "raw": raw}, f)
    return path


def load(key: str) -> Tuple[Optional[Any], str]:
    """(raw download, saved_at) for a source, or (None, "") if there is no saved copy."""
    try:
        with open(path_for(key), encoding="utf-8") as f:
            snap = json.load(f)
        return snap.get("raw"), snap.get("saved_at", "")
    except (OSError, ValueError):
        return None, ""
