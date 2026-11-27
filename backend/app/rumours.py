"""Rumour detection: the second wave of a hybrid attack. (Person 1 owns this.)

During an outage, a false claim ("the tap water is contaminated!") can spread fast.
The AI spots the same claim repeated across several messages and flags it.
It never decides what is true: an official approves the verified answer, which is
then sent to residents THROUGH A NEIGHBOUR THEY KNOW (people trust a familiar
name more than a stranger's broadcast).
"""

from datetime import timedelta, timezone

from sqlmodel import select

from . import ai
from .db import get_session
from .live import hub
from .models import Event, Helper, Report, Resident, Rumour, now
from .risk import floor_of

WINDOW = timedelta(minutes=15)


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def rumour_out(r: Rumour) -> dict:
    return {
        "id": r.id,
        "block_id": r.block_id,
        "claim": r.claim,
        "count": r.count,
        "report_ids": r.report_ids,
        "status": r.status,
        "verified_answer": r.verified_answer,
        "source": r.source,
        "created_at": _aware(r.created_at),
    }


async def check(block_id: int) -> None:
    """Look at the last 15 minutes of messages for a claim repeated 3+ times."""
    import asyncio

    cutoff = now() - WINDOW
    with get_session() as s:
        reports = [
            r
            for r in s.exec(select(Report).where(Report.block_id == block_id).order_by(Report.id)).all()
            if r.parsed and r.status != "rejected" and _aware(r.created_at) >= cutoff
        ]
        open_rumour = s.exec(select(Rumour).where(Rumour.block_id == block_id, Rumour.status == "flagged")).first()
    if len(reports) < 3:
        return

    result = await asyncio.to_thread(ai.find_rumour, [r.text for r in reports])
    if not result.get("found"):
        return
    ids = [reports[n - 1].id for n in result["message_numbers"] if 1 <= n <= len(reports)]

    with get_session() as s:
        if open_rumour:
            rumour = s.get(Rumour, open_rumour.id)
            if set(ids) <= set(rumour.report_ids):
                return  # nothing new
            rumour.report_ids = sorted(set(rumour.report_ids) | set(ids))
            rumour.count = len(rumour.report_ids)
            kind = "rumour_updated"
        else:
            rumour = Rumour(
                block_id=block_id, claim=result["claim"], count=len(ids), report_ids=ids, source=result["source"]
            )
            kind = "rumour_flagged"
        s.add(rumour)
        s.add(Event(block_id=block_id, type=kind, details={"claim": rumour.claim, "count": rumour.count}))
        s.commit()
        s.refresh(rumour)
        out = rumour_out(rumour)
    await hub.broadcast({"type": kind, "rumour": out})


def _messenger_for(resident: Resident, helpers: list[tuple[Resident, Helper]]) -> str | None:
    """The nearest helper (by floor) who isn't the resident themselves."""
    candidates = [(abs(floor_of(p.unit) - floor_of(resident.unit)), p.name) for p, _ in helpers if p.id != resident.id]
    return min(candidates)[1] if candidates else None


async def approve(rumour_id: int, answer: str) -> dict:
    """An official confirms the facts. The answer goes out via familiar neighbours."""
    with get_session() as s:
        rumour = s.get(Rumour, rumour_id)
        if rumour is None:
            raise KeyError(rumour_id)
        rumour.status = "answered"
        rumour.verified_answer = answer
        s.add(rumour)
        s.add(Event(block_id=rumour.block_id, type="rumour_answered", details={"claim": rumour.claim, "answer": answer}))
        s.commit()
        s.refresh(rumour)
        out = rumour_out(rumour)
        residents = s.exec(select(Resident).where(Resident.block_id == rumour.block_id)).all()
        helper_rows = {h.resident_id: h for h in s.exec(select(Helper)).all()}
    helpers = [(r, helper_rows[r.id]) for r in residents if r.id in helper_rows]
    via = {r.id: _messenger_for(r, helpers) for r in residents}
    await hub.broadcast({"type": "verified_message", "rumour": out, "answer": answer, "via": via})
    await hub.broadcast({"type": "rumour_updated", "rumour": out})
    return out


async def dismiss(rumour_id: int) -> dict:
    with get_session() as s:
        rumour = s.get(Rumour, rumour_id)
        if rumour is None:
            raise KeyError(rumour_id)
        rumour.status = "dismissed"
        s.add(rumour)
        s.commit()
        s.refresh(rumour)
        out = rumour_out(rumour)
    await hub.broadcast({"type": "rumour_updated", "rumour": out})
    return out
