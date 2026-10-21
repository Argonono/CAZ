"""
Shared test setup.

Several tests use the sample pop-up events in data/seed_data.py, which are dated
September 2026. Pinning "today" to 2026-09-16 keeps those tests about the app's
logic, not about what today's date happens to be. The app itself uses the real
date (see utils/dates.py).

CAREATZERO_OFFLINE=1 makes every live source act as unavailable, so the tests never
depend on outside websites and the app shows its saved directory (data/seed_data.py).
The live parsers are tested separately against saved files (tests/test_live_sources.py).
"""
import os

os.environ.setdefault("CAREATZERO_TODAY", "2026-09-16")
os.environ.setdefault("CAREATZERO_OFFLINE", "1")
# ...and without the saved copies in data/snapshots/, so "everything down" really is everything
# (tests/test_live_sources.py tests the saved copies with its own files)
os.environ.setdefault("CAREATZERO_SNAPSHOT_DIR", os.path.join(os.path.dirname(__file__), "_no_snapshots"))
