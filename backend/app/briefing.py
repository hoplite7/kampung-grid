"""The SCDF handover brief and the after-action report. (Person 1 owns this.)

Code gathers the facts (who's reached, who isn't, what was caught); Claude only
turns them into a page an officer can read in seconds, most urgent first.
"""

import asyncio
from datetime import timezone

from sqlmodel import select

from . import ai, vault
from .crisis import current_incident, family_cover, rank
from .db import get_session
from .models import Block, Incident, Report, Resident, Rumour, Task, now


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _need_line(view: dict) -> str:
    bits = []
    if view.get("powered_equipment"):
        bits.append(view["powered_equipment"] + (f" (~{view['equipment_battery_hours']}h battery)" if view.get("equipment_battery_hours") else ""))
    if view.get("mobility"):
        bits.append(f"{view['mobility']} user")
    if view.get("hearing"):
        bits.append(view["hearing"])
    return ", ".join(bits)


def handover_facts(block_id: int, demo_time: str = "9:24pm") -> dict:
    incident = current_incident(block_id)
    if incident is None:
        raise ValueError("No active incident")
    with get_session() as s:
        block = s.get(Block, block_id)
        tasks = s.exec(select(Task).where(Task.incident_id == incident.id).order_by(Task.id)).all()
        names = {r.id: r for r in s.exec(select(Resident).where(Resident.block_id == block_id)).all()}
        fake = s.exec(select(Report).where(Report.block_id == block_id, Report.status == "rejected")).all()
        rumours = s.exec(select(Rumour).where(Rumour.block_id == block_id, Rumour.status == "answered")).all()

    latest = {}
    for t in tasks:
        latest[t.resident_id] = t
    reached, not_reached = [], []
    for item in rank(block_id):
        t = latest.get(item["resident_id"])
        try:
            view = vault.open_for_responder(item["resident_id"], incident.id, "SCDF (handover brief)")
        except vault.VaultLocked:
            view = {}
        person = {
            "name": item["name"],
            "unit": item["unit"],
            "need": _need_line(view),
            "helper": (names[t.helper_id].name if t and t.helper_id in names else (t.responder if t else None)),
            "attention": bool(view.get("powered_equipment")) or "wheelchair" in str(view.get("mobility", "")).lower(),
        }
        if t and t.status == "reached":
            reached.append(person)
        else:
            status = {
                "sent": "helper alerted, no response yet",
                "on_the_way": "helper on the way",
                "escalated": "no neighbour available",
                "need_help": "helper asked for help",
                "responder_en_route": "responders on the way",
                "reassigned": "helper did not respond, reassigned",
            }.get(t.status if t else "", "not yet assigned")
            person.pop("attention", None)
            not_reached.append({**person, "status": status})
    return {
        "block": block.name,
        "time": demo_time,
        "vulnerable": len(reached) + len(not_reached),
        "reached_count": len(reached),
        # Only reached people an officer still has to act on (e.g. oxygen on a battery).
        "reached_needing_attention": [p for p in reached if p.pop("attention", False)],
        "not_reached": not_reached,
        "fake_reports_rejected": len(fake),
        "rumours_answered": [r.claim for r in rumours],
        "family_cover": family_cover(block_id),
    }


async def handover_brief(block_id: int) -> dict:
    facts = handover_facts(block_id)
    result = await asyncio.to_thread(ai.write_handover_brief, facts)
    return {**result, "facts": facts, "created_at": now()}


def after_action(block_id: int) -> dict:
    """What happened, measured: the REAL time to last knock in this incident."""
    incident = current_incident(block_id)
    if incident is None:
        with get_session() as s:
            incident = s.exec(select(Incident).where(Incident.block_id == block_id).order_by(Incident.id.desc())).first()
    if incident is None:
        raise ValueError("No incident yet")
    with get_session() as s:
        tasks = s.exec(select(Task).where(Task.incident_id == incident.id)).all()
        fake = s.exec(select(Report).where(Report.block_id == block_id, Report.status == "rejected")).all()
        rumours = s.exec(select(Rumour).where(Rumour.block_id == block_id, Rumour.status == "answered")).all()
    latest = {}
    for t in sorted(tasks, key=lambda t: t.id):
        latest[t.resident_id] = t
    first_alert = min((_aware(t.created_at) for t in tasks), default=None)
    reached_times = [_aware(t.updated_at) for t in latest.values() if t.status == "reached"]
    measured = None
    if first_alert and reached_times and len(reached_times) == len(latest):
        measured = round((max(reached_times) - first_alert).total_seconds() / 60, 1)
    return {
        "block_id": block_id,
        "vulnerable": len(latest),
        "reached": len(reached_times),
        "measured_minutes": measured,  # None if someone still isn't reached
        "reassigned": sum(1 for t in tasks if t.status == "reassigned"),
        "fake_reports_rejected": len(fake),
        "rumours_answered": len(rumours),
        "family_cover": family_cover(block_id),
        "note": "Demo times are compressed: neighbours in the demo respond within seconds.",
    }
