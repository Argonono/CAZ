"""
Remote Area Medical (RAM) -> Free pop-up clinics (dental, vision, medical).

Source: RAM's public event calendar feed (iCalendar format), the same calendar
behind https://www.ramusa.org/schedule. Each event has its dates, address and a
description of the services. RAM clinics are free, first come first served, and
need no ID, insurance or proof of income; those details are read from each
event's own description rather than assumed.

The feed has no map coordinates, so each clinic is placed at its ZIP code's center.

RAM's website sometimes answers automated requests from cloud servers (like
Streamlit Cloud) with a web page instead of the calendar. That is treated as
"unavailable", never as "no clinics". In that case the app uses a saved copy of
RAM's calendar (data/snapshots/ram.json, refreshed by running
tools/check_live_sources.py), labeled with the date it was saved, and still hides
clinics that have already ended.
"""
import datetime
import re
from typing import Dict, List, Optional

from live import snapshots, zip_centroids
from live.common import SourceUnavailable, fetched_at, http_get, split_address, stable_id
from live.records import make_event

FEED_URL = "https://www.ramusa.org/?mec-ical-feed=1"
SOURCE_NAME = "Remote Area Medical (RAM) clinic schedule"
SOURCE_URL = "https://www.ramusa.org/schedule/"
RAM_PHONE = "(865) 579-1530"


def unfold(ics_text: str) -> List[str]:
    """iCalendar wraps long lines; a line starting with a space continues the previous one."""
    lines: List[str] = []
    for raw in ics_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\")).strip()


def parse_ics_date(value: str) -> Optional[datetime.date]:
    m = re.match(r"(\d{4})(\d{2})(\d{2})", value.strip())
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def parse_vevents(ics_text: str) -> List[Dict[str, str]]:
    """Each VEVENT as {'SUMMARY': ..., 'DTSTART': ..., ...} (parameters like ;TZID=... dropped)."""
    events, current = [], None
    for line in unfold(ics_text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";", 1)[0].upper()] = value
    return events


def services_from(text: str) -> List[str]:
    t = text.lower()
    found = [label for word, label in (("dental", "Dental"), ("vision", "Vision"), ("medical", "Medical"))
             if word in t]
    if not found and "telehealth" in t:
        found = ["Medical"]
    return found or ["Medical"]


def timing_from(description: str) -> str:
    """Pick out the arrival details (parking lot opens, tickets, doors) from the description."""
    keep = [ln.strip() for ln in description.split("\n")
            if re.search(r"parking|ticket|doors|gates|open(s)? at|\d{1,2}:\d{2}\s*(am|pm)", ln, re.I)]
    return " ".join(keep[:3]) if keep else "Check the RAM event page for arrival times; arrive early, first come first served."


def parse(ics_text: str, checked: str, today: datetime.date) -> List[dict]:
    events = []
    for ev in parse_vevents(ics_text):
        start = parse_ics_date(ev.get("DTSTART", ""))
        end = parse_ics_date(ev.get("DTEND", "")) or start
        if start is None:
            continue
        # DTEND at midnight is "up to but not including" that day
        if end and end > start and ev.get("DTEND", "").strip().endswith("T000000"):
            end = end - datetime.timedelta(days=1)
        if end < today:
            continue  # already over
        title = unescape(ev.get("SUMMARY", "")) or "RAM free clinic"
        description = unescape(ev.get("DESCRIPTION", ""))
        location = unescape(ev.get("LOCATION", ""))
        street, city, state, zip5 = split_address(location)
        coords = zip_centroids.coords_for_zip(zip5)
        desc_lower = description.lower()
        # "Free" only when the care is called free, not "free parking" or "smoke-free campus"
        is_free = bool(re.search(r"(?<![-\w])free(?!\s+parking)\b", f"{title}\n{description}", re.I))
        no_docs = "no id required" in desc_lower
        eligibility_bits = [s for s in ("Open to everyone.", "No ID required.", "No insurance required.",
                                        "No income requirements.") if s.lower() in desc_lower]
        url = unescape(ev.get("URL", "")) or SOURCE_URL
        events.append(make_event(
            id=stable_id("ram", title, start.isoformat(), zip5),
            title=f"Remote Area Medical — {title}" if not title.lower().startswith("remote area medical") else title,
            organizer_name="Remote Area Medical (RAM)",
            date_start=start.isoformat(),
            date_end=end.isoformat(),
            time_details=timing_from(description),
            location_name=street or location,
            address=street or location,
            city=city,
            state=state,
            zip_code=zip5,
            latitude=coords[0] if coords else None,
            longitude=coords[1] if coords else None,
            # services come from the title and the description's opening line
            # ("Free Dental, Vision, and Medical Services"), not later notes like
            # "Denture services are not available"
            services=services_from(f"{title}\n{description.split(chr(10))[0][:160]}"),
            cost_class="Free" if is_free else "Unknown",
            eligibility=" ".join(eligibility_bits) or "See the RAM event page for eligibility",
            appointment_rule="No appointment; first come, first served (arrive early for a ticket)",
            documents_required=["None required"] if no_docs else ["See the RAM event page"],
            phone=RAM_PHONE,
            website=url,
            source_name=SOURCE_NAME,
            source_url=url,
            last_checked=checked,
            notes=description[:600],
        ))
    events.sort(key=lambda e: e["date_start"])
    return events


def fetch_raw() -> str:
    text = http_get(FEED_URL).text
    if "BEGIN:VCALENDAR" not in text:
        start = " ".join(text.strip().split())[:80]
        raise SourceUnavailable(f"RAM's site sent a web page instead of its calendar (starts: \"{start}\")")
    return text


def fetch(today: datetime.date) -> List[dict]:
    return parse(fetch_raw(), fetched_at(), today)


def save_snapshot(ics_text: str, saved_at: str) -> None:
    snapshots.save("ram", ics_text, saved_at, FEED_URL)
