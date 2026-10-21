"""
The app's idea of "today", and how dates and times are shown.

Pop-up events are shown only until their end date, and the Care Access Score
counts the days until an event, so the app needs the real current date.
Dates and times use the time zone of the area being searched (see
utils/timezones.py), so "today" doesn't flip early in the evening on servers
that run on UTC time, and works the same in every U.S. time zone.

For tests or a repeatable demo, set the CAREATZERO_TODAY environment variable
to a fixed date, e.g.  CAREATZERO_TODAY=2026-09-16
"""
import datetime
import os

from utils.timezones import current_timezone_name, friendly_name


def _zone(tz_name=None):
    """ZoneInfo for tz_name (default: this user's display time zone), or None if unavailable."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name or current_timezone_name())
    except Exception:  # no time zone database (e.g. Windows without tzdata) or unknown name
        return None


def today(tz_name=None) -> datetime.date:
    """Today's date in the search area's time zone, or the CAREATZERO_TODAY override."""
    override = os.environ.get("CAREATZERO_TODAY", "").strip()
    if override:
        try:
            return datetime.date.fromisoformat(override)
        except ValueError:
            pass  # ignore a badly formatted override and use the real date
    zone = _zone(tz_name)
    if zone is not None:
        return datetime.datetime.now(zone).date()
    return datetime.date.today()


def today_str() -> str:
    """Today's date as YYYY-MM-DD, the format the database uses."""
    return today().isoformat()


def checked_parts(value, tz_name=None):
    """
    Split a 'last checked' value into (date, time) text for display, in the
    search area's local time (or tz_name if given).

    Live records store the exact fetch time in UTC, e.g. '2026-10-10T01:36:30+00:00'.
    That is 9:36 PM on Oct 9 in North Carolina, so it is converted before showing it:
        -> ('Oct 9, 2026', '9:36 PM EDT')        (Nashville: '8:36 PM CDT')
    Hand-verified records store only a date ('2026-09-16') -> ('Sep 16, 2026', None).
    """
    text = str(value or "").strip()
    if not text:
        return "date not listed", None
    if "T" in text or " " in text.strip()[10:11]:
        try:
            moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=datetime.timezone.utc)
            target = _zone(tz_name)
            if target is not None:
                moment = moment.astimezone(target)
                zone = moment.tzname() or ""
            else:
                moment = moment.astimezone(datetime.timezone.utc)
                zone = "UTC"
            date_text = f"{moment:%b} {moment.day}, {moment.year}"
            hour = moment.hour % 12 or 12
            time_text = f"{hour}:{moment:%M} {'AM' if moment.hour < 12 else 'PM'} {zone}"
            return date_text, time_text
        except ValueError:
            pass
    try:
        d = datetime.date.fromisoformat(text[:10])
        return f"{d:%b} {d.day}, {d.year}", None
    except ValueError:
        return text, None


def format_checked_date(value, tz_name=None) -> str:
    """Just the date part, in local time: 'Oct 9, 2026'."""
    return checked_parts(value, tz_name)[0]


def timezone_label(tz_name=None) -> str:
    """'Eastern Time', 'Central Time', ... for the display time zone."""
    return friendly_name(tz_name or current_timezone_name())


def format_checked(value, tz_name=None) -> str:
    """Date and time with time zone when known: 'Oct 9, 2026 at 9:36 PM EDT', else 'Sep 16, 2026'."""
    date_text, time_text = checked_parts(value, tz_name)
    return f"{date_text} at {time_text}" if time_text else date_text


def format_event_dates(start, end=None) -> str:
    """'2027-04-24', '2027-04-25' -> 'Apr 24–25, 2027'; one day -> 'Apr 24, 2027'."""
    try:
        d1 = datetime.date.fromisoformat(str(start)[:10])
        d2 = datetime.date.fromisoformat(str(end)[:10]) if end else d1
    except (TypeError, ValueError):
        return str(start or "Date to be announced")
    if d2 <= d1:
        return f"{d1:%b} {d1.day}, {d1.year}"
    if (d1.year, d1.month) == (d2.year, d2.month):
        return f"{d1:%b} {d1.day}–{d2.day}, {d1.year}"
    if d1.year == d2.year:
        return f"{d1:%b} {d1.day} – {d2:%b} {d2.day}, {d1.year}"
    return f"{d1:%b} {d1.day}, {d1.year} – {d2:%b} {d2.day}, {d2.year}"
