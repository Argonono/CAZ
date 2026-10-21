"""
Map location (latitude, longitude) for any U.S. ZIP code.

Source: U.S. Census Bureau ZCTA Gazetteer file (official, public).
The national file is downloaded once and saved as data/us_zip_centroids.csv,
so the app doesn't need to download it again. tools/check_live_sources.py
creates that file, and it is committed to the repo.

A ZIP's centroid is the middle of the ZIP area, not an exact street address:
accurate enough for distance in miles, which is all the app uses it for.
"""
import csv
import io
import os
import zipfile
import time
from typing import Dict, Optional, Tuple

from live.common import http_get

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_zcta_national.zip"
)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(PROJECT_ROOT, "data", "us_zip_centroids.csv")

_cache: Optional[Dict[str, Tuple[float, float]]] = None
_download_failed_at = 0.0
RETRY_DOWNLOAD_SECONDS = 10 * 60


def parse_gazetteer(text: str) -> Dict[str, Tuple[float, float]]:
    """Parse the tab-separated Census file. Columns are found by name, since their order has changed over the years."""
    lines = text.splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    zi, la, lo = header.index("GEOID"), header.index("INTPTLAT"), header.index("INTPTLONG")
    result = {}
    for line in lines[1:]:
        cols = line.split("\t")
        if len(cols) <= max(zi, la, lo):
            continue
        try:
            result[cols[zi].strip()] = (float(cols[la]), float(cols[lo]))
        except ValueError:
            continue
    return result


def download_and_save() -> Dict[str, Tuple[float, float]]:
    resp = http_get(GAZETTEER_URL, timeout=60)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".txt"))
        text = zf.read(name).decode("latin-1")
    centroids = parse_gazetteer(text)
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["zip", "lat", "lon"])
        for z, (lat, lon) in sorted(centroids.items()):
            w.writerow([z, round(lat, 5), round(lon, 5)])
    return centroids


def load() -> Dict[str, Tuple[float, float]]:
    """All U.S. ZIP centroids, from the saved file (downloading it once if missing)."""
    global _cache, _download_failed_at
    if _cache is not None:
        return _cache
    if os.path.exists(CACHE_PATH):
        result = {}
        with open(CACHE_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    result[row["zip"]] = (float(row["lat"]), float(row["lon"]))
                except (KeyError, ValueError):
                    continue
        if result:
            _cache = result
            return _cache
    if time.time() - _download_failed_at < RETRY_DOWNLOAD_SECONDS:
        return {}  # a download just failed; don't make every ZIP lookup wait on it again
    try:
        _cache = download_and_save()
    except Exception:
        _download_failed_at = time.time()
        raise
    return _cache


def nearest_zip(lat: float, lon: float, max_miles: float = 25.0) -> Optional[str]:
    """The ZIP code whose center is closest to (lat, lon), or None if none is within max_miles."""
    try:
        centroids = load()
    except Exception:
        return None
    import math
    best, best_d = None, None
    cos_lat = math.cos(math.radians(lat))
    for z, (zl, zo) in centroids.items():
        d = (zl - lat) ** 2 + ((zo - lon) * cos_lat) ** 2  # fast flat-earth distance, fine at this scale
        if best_d is None or d < best_d:
            best, best_d = z, d
    if best is None or math.sqrt(best_d) * 69.0 > max_miles:
        return None
    return best


def coords_for_zip(zip_code: str) -> Optional[Tuple[float, float]]:
    """(lat, lon) for a 5-digit ZIP, or None if unknown or the ZIP list can't be loaded."""
    zip5 = (zip_code or "").strip()[:5]
    if not (len(zip5) == 5 and zip5.isdigit()):
        return None
    try:
        return load().get(zip5)
    except Exception:
        return None
