"""Silence Alert: noticing when a senior who lives alone may need a knock. (Person 4 owns this.)

Small signals, no cameras: a missed daily "I'm okay" tap, a neighbour tapping
"haven't seen Mr Lim", (later) uncollected meals. Code scores them; at amber the
escalation ladder starts, and A PERSON APPROVES EVERY NEXT STEP:

    1. gentle reminder to the senior
    2. a trusted nearby neighbour is asked to knock
    3. an RC volunteer or befriender visits
    4. a welfare check by the authorities

Goal: cut "days or weeks" to "within 24 hours".
"""

from datetime import datetime, timedelta, timezone

from sqlmodel import select

from .db import get_session
from .live import hub
from .models import Event, Helper, Resident, SilenceCase, now
from .risk import floor_of

LADDER = [
    "Gentle reminder to check in",
    "Ask a nearby neighbour to knock",
    "RC volunteer or befriender visits",
    "Welfare check by the authorities",
]


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def signals_for(resident: Resident, at: datetime | None = None) -> tuple[int, int]:
    """(days since last check-in, neighbour 'haven't seen' taps in the last 3 days)."""
    at = at or now()
    with get_session() as s:
        events = s.exec(select(Event).where(Event.type.in_(["checkin", "not_seen"]))).all()
    checkins = [_aware(e.created_at) for e in events if e.type == "checkin" and e.details.get("resident_id") == resident.id]
    last = max(checkins) if checkins else None
    # A tap only counts if it came after the senior's last check-in, within 3 days.
    taps = [
        e
        for e in events
        if e.type == "not_seen"
        and e.details.get("unit") == resident.unit
        and at - _aware(e.created_at) <= timedelta(days=3)
        and (last is None or _aware(e.created_at) > last)
    ]
    days = (at - last).days if last else 1  # never checked in: treat as 1 missed day
    return days, len({e.details.get("reporter_id") for e in taps})


def score(days_missed: int, taps: int) -> tuple[str, list[str]]:
    signals = []
    if days_missed >= 1:
        signals.append(f"no check-in for {days_missed} day{'s' if days_missed > 1 else ''}")
    if taps:
        signals.append(f"{taps} neighbour{'s' if taps > 1 else ''}: haven't seen")
    if days_missed >= 3 or taps >= 2:
        return "red", signals
    if days_missed >= 2 or taps >= 1:
        return "amber", signals
    if days_missed >= 1:
        return "watch", signals
    return "clear", signals


def case_out(c: SilenceCase) -> dict:
    with get_session() as s:
        r = s.get(Resident, c.resident_id)
    return {
        "id": c.id,
        "resident_id": c.resident_id,
        "name": r.name if r else c.resident_id,
        "unit": r.unit if r else None,
        "level": c.level,
        "signals": c.signals,
        "step": c.step,
        "step_label": LADDER[c.step] if c.step < len(LADDER) else None,
        "ladder": LADDER,
        "status": c.status,
        "outcome": c.outcome,
        "neighbour": nearest_neighbour(r) if r else None,
    }


def nearest_neighbour(resident: Resident) -> dict | None:
    """A nearby helper (by floor) who isn't the resident."""
    with get_session() as s:
        helpers = {h.resident_id for h in s.exec(select(Helper)).all()}
        people = s.exec(select(Resident).where(Resident.block_id == resident.block_id)).all()
    options = [(abs(floor_of(p.unit) - floor_of(resident.unit)), p) for p in people if p.id in helpers and p.id != resident.id]
    if not options:
        return None
    p = min(options, key=lambda x: x[0])[1]
    return {"id": p.id, "name": p.name, "unit": p.unit}


async def check_all(block_id: int = 123) -> list[dict]:
    """Score every opted-in senior; open (or update) a case when they reach amber."""
    with get_session() as s:
        seniors = s.exec(select(Resident).where(Resident.block_id == block_id, Resident.silence_opt_in == True)).all()  # noqa: E712
    changed = []
    for r in seniors:
        days, taps = signals_for(r)
        level, signals = score(days, taps)
        with get_session() as s:
            case = s.exec(select(SilenceCase).where(SilenceCase.resident_id == r.id, SilenceCase.status == "open")).first()
            if level in {"amber", "red"}:
                if case is None:
                    case = SilenceCase(resident_id=r.id, level=level, signals=signals)
                else:
                    case.level, case.signals, case.updated_at = level, signals, now()
                s.add(case)
                s.commit()
                s.refresh(case)
                changed.append(case_out(case))
            elif case is not None and level == "clear":
                case.status, case.outcome = "resolved", "checked in"
                s.add(case)
                s.commit()
                s.refresh(case)
                changed.append(case_out(case))
    for c in changed:
        await hub.broadcast({"type": "silence_case", "case": c})
    return changed


async def approve_next(case_id: int) -> dict:
    """A person approves the next step of the ladder."""
    with get_session() as s:
        case = s.get(SilenceCase, case_id)
        if case is None:
            raise KeyError(case_id)
        if case.step < len(LADDER) - 1:
            case.step += 1
        case.updated_at = now()
        s.add(case)
        s.add(Event(type="silence_step", details={"case_id": case_id, "step": LADDER[case.step], "approved_by": "official (dashboard)"}))
        s.commit()
        s.refresh(case)
        out = case_out(case)
    await hub.broadcast({"type": "silence_case", "case": out})
    if out["step"] == 1 and out["neighbour"]:
        # Ask the nearby neighbour (on their phone) to knock.
        await hub.broadcast({"type": "knock_request", "case": out, "helper_id": out["neighbour"]["id"]})
    return out


async def resolve(case_id: int, outcome: str) -> dict:
    """The neighbour reports back. 'okay' closes the case; 'no answer' moves up the ladder."""
    with get_session() as s:
        case = s.get(SilenceCase, case_id)
        if case is None:
            raise KeyError(case_id)
        if outcome == "okay":
            case.status, case.outcome = "resolved", "neighbour knocked: he's okay"
        else:
            case.outcome = "neighbour knocked: no answer"
            case.level = "red"
        case.updated_at = now()
        s.add(case)
        s.add(Event(type="silence_outcome", details={"case_id": case_id, "outcome": outcome}))
        s.commit()
        s.refresh(case)
        out = case_out(case)
    await hub.broadcast({"type": "silence_case", "case": out})
    return out


def open_cases() -> list[dict]:
    with get_session() as s:
        cases = s.exec(select(SilenceCase).order_by(SilenceCase.id.desc())).all()
    return [case_out(c) for c in cases]


def backdate_checkin(resident_id: str, days_ago: int) -> None:
    """Demo only: pretend the senior's last check-in was some days ago."""
    with get_session() as s:
        r = s.get(Resident, resident_id)
        s.add(Event(block_id=r.block_id, type="checkin", details={"resident_id": resident_id, "unit": r.unit}, created_at=now() - timedelta(days=days_ago)))
        s.commit()
