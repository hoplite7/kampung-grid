"""The crisis engine: the step-by-step brain of crisis mode. (Person 1 owns this.)

    start_incident  -> crisis mode on (power out, lifts down)
    rank            -> who needs a knock first, and why (uses risk.py)
    match           -> the nearest suitable helper who is home and free
    assign          -> create tasks, ask Claude to write each helper's instructions
    escalation      -> if a helper doesn't respond in time, ask the next-best one;
                       if nobody is left, escalate to official services
    simulation      -> fictional neighbours respond on their own, so the block comes
                       alive in the demo. Only "featured" helpers (real phones) wait for a tap.

Rule: code decides (predictable, same answer every rehearsal);
Claude reads messy reports and writes the instructions.
"""

import asyncio
import os
import random
from typing import Optional

from sqlmodel import select

from . import ai, vault
from .db import get_session
from . import people
from .live import hub
from .models import Event, Helper, Incident, Report, Resident, Task, Unit, now
from .risk import Conditions, floor_of, risk_score

# ---- Settings (override in .env) -------------------------------------------
ESCALATE_SECONDS = float(os.getenv("KG_ESCALATE_SECONDS", "90"))
# Real phones in the demo get longer, so a rehearsal isn't spoiled by a slow tap.
FEATURED_ESCALATE_SECONDS = float(os.getenv("KG_FEATURED_ESCALATE_SECONDS", "300"))
# Helpers whose phones are real in the demo; everyone else is simulated.
FEATURED_HELPERS = {h.strip() for h in os.getenv("KG_FEATURED_HELPERS", "aziz").split(",") if h.strip()}
SIMULATE_NEIGHBOURS = os.getenv("KG_SIMULATE_NEIGHBOURS", "true").lower() == "true"
# Simulated neighbours who never answer, so the demo has someone still "not reached"
# when SCDF arrives (Mr Rajan's helper by default). Empty it to have everyone answer.
SIM_NO_RESPONSE = {h.strip() for h in os.getenv("KG_SIM_NO_RESPONSE", "nurul").split(",") if h.strip()}
# Residents no simulated neighbour ever reaches, however slowly the demo runs: every helper
# asked "doesn't answer", so they're still NOT REACHED when SCDF arrives. Empty = everyone reachable.
SIM_UNREACHED = {r.strip() for r in os.getenv("KG_SIM_UNREACHED", "rajan").split(",") if r.strip()}
# The demo is set at 9pm, which decides which helpers are home.
DEMO_TIME = os.getenv("KG_DEMO_TIME", "21:00")

OPEN_STATUSES = {"sent", "on_the_way", "responder_en_route"}

# ---- Background jobs (cancelled on Reset) -----------------------------------
_jobs: set[asyncio.Task] = set()


def spawn(coro) -> None:
    job = asyncio.create_task(coro)
    _jobs.add(job)
    job.add_done_callback(_jobs.discard)


def cancel_all() -> None:
    for job in list(_jobs):
        job.cancel()
    _jobs.clear()


# ---- Small helpers ------------------------------------------------------------


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def is_home(home_hours: list[str], at: str = DEMO_TIME) -> bool:
    """'18:00-08:00' wraps past midnight. '00:00-24:00' means always."""
    t = _minutes(at)
    for span in home_hours:
        start, end = (_minutes(x) for x in span.split("-"))
        if start <= end:
            if start <= t < end:
                return True
        elif t >= start or t < end:  # wraps past midnight
            return True
    return False


def unit_number(unit: str) -> int:
    return int(unit.lstrip("#").split("-")[1])


def stairwell_for(block_stairwells: dict, unit: str) -> str:
    n = unit_number(unit)
    for name, nums in block_stairwells.items():
        if n in nums:
            return name
    return "A"


def log_event(block_id: int, type_: str, details: dict) -> None:
    with get_session() as s:
        s.add(Event(block_id=block_id, type=type_, details=details))
        s.commit()


# ---- Incidents ---------------------------------------------------------------


def current_incident(block_id: int) -> Optional[Incident]:
    with get_session() as s:
        return s.exec(
            select(Incident).where(Incident.block_id == block_id, Incident.status == "active").order_by(Incident.id.desc())
        ).first()


async def start_incident(block_id: int, type_: str = "blackout", cause: str = "grid cyberattack") -> Incident:
    existing = current_incident(block_id)
    if existing:
        return existing
    with get_session() as s:
        incident = Incident(block_id=block_id, type=type_, cause=cause)
        s.add(incident)
        s.commit()
        s.refresh(incident)
    log_event(block_id, "incident_started", {"incident_id": incident.id, "cause": cause})
    await hub.broadcast(
        {
            "type": "incident",
            "status": "active",
            "incident_id": incident.id,
            "block_id": block_id,
            "cause": cause,
            "power_out": True,
            "lifts_down": True,
        }
    )
    return incident


# ---- Ranking -----------------------------------------------------------------


def rank(block_id: int) -> list[dict]:
    """Every vulnerable resident, most urgent first, with the reasons."""
    incident = current_incident(block_id)
    with get_session() as s:
        residents = s.exec(select(Resident).where(Resident.block_id == block_id)).all()
        # Filter in Python: a JSON column stores Python None as JSON null, not SQL NULL.
        reports = [r for r in s.exec(select(Report).where(Report.block_id == block_id)).all() if r.parsed]
        tasks = s.exec(select(Task).where(Task.incident_id == (incident.id if incident else -1))).all()

    reached = {t.resident_id for t in tasks if t.status == "reached"}
    by_resident: dict[str, list] = {}
    for r in reports:
        if r.resident_id and r.status not in {"rejected", "waiting_for_human"}:
            by_resident.setdefault(r.resident_id, []).append(r.parsed)

    if incident is None:
        return []  # profiles can only be opened during an active incident

    ranked = []
    for res in residents:
        if not res.has_profile:
            continue
        try:
            profile = vault.open_for_engine(res.id, incident.id)
        except vault.VaultLocked:
            continue
        cond = Conditions(
            power_out=incident is not None,
            lifts_down=incident is not None,
            reports=by_resident.get(res.id, []),
        )
        score, reasons = risk_score(profile, res.unit, cond)
        ranked.append(
            {"resident_id": res.id, "name": res.name, "unit": res.unit, "score": score, "reasons": reasons, "reached": res.id in reached}
        )
    ranked.sort(key=lambda x: (-x["score"], x["unit"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


# ---- Matching ----------------------------------------------------------------


def _busy_helpers(incident_id: int) -> set[str]:
    with get_session() as s:
        tasks = s.exec(select(Task).where(Task.incident_id == incident_id)).all()
    return {t.helper_id for t in tasks if t.helper_id and t.status in OPEN_STATUSES}


def match_helper(block_id: int, resident: Resident, incident_id: int, exclude: set[str] = frozenset()) -> Optional[dict]:
    """Nearest available helper. Lower cost = better.

    cost = floors apart + 3 if a different stairwell - 2 if they have first-aid/CPR
           and the resident needs powered equipment (or -1 for any trained helper).
    Essential workers aren't asked: they're reporting for duty.
    """
    with get_session() as s:
        from .models import Block

        block = s.get(Block, block_id)
        helpers = s.exec(select(Helper)).all()
        residents = {r.id: r for r in s.exec(select(Resident).where(Resident.block_id == block_id)).all()}

    busy = _busy_helpers(incident_id) | set(exclude)
    target_floor = floor_of(resident.unit)
    target_stair = stairwell_for(block.stairwells, resident.unit)
    try:
        profile = vault.open_for_engine(resident.id, incident_id)
    except vault.VaultLocked:
        profile = {}
    needs_trained = bool(profile.get("powered_equipment"))

    best, best_cost = None, None
    for h in helpers:
        person = residents.get(h.resident_id)
        if person is None or h.resident_id in busy or person.is_essential_worker:
            continue
        if not is_home(h.home_hours):
            continue
        trained = bool({"cpr", "first_aid"} & set(h.skills))
        cost = abs(floor_of(person.unit) - target_floor)
        cost += 3 if stairwell_for(block.stairwells, person.unit) != target_stair else 0
        cost -= (2 if needs_trained else 1) if trained else 0
        if best_cost is None or cost < best_cost:
            best, best_cost = (h, person), cost

    if best is None:
        return None
    h, person = best
    return {
        "helper_id": h.resident_id,
        "name": person.name,
        "unit": person.unit,
        "language": (h.languages or [person.language])[0],
        "skills": h.skills,
        "stairwell": target_stair,
    }


# ---- Tasks -------------------------------------------------------------------


def task_out(task: Task) -> dict:
    """The shape screens receive for a task (see docs/api.md)."""
    from datetime import timezone

    with get_session() as s:
        resident = s.get(Resident, task.resident_id)
        helper = s.get(Resident, task.helper_id) if task.helper_id else None
    created = task.created_at.replace(tzinfo=timezone.utc) if task.created_at.tzinfo is None else task.created_at
    return {
        "id": task.id,
        "incident_id": task.incident_id,
        "rank": task.rank,
        "score": task.score,
        "reasons": task.reasons,
        "resident_id": task.resident_id,
        "resident_name": resident.name if resident else None,
        "resident_unit": resident.unit if resident else None,
        "helper_id": task.helper_id,
        "helper_name": helper.name if helper else None,
        "helper_unit": helper.unit if helper else None,
        "instructions": task.instructions,
        "channel": task.channel,
        "status": task.status,
        "simulated": task.simulated,
        # How a real person is taking part: "telegram", "web" (joined by QR) or "presenter".
        "via": people.CLAIMS.get(task.helper_id) or ("presenter" if task.helper_id in FEATURED_HELPERS else None),
        "responder": task.responder,
        "family_of": task.family_of,
        "created_at": created,
    }


async def _set_unit_status(block_id: int, unit_label: str, status: str) -> None:
    with get_session() as s:
        unit = s.get(Unit, f"{block_id}-{unit_label}")
        if unit is None:
            return
        unit.status = status
        s.add(unit)
        s.commit()
    await hub.broadcast({"type": "unit_status", "block_id": block_id, "unit": unit_label, "status": status})


async def assign_all(block_id: int) -> list[dict]:
    """Create a task for every vulnerable resident who doesn't have one yet,
    most urgent first, each with the best free helper."""
    incident = current_incident(block_id)
    if incident is None:
        raise ValueError("No active incident: press Cyberattack first")

    with get_session() as s:
        open_or_done = {
            t.resident_id
            for t in s.exec(select(Task).where(Task.incident_id == incident.id)).all()
            if t.status in OPEN_STATUSES | {"reached"}
        }

    created = []
    for item in rank(block_id):
        if item["resident_id"] in open_or_done or item["score"] == 0:
            continue
        task = await _create_task(block_id, incident.id, item)
        created.append(task)
    log_event(block_id, "assigned", {"tasks": [t["id"] for t in created]})
    return created


async def test_job(block_id: int, helper_id: str) -> dict | None:
    """Send one practice job to a real person who joined, without running the demo beats.

    Picks the most urgent resident who isn't reached yet. Returns the new task, or None
    if that helper can't take one (e.g. not home at the demo time)."""
    incident = current_incident(block_id) or await start_incident(block_id, "blackout", "grid cyberattack")
    with get_session() as s:
        all_helpers = {h.resident_id for h in s.exec(select(Helper)).all()}
        open_task = s.exec(
            select(Task).where(Task.incident_id == incident.id, Task.helper_id == helper_id, Task.status.in_(["sent", "on_the_way"]))
        ).first()
    if open_task:
        return task_out(open_task)  # they already have a job
    # Mdm Tan is kept for the presenter's phone (her "reached" moment is the pitch's climax).
    ranked = [r for r in rank(block_id) if r["resident_id"] != "tan"]
    candidates = [r for r in ranked if not r["reached"]] or ranked
    if not candidates:
        return None
    with get_session() as s:
        me = s.get(Resident, helper_id)
    # The nearest resident to the judge, so the job feels like a real neighbour's.
    item = min(candidates, key=lambda r: (abs(floor_of(r["unit"]) - floor_of(me.unit)), r["rank"]))
    with get_session() as s:
        resident = s.get(Resident, item["resident_id"])
    if match_helper(block_id, resident, incident.id, all_helpers - {helper_id}) is None:
        return None
    return await _create_task(block_id, incident.id, item, exclude=all_helpers - {helper_id})


async def _create_task(block_id: int, incident_id: int, item: dict, exclude: set[str] = frozenset()) -> dict:
    with get_session() as s:
        resident = s.get(Resident, item["resident_id"])
    helper = match_helper(block_id, resident, incident_id, exclude)

    # Family cover: is this resident an essential worker's family member?
    with get_session() as s:
        worker = s.exec(
            select(Resident).where(
                Resident.block_id == block_id, Resident.is_essential_worker == True, Resident.dependent_unit == resident.unit  # noqa: E712
            )
        ).first()
    family_of = worker.id if worker else None

    with get_session() as s:
        task = Task(
            incident_id=incident_id,
            family_of=family_of,
            resident_id=resident.id,
            helper_id=helper["helper_id"] if helper else None,
            rank=item["rank"],
            score=item["score"],
            reasons=item["reasons"],
            status="sent" if helper else "escalated",
            simulated=bool(helper) and not people.is_real(helper["helper_id"]),
        )
        s.add(task)
        s.commit()
        s.refresh(task)
        out = task_out(task)

    await hub.broadcast({"type": "task_new", "task": out})
    await _set_unit_status(block_id, resident.unit, "task_sent" if helper else "escalated")

    if family_of:
        await _family_update(out, "on_the_way" if helper else "escalated")

    if helper:
        spawn(_write_instructions(task.id, block_id, helper))
        wait = ESCALATE_SECONDS if out["simulated"] else FEATURED_ESCALATE_SECONDS
        spawn(_escalation_watch(task.id, block_id, wait))
        if out["simulated"] and SIMULATE_NEIGHBOURS:
            spawn(_simulate_neighbour(task.id))
    else:
        log_event(block_id, "escalated", {"resident_id": resident.id, "reason": "no helper available"})
    return out


async def _write_instructions(task_id: int, block_id: int, helper: dict) -> None:
    """Background: Claude writes the helper's card in their language."""
    with get_session() as s:
        task = s.get(Task, task_id)
        resident = s.get(Resident, task.resident_id)
        report = next(
            (r for r in s.exec(select(Report).where(Report.resident_id == resident.id).order_by(Report.id.desc())).all() if r.parsed),
            None,
        )
    concern = report.parsed.get("concern") if report else None

    # Open the Sealed Profile for THIS helper only: needs the incident key (active
    # incident) and that the helper is assigned. They get the need-to-know view.
    try:
        needs, log_entry = vault.open_for_helper(resident.id, task.incident_id, helper["helper_id"])
    except vault.VaultLocked as exc:
        print(f"[vault] {exc}")
        needs, log_entry = {}, None
    if log_entry:
        await hub.broadcast(
            {
                "type": "profile_unlocked",
                "task_id": task_id,
                "resident_id": resident.id,
                "helper_id": helper["helper_id"],
                "keys": {"incident": True, "assigned": True},
                "log": log_entry,
            }
        )

    instructions = await asyncio.to_thread(
        ai.write_instruction,
        resident.name,
        resident.unit,
        needs,
        helper["name"],
        helper["language"],
        helper["skills"],
        helper["stairwell"],
        True,
        concern,
    )
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None:
            return
        task.instructions = instructions
        task.updated_at = now()
        s.add(task)
        s.commit()
        s.refresh(task)
        out = task_out(task)
        incident = s.get(Incident, task.incident_id)
        mode = incident.mode if incident else "full"
    await hub.broadcast({"type": "task_updated", "task": out})
    if mode != "full":
        from .messaging import deliver

        await deliver(out, mode)  # e.g. as an SMS when mobile data is down


async def set_task_status(task_id: int, status: str) -> dict:
    """A helper taps a button (or a simulated neighbour 'taps' it)."""
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None:
            raise KeyError(task_id)
        task.status = status
        task.updated_at = now()
        s.add(task)
        s.commit()
        s.refresh(task)
        incident = s.get(Incident, task.incident_id)
        resident = s.get(Resident, task.resident_id)
        out = task_out(task)

    await hub.broadcast({"type": "task_status", "task": out})
    unit_status = {"on_the_way": "task_sent", "reached": "reached", "need_help": "escalated"}.get(status)
    if unit_status:
        await _set_unit_status(incident.block_id, resident.unit, unit_status)
    log_event(incident.block_id, "task_status", {"task_id": task_id, "status": status, "resident_id": resident.id})

    if status == "need_help":
        log_event(incident.block_id, "escalated", {"resident_id": resident.id, "reason": "helper asked for help"})
    if status == "reached":
        await _check_all_reached(incident.block_id, incident.id)
    if out["family_of"]:
        await _family_update(out, status)
    return out


async def _family_update(task: dict, status: str) -> None:
    """Tell an essential worker how their family member is doing, so they can report for duty."""
    await hub.broadcast(
        {
            "type": "family_status",
            "worker_id": task["family_of"],
            "dependent_unit": task["resident_unit"],
            "dependent_name": task["resident_name"],
            "helper_name": task["helper_name"] or task["responder"],
            "status": "reached" if status == "reached" else "escalated" if status in {"escalated", "need_help"} else "on_the_way",
        }
    )


def family_cover(block_id: int) -> dict:
    """Counts for the dashboard: essential workers, and whose family has been checked."""
    incident = current_incident(block_id)
    with get_session() as s:
        workers = s.exec(select(Resident).where(Resident.block_id == block_id, Resident.is_essential_worker == True)).all()  # noqa: E712
        tasks = s.exec(select(Task).where(Task.incident_id == (incident.id if incident else -1))).all()
    with_family = [w for w in workers if w.dependent_unit]
    covered = {t.family_of for t in tasks if t.family_of and t.status == "reached"}
    return {"workers": len(workers), "with_family": len(with_family), "covered": len(covered)}


# ---- Official responders (reallocation) ---------------------------------------


async def send_responders(block_id: int, team: str) -> int:
    """An official sends a responder team to a block: they go to everyone with no neighbour."""
    incident = current_incident(block_id)
    if incident is None:
        return 0
    with get_session() as s:
        tasks = s.exec(select(Task).where(Task.incident_id == incident.id, Task.status == "escalated")).all()
        ids = [t.id for t in tasks]
        for t in tasks:
            t.status = "responder_en_route"
            t.responder = team
            t.updated_at = now()
            s.add(t)
        s.commit()
    for tid in ids:
        with get_session() as s:
            out = task_out(s.get(Task, tid))
        await hub.broadcast({"type": "task_status", "task": out})
        await _set_unit_status(block_id, out["resident_unit"], "task_sent")
        spawn(_responder_arrives(tid))
    log_event(block_id, "responders_sent", {"team": team, "tasks": ids})
    return len(ids)


async def _responder_arrives(task_id: int) -> None:
    await asyncio.sleep(random.uniform(12, 30))
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None or task.status != "responder_en_route":
            return
    await set_task_status(task_id, "reached")


async def _check_all_reached(block_id: int, incident_id: int) -> None:
    ranked = rank(block_id)
    remaining = [r for r in ranked if not r["reached"]]
    with get_session() as s:
        tasks = s.exec(select(Task).where(Task.incident_id == incident_id)).all()
    reached = {t.resident_id for t in tasks if t.status == "reached"}
    vulnerable = len(ranked)
    await hub.broadcast(
        {"type": "progress", "block_id": block_id, "reached": len(reached), "vulnerable": vulnerable, "all_reached": not remaining}
    )


async def _escalation_watch(task_id: int, block_id: int, wait: float = ESCALATE_SECONDS) -> None:
    """If nobody has responded in time, move the task to the next-best helper."""
    await asyncio.sleep(wait)
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None or task.status != "sent":
            return
        task.status = "reassigned"
        task.updated_at = now()
        s.add(task)
        s.commit()
        s.refresh(task)
        item = {"resident_id": task.resident_id, "rank": task.rank, "score": task.score, "reasons": task.reasons}
        previous = {t.helper_id for t in s.exec(select(Task).where(Task.resident_id == task.resident_id)).all() if t.helper_id}
        incident_id = task.incident_id
        out = task_out(task)
    await hub.broadcast({"type": "task_status", "task": out})
    log_event(block_id, "reassigned", {"task_id": task_id, "from": out["helper_id"]})
    await _create_task(block_id, incident_id, item, exclude=previous)


async def _simulate_neighbour(task_id: int) -> None:
    """Fictional neighbours respond on their own, a few seconds apart."""
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None or task.helper_id in SIM_NO_RESPONSE or task.resident_id in SIM_UNREACHED:
            return  # this neighbour doesn't answer (asleep, phone off...)
    await asyncio.sleep(random.uniform(4, 9))
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None or task.status != "sent":
            return
    await set_task_status(task_id, "on_the_way")
    await asyncio.sleep(random.uniform(15, 35))
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None or task.status != "on_the_way":
            return
    await set_task_status(task_id, "reached")
