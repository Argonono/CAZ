import datetime
from typing import Any, Dict

from utils.dates import today


def _ics_text(value: Any) -> str:
    """Escape text for a calendar file (commas, semicolons, backslashes and new lines are special)."""
    return (str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Calendar lines longer than 75 characters are split, each new part starting with a space."""
    parts = []
    while len(line.encode("utf-8")) > 75:
        cut = 75
        while len(line[:cut].encode("utf-8")) > 75:
            cut -= 1
        parts.append(line[:cut])
        line = " " + line[cut:]
    parts.append(line)
    return "\r\n".join(parts)


def generate_ics_calendar(event: Dict[str, Any]) -> str:
    """
    A calendar file (.ics, RFC 5545) for a pop-up event or a clinic visit, which opens in
    Google Calendar, Apple Calendar or Outlook.
    - Pop-up events: an all-day entry for each day of the event.
    - Permanent clinics: an all-day reminder for today, since their hours vary
      ("Call for current hours"); the clinic's phone number is in the notes.
    """
    title = event.get("title") or event.get("name") or "CareAtZero health visit"
    location = f"{event.get('address', '')}, {event.get('city', '')}, {event.get('state', '')} {event.get('zip_code', '')}".strip(" ,")
    cost_class = event.get("cost_class") or "Unknown"
    cost_label = "Cost: ask the clinic" if cost_class == "Unknown" else cost_class
    phone = event.get("phone") or "not listed"
    website = event.get("website") or event.get("source_url") or ""

    try:
        start = datetime.date.fromisoformat(str(event.get("date_start"))[:10])
        end = datetime.date.fromisoformat(str(event.get("date_end") or event.get("date_start"))[:10])
    except ValueError:
        start = end = today()  # a clinic visit: today in the user's time zone
    end_exclusive = end + datetime.timedelta(days=1)  # all-day events end the morning after

    now_stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"careatzero-{event.get('id', 'visit')}-{start:%Y%m%d}@careatzero"

    description = "\n".join([
        f"Cost: {cost_label}",
        f"Services: {', '.join(event.get('services') or [])}",
        f"Hours: {event.get('time_details') or event.get('hours_summary') or 'Call for current hours'}",
        f"How to get in: {event.get('appointment_rule') or 'Call ahead'}",
        f"What to bring: {', '.join(event.get('documents_required') or ['Call to confirm'])}",
        f"Phone: {phone}",
        f"More info: {website}",
        "Found with CareAtZero. Emergency: call 911. Crisis: call or text 988.",
    ])

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CareAtZero//Free care finder//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_stamp}",
        f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
        f"DTEND;VALUE=DATE:{end_exclusive:%Y%m%d}",
        f"SUMMARY:{_ics_text(f'[{cost_label}] {title}')}",
        f"LOCATION:{_ics_text(location)}",
        f"DESCRIPTION:{_ics_text(description)}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
