"""
Checks every live data source CareAtZero uses, from your own computer.

Run from the project folder:
    python tools/check_live_sources.py

It will:
  1. Download the U.S. Census ZIP code list once and save it as
     data/us_zip_centroids.csv (commit this file so the app never has to download it).
  2. Fetch each live source, print how many records came back and one example.
  3. Save the raw downloads in tools/samples/ so the parsers can be tested
     against real data (tests/test_live_sources.py uses them when present).

If a source fails, the message says why (site down, address moved, etc.).
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from live import hrsa, nc_safety_net, ram_events, samhsa, snapshots, zip_centroids  # noqa: E402
from live.common import fetched_at  # noqa: E402
from utils.dates import today  # noqa: E402

SAMPLES = os.path.join(ROOT, "tools", "samples")
RALEIGH = (35.7796, -78.6382)


def show(title, records, fields):
    if not records:
        raise RuntimeError("the source answered, but 0 records could be read from it")
    print(f"   OK: {len(records)} records")
    if records:
        r = records[0]
        print("   Example: " + " | ".join(f"{f}={r.get(f)}" for f in fields))


def step(title, fn):
    print(f"\n== {title}")
    start = time.time()
    try:
        fn()
        print(f"   ({time.time() - start:.1f}s)")
        return True
    except Exception as e:
        print(f"   FAILED: {e}")
        return False


def check_zips():
    centroids = zip_centroids.download_and_save()
    print(f"   OK: {len(centroids)} ZIP codes saved to {os.path.relpath(zip_centroids.CACHE_PATH, ROOT)}")
    print(f"   27601 (Raleigh) -> {centroids.get('27601')}")


def check_hrsa():
    raw = hrsa.fetch_raw("NC")
    with open(os.path.join(SAMPLES, "hrsa.json"), "w", encoding="utf-8") as f:
        json.dump({"features": raw}, f)
    if raw:
        saved = snapshots.save("hrsa", raw, fetched_at(), hrsa.QUERY_URL)
        print(f"   Saved copy updated: {os.path.relpath(saved, ROOT)}")
    show("HRSA", hrsa.parse(raw, fetched_at()), ["name", "city", "zip_code", "phone", "cost_class"])


def check_nc():
    text = nc_safety_net.fetch_raw()
    with open(os.path.join(SAMPLES, "nc_safety_net.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(text)
    if nc_safety_net.parse(text, fetched_at()):
        saved = snapshots.save("nc_safety_net", text, fetched_at(), nc_safety_net.CSV_URL)
        print(f"   Saved copy updated: {os.path.relpath(saved, ROOT)}")
    sites = nc_safety_net.parse(text, fetched_at())
    show("NC", sites, ["name", "type", "city", "zip_code", "cost_class"])
    free = sum(1 for s in sites if s["cost_class"] == "Free")
    print(f"   Free & charitable clinics: {free}")


def check_samhsa():
    raw = samhsa.fetch_raw(*RALEIGH)
    with open(os.path.join(SAMPLES, "samhsa.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": raw}, f)
    show("SAMHSA", samhsa.parse(raw, fetched_at()), ["name", "city", "phone", "cost_class"])


def check_ram():
    text = ram_events.fetch_raw()
    with open(os.path.join(SAMPLES, "ram.ics"), "w", encoding="utf-8", newline="") as f:
        f.write(text)
    ram_events.save_snapshot(text, fetched_at())
    print(f"   Saved copy updated: {os.path.relpath(snapshots.path_for('ram'), ROOT)}")
    events = ram_events.parse(text, fetched_at(), today())
    show("RAM", events, ["title", "date_start", "date_end", "city", "state", "services"])
    nc = [e for e in events if e["state"] == "NC"]
    print(f"   Upcoming in NC: {len(nc)}" + "".join(f"\n     - {e['date_start']} {e['title']} ({e['city']})" for e in nc[:5]))


if __name__ == "__main__":
    os.makedirs(SAMPLES, exist_ok=True)
    results = {
        "U.S. Census ZIP code list": step("U.S. Census ZIP code list", check_zips),
        "HRSA health centers (NC)": step("HRSA health centers (NC)", check_hrsa),
        "NC DHHS Safety Net list": step("NC DHHS Safety Net list", check_nc),
        "SAMHSA FindTreatment.gov (Raleigh)": step("SAMHSA FindTreatment.gov (Raleigh)", check_samhsa),
        "Remote Area Medical calendar": step("Remote Area Medical calendar", check_ram),
    }
    print("\n== Summary")
    for name, ok in results.items():
        print(f"   {'OK    ' if ok else 'FAILED'}  {name}")
    print(f"\nRaw samples saved in {os.path.relpath(SAMPLES, ROOT)}")
    print("Saved copies updated in data/snapshots/ - commit them so the live app has them.")
    sys.exit(0 if all(results.values()) else 1)
