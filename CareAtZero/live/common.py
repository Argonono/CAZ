"""Shared helpers for the live data connectors."""
import datetime
import hashlib
import os
import re
from typing import Optional, Tuple

import requests

USER_AGENT = "CareAtZero/1.0 (student project; free-care finder for uninsured patients)"
TIMEOUT_SECONDS = 8  # a slow site must not hold up a search for long


class SourceUnavailable(Exception):
    """A live source couldn't be reached or returned unusable data. Never fill the gap with made-up data."""


def http_get(url: str, params: Optional[dict] = None, timeout: int = TIMEOUT_SECONDS) -> requests.Response:
    # CAREATZERO_OFFLINE=1 (set by the tests) acts as if every source is down, so tests
    # don't depend on outside websites and the saved-directory fallback gets exercised.
    if os.environ.get("CAREATZERO_OFFLINE") == "1":
        raise SourceUnavailable("offline mode (CAREATZERO_OFFLINE=1)")
    try:
        resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        raise SourceUnavailable(f"{url.split('/')[2]} unreachable: {e}") from e


def fetched_at() -> str:
    """Timestamp stored as each record's 'last_checked' (UTC, ISO format)."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def stable_id(prefix: str, *parts: str) -> str:
    """
    An ID that stays the same every time the data is fetched, so a clinic picked
    on the Find screen can be found again on the Detail screen.
    (Python's built-in hash() changes between runs, so it can't be used here.)
    """
    digest = hashlib.sha1("|".join(p or "" for p in parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


_ADDRESS_TAIL = re.compile(r",\s*([^,]+?),?\s+([A-Z]{2})(?:\s+(\d{5})(?:-\d{4})?)?\s*$")


def split_address(full: str) -> Tuple[str, str, str, str]:
    """'21 Campus Circle, Murphy, NC 28906' -> ('21 Campus Circle', 'Murphy', 'NC', '28906')."""
    full = (full or "").strip()
    m = _ADDRESS_TAIL.search(full)
    if not m:
        return full, "", "", ""
    street = full[: m.start()].strip(" ,")
    return street, m.group(1).strip(), m.group(2), m.group(3) or ""


def clean_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return (phone or "").strip()
