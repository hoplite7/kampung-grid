"""The trust check: how much can we trust a report? (Person 1 owns this.)

Attackers may send fake reports ("Auntie at 14-03 collapsed, come quick!") to pull
helpers away, waste responders' time, or lure someone somewhere unsafe.

1. Code collects hard FACTS: who sent it, does anyone confirm it, is the unit
   occupied, is one sender flooding us with reports?
2. Code turns the facts into a starting level: High, Medium or Low.
3. Claude reads the wording and may LOWER the level by one step (e.g. it looks
   copied or like a lure). It can never RAISE it: hard facts always stand.

Low trust is never thrown away: it waits for a human on the dashboard.
"""

from datetime import timedelta

from sqlmodel import select

from . import ai
from .db import get_session
from .models import Report, Resident, Unit

LEVELS = ["low", "medium", "high"]
CONFIRM_WINDOW = timedelta(minutes=10)
BURST_WINDOW = timedelta(minutes=5)
BURST_COUNT = 3


def _aware(dt):
    from datetime import timezone

    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def collect_facts(report: Report) -> dict:
    parsed = report.parsed or {}
    unit_label = parsed.get("unit")
    with get_session() as s:
        residents = s.exec(select(Resident).where(Resident.block_id == report.block_id)).all()
        reports = s.exec(select(Report).where(Report.block_id == report.block_id, Report.id != report.id)).all()
        unit = s.get(Unit, f"{report.block_id}-{unit_label}") if unit_label else None

    phones = {r.phone: r.id for r in residents}
    ids = {r.id for r in residents}
    sender = report.sender_id if report.sender_id in ids else phones.get(report.sender_phone or "")
    created = _aware(report.created_at)

    confirmations = {
        (r.sender_id or r.sender_phone)
        for r in reports
        if r.parsed
        and r.parsed.get("unit") == unit_label
        and unit_label
        and r.status != "rejected"
        and (r.sender_id or r.sender_phone) != (report.sender_id or report.sender_phone)
        and abs(_aware(r.created_at) - created) <= CONFIRM_WINDOW
    }
    same_sender_recent = sum(
        1
        for r in reports
        if (r.sender_id or r.sender_phone) == (report.sender_id or report.sender_phone)
        and abs(_aware(r.created_at) - created) <= BURST_WINDOW
    )
    resident_here = any(r.unit == unit_label for r in residents) if unit_label else None

    return {
        "known_sender": sender is not None,
        "confirmations": len(confirmations),
        "unit": unit_label,
        "unit_occupied": (unit.occupied if unit else None),
        "resident_listed": resident_here,
        "sender_recent_reports": same_sender_recent + 1,
    }


def starting_level(facts: dict) -> tuple[str, list[str]]:
    points, reasons = 0, []

    if facts["known_sender"]:
        points += 2
        reasons.append("known resident")
    else:
        points -= 1
        reasons.append("unknown sender")

    if facts["confirmations"] >= 1:
        points += 2
        n = facts["confirmations"]
        reasons.append(f"confirmed by {n} other neighbour{'s' if n > 1 else ''}")
    elif facts["unit"]:
        reasons.append("no second report")

    if facts["unit"]:
        if facts["unit_occupied"] is False:
            points -= 2
            reasons.append(f"unit {facts['unit']} is vacant")
        elif facts["resident_listed"]:
            points += 1
            reasons.append("resident lives there")

    if facts["sender_recent_reports"] >= BURST_COUNT:
        points -= 2
        reasons.append(f"{facts['sender_recent_reports']} reports from one sender in 5 min")

    level = "high" if points >= 2 else "medium" if points >= 0 else "low"
    return level, reasons


def check(report: Report) -> tuple[str, list[str]]:
    """Return (level, reasons) for a report whose AI reading (parsed) is done."""
    facts = collect_facts(report)
    level, reasons = starting_level(facts)
    review = ai.review_trust(report.text, facts)
    if review.get("more_suspicious") and level != "low":
        level = LEVELS[LEVELS.index(level) - 1]  # lower by one step, never more
        if review.get("reason"):
            reasons.append(f"AI: {review['reason']}")
    return level, reasons
