"""India + US festival/holiday lookup. This is what lets the event-selection
skill give cultural moments (Diwali, Dussehra, Eid, Independence Day,
Republic Day, Thanksgiving, Christmas, Labor Day, Presidents Day, ...)
precedence over ordinary trending news (sports, finance, policy) when
"today" or "tomorrow" is one of them.

Primary source: the `holidays` PyPI package, which carries India's
optional Hindu/Islamic religious-festival categories (Diwali, Dussehra,
Holi, Eid al-Fitr, Eid al-Adha, ...) alongside its standard US federal
calendar. If the installed `holidays` version doesn't expose those
categories (its API for this has changed across versions), this falls back
to festivals_static.yaml, a small hand-maintained table.

Caveat: Eid al-Fitr and Eid al-Adha follow the lunar Hijri calendar, so
their Gregorian dates shift every year — both the `holidays` package and
festivals_static.yaml need periodic review to stay accurate more than a
few years out.
"""
import os
from datetime import date, timedelta

import yaml

_STATIC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", "festivals_static.yaml")


def _from_holidays_package(check_date: date):
    try:
        import holidays
    except ImportError:
        return None

    hits = []

    try:
        in_categories = getattr(holidays, "HINDU", None), getattr(holidays, "ISLAMIC", None)
        in_categories = tuple(c for c in in_categories if c)
        india = holidays.India(years=check_date.year, categories=in_categories) if in_categories else holidays.India(years=check_date.year)
    except TypeError:
        india = holidays.India(years=check_date.year)
    except Exception:
        india = {}

    try:
        us = holidays.US(years=check_date.year)
    except Exception:
        us = {}

    if check_date in india:
        hits.append(("India", india.get(check_date)))
    if check_date in us:
        hits.append(("US", us.get(check_date)))

    return hits or None


def _from_static_table(check_date: date):
    try:
        with open(_STATIC_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return None

    key = check_date.isoformat()
    entries = data.get(key, [])
    if not entries:
        return None
    return [(e.get("country", "India"), e.get("name", "")) for e in entries]


def get_festival_for_date(check_date: date):
    """Returns a list of (country, festival_name) tuples for the given
    date, or None if it isn't a tracked festival/holiday."""
    hits = _from_holidays_package(check_date)
    if hits:
        return hits
    return _from_static_table(check_date)


def get_upcoming_festival():
    """Checks today, then tomorrow, for a tracked India/US festival or
    national holiday. Returns a dict {when, country, name} for the first
    match found, or None if neither day has one."""
    today = date.today()
    for label, d in (("today", today), ("tomorrow", today + timedelta(days=1))):
        hits = get_festival_for_date(d)
        if hits:
            country, name = hits[0]
            return {"when": label, "date": d.isoformat(), "country": country, "name": name}
    return None
