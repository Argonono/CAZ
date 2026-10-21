"""
Collects live records from every source for the Find and Home screens.

How the data is kept (no database needed):
- Records are kept in this server's memory, shared by all users, for 6 hours.
  Searches are answered instantly from memory; only the very first search after
  the app starts waits for the sources (about 1-2 seconds, all fetched at once).
- After 6 hours the next search still gets the copy in memory straight away, and
  a fresh copy is fetched in the background ("stale-while-revalidate").
- If a refresh fails, the last good copy is kept (with its real fetch time), and
  the refresh is tried again in 5 minutes.
- Memory is wiped when the app restarts. If a source can't be reached right after
  a restart, the app uses that source's saved copy from the repo
  (data/snapshots/, see live/snapshots.py), labeled "saved copy" with its date.
- If every clinic source is down and there are no saved copies, the app falls back
  to its built-in directory (data/seed_data.py) and says so on screen.
- Each source reports its status, record count and fetch time; About shows this.
- Pop-up events = RAM's live calendar + the hand-verified community events in the
  saved directory (dental buses, county vans etc. that publish no feed), each shown
  only until its end date.
"""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from live import hrsa, nc_safety_net, ram_events, samhsa, snapshots
from live.common import SourceUnavailable, fetched_at
from utils.dates import today, today_str

CACHE_SECONDS = 6 * 60 * 60
RETRY_SECONDS = 5 * 60


@dataclass
class SourceStatus:
    key: str
    name: str
    provides: str
    url: str
    ok: bool = False
    count: int = 0
    checked: str = ""
    error: str = ""
    saved_copy_from: str = ""  # set when a saved copy is shown because the live source is down


@dataclass
class LiveData:
    sites: List[dict] = field(default_factory=list)
    events: List[dict] = field(default_factory=list)
    statuses: List[SourceStatus] = field(default_factory=list)
    using_saved_directory: bool = False


SOURCES = {
    "hrsa": ("HRSA health centers", "Medical care (sliding scale)", hrsa.SOURCE_URL),
    "nc_safety_net": ("NC DHHS Safety Net list", "Free clinics, dental clinics, health departments", nc_safety_net.SOURCE_URL),
    "samhsa": ("SAMHSA FindTreatment.gov", "Mental health & substance use care near you", samhsa.SOURCE_URL),
    "ram": ("Remote Area Medical (RAM)", "Free pop-up clinics: dental, vision, medical", ram_events.SOURCE_URL),
}

@dataclass
class _Entry:
    records: List[dict]
    checked: str            # when these records were fetched ("" if never fetched)
    error: Optional[str]    # why the last fetch failed (None if it worked)
    refresh_at: float       # after this time, fetch again


_cache: Dict[Tuple, _Entry] = {}
_refreshing: set = set()
_key_locks: Dict[Tuple, threading.Lock] = {}
_lock = threading.Lock()


def _fetch(key: Tuple, loader: Callable[[], List[dict]]) -> _Entry:
    """Fetch one source now and update the cache. A failure keeps the last good records."""
    with _lock:
        key_lock = _key_locks.setdefault(key, threading.Lock())
    with key_lock:  # only one download per source at a time; others wait and reuse its result
        with _lock:
            current = _cache.get(key)
        if current is not None and time.time() < current.refresh_at:
            return current  # someone else fetched it while we waited
        return _download(key, loader)


def _download(key: Tuple, loader: Callable[[], List[dict]]) -> _Entry:
    now = time.time()
    try:
        entry = _Entry(loader(), fetched_at(), None, now + CACHE_SECONDS)
    except Exception as e:  # SourceUnavailable, or an unexpected bug in one source
        error = str(e) if isinstance(e, SourceUnavailable) else f"Unexpected error: {e}"
        with _lock:
            old = _cache.get(key)
        if old and old.records:
            entry = _Entry(old.records, old.checked, error, now + RETRY_SECONDS)  # keep the last good copy
        else:
            entry = _Entry([], "", error, now + RETRY_SECONDS)
    with _lock:
        _cache[key] = entry
        # forget sources nobody has asked for in a long time (old days, far-away searches)
        for old_key in [k for k, v in _cache.items() if v.refresh_at < now - 2 * CACHE_SECONDS]:
            del _cache[old_key]
    return entry


def _refresh_in_background(key: Tuple, loader: Callable[[], List[dict]]) -> None:
    with _lock:
        if key in _refreshing:
            return
        _refreshing.add(key)

    def run():
        try:
            _fetch(key, loader)
        finally:
            with _lock:
                _refreshing.discard(key)

    threading.Thread(target=run, daemon=True).start()


def _cached(key: Tuple, loader: Callable[[], List[dict]]) -> Tuple[List[dict], Optional[str], str]:
    """
    (records, error, fetched_time) for one source.
    Answers from memory whenever there is a copy; refreshes old copies in the background.
    Waits for the network only when there is no copy at all (first search after a restart).
    """
    with _lock:
        entry = _cache.get(key)
    if entry is None:
        entry = _fetch(key, loader)
    elif time.time() >= entry.refresh_at:
        if entry.records:
            _refresh_in_background(key, loader)  # answer now with the copy we have
        else:
            entry = _fetch(key, loader)          # nothing to show yet: try again now
    return entry.records, (entry.error if not entry.records else None), entry.checked


def _site_jobs(lat: Optional[float], lon: Optional[float]) -> Dict[str, Tuple[Tuple, Callable[[], List[dict]]]]:
    jobs = {
        "hrsa": (("hrsa", "NC"), lambda: hrsa.fetch("NC")),
        "nc_safety_net": (("nc_safety_net",), nc_safety_net.fetch),
    }
    if lat is not None and lon is not None:
        samhsa_key = ("samhsa", round(lat, 1), round(lon, 1))  # ~7-mile grid so nearby searches share results
        jobs["samhsa"] = (samhsa_key, lambda: samhsa.fetch(lat, lon))
    return jobs


def warm_up(lat: Optional[float] = None, lon: Optional[float] = None) -> None:
    """
    Start loading the clinic sources in the background (called from Home), so the
    first Find search is instant. Does nothing for sources already in memory.
    """
    for key, loader in _site_jobs(lat, lon).values():
        with _lock:
            known = key in _cache
        if not known:
            _refresh_in_background(key, loader)


def clear_cache() -> None:
    with _lock:
        _cache.clear()
        _refreshing.clear()
        _key_locks.clear()


def _saved_copy(key: str, day) -> Tuple[List[dict], str]:
    """A source's saved copy from the repo, parsed and labeled, and when it was saved."""
    raw, saved_at = snapshots.load(key)
    if raw is None:
        return [], ""
    try:
        if key == "hrsa":
            records = hrsa.parse(raw, saved_at)
        elif key == "nc_safety_net":
            records = nc_safety_net.parse(raw, saved_at)
        elif key == "ram":
            records = ram_events.parse(raw, saved_at, day)
        else:
            return [], ""
    except Exception:
        return [], ""
    for r in records:
        r["is_live"] = False
        r["source_name"] = f"{r['source_name']} (saved copy)"
    return records, saved_at


def _dedupe_key(site: dict) -> str:
    name = re.sub(r"[^a-z0-9]", "", (site.get("name") or "").lower())
    return f"{name}|{site.get('zip_code', '')}"


COST_RANK = {"Free": 3, "Very Low Cost": 2, "Sliding Scale": 1}


def _merge_into(kept: dict, other: dict) -> None:
    """
    Combine two listings of the same clinic: keep every service either list mentions,
    and the lowest cost either list states (e.g. the state's "Free and Charitable
    Clinic" label wins over HRSA's general "Sliding Scale").
    """
    kept["services"] = list(dict.fromkeys(list(kept.get("services") or []) + list(other.get("services") or [])))
    if COST_RANK.get(other.get("cost_class"), 0) > COST_RANK.get(kept.get("cost_class"), 0):
        for name in ("cost_class", "eligibility", "documents_required"):
            kept[name] = other.get(name, kept.get(name))
        kept["source_name"] = f"{kept['source_name']}; cost from {other.get('source_name')}"


def load_live_data(lat: Optional[float], lon: Optional[float], include_sites: bool = True) -> LiveData:
    """
    Live sites and upcoming events around (lat, lon), plus each source's status.
    include_sites=False loads only the pop-up events (used by the Home screen).
    With no location (lat/lon None), the location-based source (SAMHSA) is skipped.
    """
    day = today()
    jobs = {"ram": (("ram", day.isoformat()), lambda: ram_events.fetch(day))}
    if include_sites:
        jobs.update(_site_jobs(lat, lon))
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {k: pool.submit(_cached, key, loader) for k, (key, loader) in jobs.items()}
        results = {k: f.result() for k, f in futures.items()}

    data = LiveData()
    seen: Dict[str, dict] = {}
    for key in ("hrsa", "nc_safety_net", "samhsa", "ram"):
        if key not in results:
            continue
        records, error, checked = results[key]
        name, provides, url = SOURCES[key]
        data.statuses.append(SourceStatus(key, name, provides, url, ok=error is None,
                                          count=len(records), checked=checked, error=error or ""))
        if error:  # live source unavailable and nothing in memory: use its saved copy, clearly labeled
            saved, saved_at = _saved_copy(key, day)
            if saved_at:
                data.statuses[-1].saved_copy_from = saved_at
                data.statuses[-1].count = len(saved)
                records = saved
        if key == "ram":
            data.events.extend(records)
            continue
        for site in records:
            k = _dedupe_key(site)
            if k in seen:  # the same clinic is in more than one list: merge what each list knows
                _merge_into(seen[k], site)
            else:
                seen[k] = dict(site)  # a copy, so the shared copy in memory is never changed
                data.sites.append(seen[k])

    # Hand-verified community events (dental buses, county vans...) that publish no feed
    try:
        from database.db import get_all_events, get_all_sites
        community = get_all_events(include_expired=False, current_date_str=today_str())
        for e in community:
            e["source_name"] = f"{e.get('source_name') or 'CareAtZero community list'} (manually verified)"
        data.events.extend(community)
        if include_sites and not data.sites:
            # every clinic source is down: show the saved directory, clearly labeled
            data.using_saved_directory = True
            for s in get_all_sites():
                s["source_name"] = f"{s.get('source_name') or 'Saved directory'} (saved copy)"
                data.sites.append(s)
    except Exception:
        pass

    data.events.sort(key=lambda e: e.get("date_start") or "")
    return data


def find_record(record_id: str, lat: float, lon: float) -> Optional[dict]:
    """Look up one record by id (for the Detail screen), live data first, then the saved directory."""
    data = load_live_data(lat, lon)
    for rec in data.sites + data.events:
        if rec.get("id") == record_id:
            return rec
    try:
        from database.db import get_event_by_id, get_site_by_id
        return get_site_by_id(record_id) or get_event_by_id(record_id)
    except Exception:
        return None
