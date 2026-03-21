"""Custody schedule calculator — Friday-to-Friday alternating weeks."""

from datetime import date, datetime, timedelta
from typing import Optional

from config import ACE_ON_WEEK_ANCHOR, TIMEZONE


def _parse_anchor() -> date:
    return date.fromisoformat(ACE_ON_WEEK_ANCHOR)


def get_week_status(target_date: Optional[date] = None) -> dict:
    """Determine custody week status for a given date.

    ACE_ON_WEEK_ANCHOR is a known Friday when an ON week starts.
    Weeks run Friday-to-Thursday (7 days).
    Even weeks from anchor = ON (Ace with Joey), odd = OFF.

    Returns dict with:
        is_on_week, week_label, week_start, week_end,
        days_remaining, controlling_parent
    """
    if target_date is None:
        target_date = date.today()

    anchor = _parse_anchor()
    delta_days = (target_date - anchor).days

    # Find which week we're in (weeks start on Friday)
    # Shift so that Friday = day 0 of each week
    # anchor is a Friday, so delta_days=0 is Friday of week 0
    week_number = delta_days // 7
    day_in_week = delta_days % 7

    # Handle dates before anchor
    if delta_days < 0:
        week_number = (delta_days - 6) // 7  # floor division for negatives
        day_in_week = delta_days - (week_number * 7)

    is_on_week = (week_number % 2) == 0

    # Week boundaries
    week_start = target_date - timedelta(days=day_in_week)
    week_end = week_start + timedelta(days=6)
    days_remaining = (week_end - target_date).days

    controlling_parent = "parent_a" if is_on_week else "parent_b"
    week_label = "Joey's week" if is_on_week else "Christina's week"

    return {
        "is_on_week": is_on_week,
        "week_label": week_label,
        "week_start": week_start,
        "week_end": week_end,
        "days_remaining": days_remaining,
        "controlling_parent": controlling_parent,
    }


def get_controlling_parent(target_date: Optional[date] = None) -> str:
    """Return which parent has custody ('parent_a' or 'parent_b')."""
    return get_week_status(target_date)["controlling_parent"]
