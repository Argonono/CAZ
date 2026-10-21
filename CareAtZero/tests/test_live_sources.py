"""
Tests for the live data connectors (live/).

The small inputs below copy each source's real format. If tools/check_live_sources.py
has been run, the real downloads in tools/samples/ are also parsed (those tests are
skipped otherwise), so a change in a source's format shows up here.
"""
import datetime
import json
import os

import pytest

from live import hrsa, nc_safety_net, ram_events, samhsa, sources, zip_centroids
from live.common import split_address, stable_id

CHECKED = "2026-10-09T14:00:00+00:00"
TODAY = datetime.date(2026, 10, 9)
SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "samples")

TEST_ZIPS = {"27537": (36.33, -78.39), "27601": (35.773, -78.634), "28906": (35.087, -84.03),
             "37902": (35.96, -83.92)}


@pytest.fixture(autouse=True)
def small_zip_list(monkeypatch):
    monkeypatch.setattr(zip_centroids, "_cache", dict(TEST_ZIPS))
    sources.clear_cache()
    yield
    sources.clear_cache()


# ---------- shared helpers ----------

def test_split_address():
    assert split_address("21 Campus Circle, Murphy, NC 28906") == ("21 Campus Circle", "Murphy", "NC", "28906")
    assert split_address("Somewhere without a zip") == ("Somewhere without a zip", "", "", "")


def test_stable_id_is_repeatable():
    assert stable_id("x", "a", "b") == stable_id("x", "a", "b")
    assert stable_id("x", "a", "b") != stable_id("x", "a", "c")


# ---------- RAM pop-up clinics ----------

RAM_ICS = "\r\n".join([
    "BEGIN:VCALENDAR",
    "BEGIN:VEVENT",
    "SUMMARY:Henderson\\, NC",
    "DTSTART;TZID=America/New_York:20270424T000000",
    "DTEND;TZID=America/New_York:20270426T000000",
    "LOCATION:Vance-Granville Community College\\, 200 Community College Rd\\, Henderson\\, NC 27537",
    "DESCRIPTION:Free Dental\\, Vision\\, and Medical Services\\nOpen to everyone. No ID required. No insur",
    " ance required.\\nParking lot opens at 12:00 am. Doors open at 6:00 am.\\nDenture services are not available.",
    "URL:https://www.ramusa.org/events/henderson-nc/",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "SUMMARY:Old Clinic\\, TN",
    "DTSTART:20260301T000000",
    "DTEND:20260303T000000",
    "LOCATION:1 Main St\\, Knoxville\\, TN 37902",
    "DESCRIPTION:Free Dental Services",
    "END:VEVENT",
    "END:VCALENDAR",
])


def test_ram_parses_upcoming_event():
    events = ram_events.parse(RAM_ICS, CHECKED, TODAY)
    assert len(events) == 1  # the March 2026 clinic is already over
    e = events[0]
    assert e["date_start"] == "2027-04-24"
    assert e["date_end"] == "2027-04-25"  # DTEND midnight = not including the 26th
    assert e["city"] == "Henderson" and e["state"] == "NC" and e["zip_code"] == "27537"
    assert (e["latitude"], e["longitude"]) == TEST_ZIPS["27537"]
    assert e["services"] == ["Dental", "Vision", "Medical"]
    assert e["cost_class"] == "Free"
    assert e["documents_required"] == ["None required"]
    assert "No insurance required." in e["eligibility"]  # folded line joined correctly
    assert "Parking lot opens" in e["time_details"]
    assert e["website"] == "https://www.ramusa.org/events/henderson-nc/"
    assert e["is_live"] and e["last_checked"] == CHECKED


def test_ram_not_free_unless_it_says_so():
    ics = RAM_ICS.replace("Free Dental", "Dental")
    assert ram_events.parse(ics, CHECKED, TODAY)[0]["cost_class"] == "Unknown"


# ---------- HRSA health centers ----------

HRSA_FEATURES = [
    {"attributes": {"OBJECTID": 1, "SITE_NM": "Advance Community Health", "SITE_ADDRESS": "1001 Rock Quarry Rd",
                    "SITE_CITY": "RALEIGH", "SITE_STATE_ABBR": "NC", "SITE_ZIP_CD": "27610-4104",
                    "SITE_PHONE_NUM": "919-833-3111", "SITE_URL": "https://advancechc.org",
                    "HCC_LOC_SETTING_DESC": "All Other Clinic Types", "HCC_LOC_DESC": "Permanent",
                    "GRANTEE_NM": "Advance Community Health, Inc."},
     "geometry": {"x": -78.61, "y": 35.76}},
    {"attributes": {"OBJECTID": 2, "SITE_NM": "School Clinic", "SITE_ZIP_CD": "27601",
                    "HCC_LOC_SETTING_DESC": "School"}, "geometry": {"x": -78.6, "y": 35.7}},
    {"attributes": {"OBJECTID": 3, "SITE_NM": "No location"}, "geometry": {}},
]


def test_hrsa_parse():
    sites = hrsa.parse(HRSA_FEATURES, CHECKED)
    assert len(sites) == 1  # school-based and unmapped sites left out
    s = sites[0]
    assert s["name"] == "Advance Community Health"
    assert s["city"] == "Raleigh" and s["zip_code"] == "27610"
    assert s["phone"] == "(919) 833-3111"
    assert s["cost_class"] == "Sliding Scale"  # never labeled Free
    assert (s["latitude"], s["longitude"]) == (35.76, -78.61)


# ---------- NC DHHS Safety Net list ----------

NC_CSV = (
    "Site Name,Facility Type,Street_Address,Street_Address_2,City,State,Zip_Code,phone_number1\n"
    "Open Door Clinic,Free and Charitable Clinic,309 Bragg St,,RALEIGH,NC,27601,919-555-0100\n"
    "Wake Dental,Dental Clinic (stand alone),10 Main St,Suite 2,RALEIGH,NC,27601,9195550101\n"
    "Rural Hospital,Critical Access Hospital,1 Main,,MURPHY,NC,28906,\n"
    "Kids Clinic,School Based Health Center,2 Main,,RALEIGH,NC,27601,\n"
    "Unknown Zip Clinic,Free and Charitable Clinic,3 Main,,NOWHERE,NC,99999,\n"
    "Other Place,Some New Category,4 Main,,MURPHY,NC,28906,\n"
)


def test_nc_safety_net_parse():
    sites = {s["name"]: s for s in nc_safety_net.parse(NC_CSV, CHECKED)}
    assert set(sites) == {"Open Door Clinic", "Wake Dental", "Other Place"}
    assert sites["Open Door Clinic"]["cost_class"] == "Free"
    assert sites["Open Door Clinic"]["type"] == "free_clinic"
    assert sites["Wake Dental"]["cost_class"] == "Sliding Scale"
    assert sites["Wake Dental"]["services"] == ["Dental"]
    assert sites["Wake Dental"]["address"] == "10 Main St, Suite 2"
    assert sites["Other Place"]["cost_class"] == "Unknown"  # never guessed


# ---------- SAMHSA FindTreatment.gov ----------

SAMHSA_ROWS = [
    {"name1": "Alliance Behavioral Care", "name2": "", "street1": "5200 Paramount Pkwy", "street2": "",
     "city": "MORRISVILLE", "state": "NC", "zip": "27560", "phone": "919-651-8401", "website": "https://x.org",
     "latitude": "35.85", "longitude": "-78.83", "type_facility": "MH",
     "services": [{"f2": "PYAS", "f3": "Sliding fee scale"}, {"f2": "AGE", "f3": "Adults"},
                  {"f2": "SET", "f3": "Outpatient; Walk-in"}]},
    {"name1": "Free Help Center", "latitude": "35.8", "longitude": "-78.6",
     "services": [{"f2": "PYAS", "f3": "Treatment at no charge or minimal payment for clients who cannot afford to pay"}]},
    {"name1": "Plain Center", "latitude": "35.8", "longitude": "-78.6", "services": []},
    {"name1": "No coords"},
]


def test_samhsa_parse():
    sites = {s["name"]: s for s in samhsa.parse(SAMHSA_ROWS, CHECKED)}
    assert set(sites) == {"Alliance Behavioral Care", "Free Help Center", "Plain Center"}
    assert sites["Alliance Behavioral Care"]["cost_class"] == "Sliding Scale"
    assert sites["Alliance Behavioral Care"]["appointment_rule"] == "Walk-in services offered"
    assert sites["Free Help Center"]["cost_class"] == "Free"
    assert sites["Plain Center"]["cost_class"] == "Unknown"


# ---------- putting the sources together ----------

def test_all_sources_down_uses_labeled_saved_directory():
    data = sources.load_live_data(35.77, -78.63)  # tests run with CAREATZERO_OFFLINE=1
    assert data.using_saved_directory
    assert data.sites and all("(saved copy)" in s["source_name"] for s in data.sites)
    assert {s.key for s in data.statuses} == {"hrsa", "nc_safety_net", "samhsa", "ram"}
    assert not any(s.ok for s in data.statuses)


def test_live_sources_combined_and_deduplicated(monkeypatch):
    hrsa_sites = hrsa.parse(HRSA_FEATURES, CHECKED)
    dup = dict(hrsa_sites[0], id="ncdhhs_dup", name="ADVANCE COMMUNITY HEALTH")
    monkeypatch.setattr(hrsa, "fetch", lambda state: hrsa_sites)
    monkeypatch.setattr(nc_safety_net, "fetch", lambda: nc_safety_net.parse(NC_CSV, CHECKED) + [dup])
    monkeypatch.setattr(samhsa, "fetch", lambda lat, lon: samhsa.parse(SAMHSA_ROWS, CHECKED))
    monkeypatch.setattr(ram_events, "fetch", lambda day: ram_events.parse(RAM_ICS, CHECKED, TODAY))
    data = sources.load_live_data(35.77, -78.63)
    assert not data.using_saved_directory
    assert all(s.ok for s in data.statuses)
    names = [s["name"] for s in data.sites]
    assert names.count("Advance Community Health") == 1 and "ADVANCE COMMUNITY HEALTH" not in names
    assert all(s.get("is_live") for s in data.sites)
    assert any(e["title"].startswith("Remote Area Medical") for e in data.events)
    rec = sources.find_record(data.sites[0]["id"], 35.77, -78.63)
    assert rec and rec["id"] == data.sites[0]["id"]


def test_one_source_down_keeps_the_others(monkeypatch):
    monkeypatch.setattr(hrsa, "fetch", lambda state: hrsa.parse(HRSA_FEATURES, CHECKED))
    data = sources.load_live_data(35.77, -78.63)
    status = {s.key: s.ok for s in data.statuses}
    assert status["hrsa"] and not status["samhsa"]
    assert not data.using_saved_directory
    assert [s["name"] for s in data.sites] == ["Advance Community Health"]


# ---------- real downloads (after running tools/check_live_sources.py) ----------

def _sample(name):
    path = os.path.join(SAMPLES, name)
    if not os.path.exists(path):
        pytest.skip(f"run tools/check_live_sources.py to create {name}")
    return path


def test_real_hrsa_sample():
    with open(_sample("hrsa.json"), encoding="utf-8") as f:
        sites = hrsa.parse(json.load(f)["features"], CHECKED)
    assert len(sites) > 50 and all(s["state"] == "NC" for s in sites)


def test_real_nc_sample(monkeypatch):
    monkeypatch.setattr(zip_centroids, "_cache", None)  # use the real ZIP list
    with open(_sample("nc_safety_net.csv"), encoding="utf-8") as f:
        sites = nc_safety_net.parse(f.read(), CHECKED)
    assert len(sites) > 50 and any(s["cost_class"] == "Free" for s in sites)


def test_real_samhsa_sample():
    with open(_sample("samhsa.json"), encoding="utf-8") as f:
        assert samhsa.parse(json.load(f)["rows"], CHECKED)


def test_real_ram_sample(monkeypatch):
    monkeypatch.setattr(zip_centroids, "_cache", None)
    with open(_sample("ram.ics"), encoding="utf-8") as f:
        events = ram_events.parse(f.read(), CHECKED, datetime.date(2000, 1, 1))
    assert events and all(e["date_end"] >= e["date_start"] for e in events)


# ---------- RAM's site answering with a web page instead of the calendar ----------

class _Page:
    text = "<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>"


def test_ram_web_page_is_unavailable_not_empty(monkeypatch):
    monkeypatch.setattr(ram_events, "http_get", lambda *a, **k: _Page())
    with pytest.raises(sources.SourceUnavailable):
        ram_events.fetch(TODAY)


def test_ram_down_uses_labeled_saved_copy(monkeypatch, tmp_path):
    from live import snapshots
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", str(tmp_path))
    ram_events.save_snapshot(RAM_ICS, "2026-10-10T01:21:20+00:00")
    data = sources.load_live_data(35.77, -78.63, include_sites=False)  # tests run offline
    ram = next(s for s in data.statuses if s.key == "ram")
    assert not ram.ok and ram.saved_copy_from == "2026-10-10T01:21:20+00:00" and ram.count == 1
    henderson = [e for e in data.events if "Henderson" in e["title"]]
    assert henderson and "(saved copy)" in henderson[0]["source_name"] and not henderson[0]["is_live"]


def test_ram_down_without_saved_copy_shows_nothing(monkeypatch, tmp_path):
    from live import snapshots
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", str(tmp_path / "none"))
    data = sources.load_live_data(35.77, -78.63, include_sites=False)
    ram = next(s for s in data.statuses if s.key == "ram")
    assert not ram.ok and not ram.saved_copy_from
    assert not any("(saved copy)" in e["source_name"] for e in data.events)


# ---------- answering from memory, refreshing in the background ----------

def _wait_for_refreshes():
    import time
    for _ in range(200):
        with sources._lock:
            if not sources._refreshing:
                return
        time.sleep(0.01)


def test_old_copy_answers_instantly_and_refreshes_in_background():
    calls = []
    def loader():
        calls.append(1)
        if len(calls) > 1:
            import time; time.sleep(0.2)   # a slow refresh must not hold up the answer
        return [{"n": len(calls)}]
    key = ("test_source",)
    assert sources._cached(key, loader)[0] == [{"n": 1}]          # first time: fetched now
    sources._cache[key].refresh_at = 0                             # pretend 6 hours passed
    import time; start = time.time()
    records, error, _ = sources._cached(key, loader)
    assert records == [{"n": 1}] and error is None                 # old copy, straight away
    assert time.time() - start < 0.1
    _wait_for_refreshes()
    assert sources._cached(key, loader)[0] == [{"n": 2}]          # refreshed copy now in memory


def test_failed_refresh_keeps_last_good_copy():
    state = {"fail": False}
    def loader():
        if state["fail"]:
            raise sources.SourceUnavailable("site down")
        return [{"clinic": "A"}]
    key = ("test_source2",)
    _, _, first_checked = sources._cached(key, loader)
    state["fail"] = True
    sources._cache[key].refresh_at = 0
    sources._cached(key, loader); _wait_for_refreshes()
    records, error, checked = sources._cached(key, loader)
    assert records == [{"clinic": "A"}] and error is None
    assert checked == first_checked              # still shows when the data was really fetched
    assert sources._cache[key].error == "site down"


def test_after_restart_with_sources_down_saved_copies_are_used(monkeypatch, tmp_path):
    from live import snapshots
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", str(tmp_path))
    snapshots.save("hrsa", HRSA_FEATURES, "2026-10-10T01:21:17+00:00")
    snapshots.save("nc_safety_net", NC_CSV, "2026-10-10T01:21:18+00:00")
    data = sources.load_live_data(35.77, -78.63)          # everything offline, nothing in memory
    status = {s.key: s for s in data.statuses}
    assert status["hrsa"].saved_copy_from and status["nc_safety_net"].saved_copy_from
    assert not data.using_saved_directory                   # saved copies beat the old built-in list
    names = {s["name"] for s in data.sites}
    assert {"Advance Community Health", "Open Door Clinic"} <= names
    assert all("(saved copy)" in s["source_name"] and not s["is_live"] for s in data.sites)


def test_warm_up_loads_clinics_in_background(monkeypatch):
    monkeypatch.setattr(hrsa, "fetch", lambda state: hrsa.parse(HRSA_FEATURES, CHECKED))
    sources.warm_up()
    _wait_for_refreshes()
    assert sources._cache[("hrsa", "NC")].records


def test_slow_sites_time_out_quickly():
    from live import common
    assert common.TIMEOUT_SECONDS <= 8
