"""Kampung Grid API server.

Run it from the backend/ folder:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Then open http://localhost:8000/docs to try every route.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import select

from . import ai, briefing, crisis, messaging, people, rumours, silence, sim, telegram_bot, trust, vault, voice
from .db import create_tables, get_session
from .live import hub
from .models import Block, Event, Helper, Report, Resident, Rumour, Task, Unit, UnlockLog

# Demo state, kept in memory: the current scene, and which control-panel beats have run.
STATE: dict = {"scene": "idle", "done": [], "assigned": False, "brief": None, "after_action": None, "sim_version": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os

    rebuilt = create_tables()
    # Every start is a fresh demo, so a restart never leaves an old incident behind.
    # Set KG_FRESH_ON_START=false in .env to keep data between restarts.
    fresh = os.getenv("KG_FRESH_ON_START", "true").lower() == "true"
    with get_session() as s:
        empty = s.exec(select(Block)).first() is None
    if fresh or rebuilt or empty:
        from seed.seed import run as seed_run

        seed_run()
        print("[startup] Fresh demo: loaded Block 123 and Block 125")
    await telegram_bot.start()
    yield
    await telegram_bot.stop()


app = FastAPI(title="Kampung Grid API", lifespan=lifespan)

# The frontend runs on a different port in development, so allow it to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def log_event(block_id: Optional[int], type_: str, details: dict) -> None:
    with get_session() as s:
        s.add(Event(block_id=block_id, type=type_, details=details))
        s.commit()


# ---------------------------------------------------------------------------
# Basic routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"ok": True, "scene": STATE["scene"]}


@app.get("/state")
def state():
    return STATE


@app.get("/network")
def network():
    """The laptop's address on the local network, so the control panel's QR code
    points phones somewhere they can actually reach (not "localhost")."""
    import socket

    ip = None
    try:
        # Opening a UDP "connection" sends nothing; it just asks the OS which
        # network card it would use, which tells us our local address.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            ip = sock.getsockname()[0]
    except OSError:
        pass
    if not ip or ip.startswith("127."):
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = None
    return {"ip": ip if ip and not ip.startswith("127.") else None}


# ---------------------------------------------------------------------------
# Joining the demo from your own phone (QR code)
# ---------------------------------------------------------------------------


@app.get("/join/roles")
def join_roles():
    """Helper roles a judge can play, and whether the Telegram bot is on."""
    return {"roles": people.roles(), "telegram": telegram_bot.status()}


class JoinIn(BaseModel):
    helper_id: str
    consent: bool = False


@app.post("/join")
async def join(body: JoinIn):
    if not body.consent:
        raise HTTPException(400, "Please tick the box to say you're happy to join")
    try:
        role = people.claim(body.helper_id, "web")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    await hub.broadcast({"type": "joined", "helper_id": body.helper_id, "via": "web"})
    return role


@app.post("/join/leave")
async def join_leave(body: JoinIn):
    people.release(body.helper_id)
    await hub.broadcast({"type": "left", "helper_id": body.helper_id})
    return {"ok": True}


@app.get("/blocks/{block_id}")
def get_block(block_id: int):
    """The block, its units and residents, for drawing the block view.

    Privacy: this never returns vulnerability details, only a yes/no flag,
    because the dashboard must not show medical information.
    """
    with get_session() as s:
        block = s.get(Block, block_id)
        if block is None:
            raise HTTPException(404, "Block not found")
        units = s.exec(select(Unit).where(Unit.block_id == block_id)).all()
        residents = s.exec(select(Resident).where(Resident.block_id == block_id)).all()
        helpers = {h.resident_id: h for h in s.exec(select(Helper)).all()}

        people = []
        for r in residents:
            h = helpers.get(r.id)
            people.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "unit": r.unit,
                    "is_vulnerable": r.has_profile,
                    "is_helper": h is not None,
                    "helper_skills": h.skills if h else [],
                    "is_essential_worker": r.is_essential_worker,
                    "silence_opt_in": r.silence_opt_in,
                }
            )
        return {
            "id": block.id,
            "name": block.name,
            "floors": block.floors,
            "units_per_floor": block.units_per_floor,
            "stairwells": block.stairwells,
            "units": [u.model_dump() for u in sorted(units, key=lambda u: (u.floor, u.number))],
            "residents": people,
        }


@app.get("/residents/{resident_id}")
def get_resident(resident_id: str):
    """What a resident's own phone needs to show its home screen."""
    with get_session() as s:
        r = s.get(Resident, resident_id)
        if r is None:
            raise HTTPException(404, "Resident not found")
        h = s.get(Helper, resident_id)
        role = "helper" if h else "senior" if r.silence_opt_in else "resident"
        return {
            "id": r.id,
            "name": r.name,
            "block_id": r.block_id,
            "unit": r.unit,
            "language": r.language,
            "role": role,
            "is_essential_worker": r.is_essential_worker,
            "essential_role": r.essential_role,
            "dependent_unit": r.dependent_unit,
            "silence_opt_in": r.silence_opt_in,
            "last_checkin": _last_checkin(r.id) if r.silence_opt_in else None,
            "helper": {"skills": h.skills, "languages": h.languages} if h else None,
        }


@app.get("/residents")
def list_residents(block_id: int = 123):
    """Short list for the demo 'switch person' menu."""
    with get_session() as s:
        rs = s.exec(select(Resident).where(Resident.block_id == block_id)).all()
        helper_ids = {h.resident_id for h in s.exec(select(Helper)).all()}
        return [
            {"id": r.id, "name": r.name, "unit": r.unit, "is_helper": r.id in helper_ids}
            for r in sorted(rs, key=lambda r: r.unit)
        ]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class ReportIn(BaseModel):
    text: str
    sender_id: Optional[str] = None
    sender_phone: Optional[str] = None
    block_id: int = 123


def utc(dt):
    """SQLite forgets timezones, so times read back are 'naive'. They are always
    stored in UTC: label them so browsers convert them to local time correctly."""
    from datetime import timezone

    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def report_out(report: Report, resident: Optional[Resident]) -> dict:
    """The shape every screen receives for a report (see docs/api.md)."""
    report.created_at = utc(report.created_at)
    sender = None
    if report.sender_id:
        with get_session() as s:
            person = s.get(Resident, report.sender_id)
            sender = person.name if person else None
    return {
        "id": report.id,
        "text": report.text,
        "sender_id": report.sender_id,
        "sender_name": sender or (f"Unknown number {report.sender_phone}" if report.sender_phone else "Unknown sender"),
        "trust_level": report.trust_level,  # high, medium, low (None while reading)
        "trust_reasons": report.trust_reasons,
        "parsed": report.parsed,  # None while the AI is still reading it
        "resident_id": report.resident_id,
        "resident_name": resident.name if resident else None,
        "status": report.status,
        "created_at": report.created_at,
    }


# Keep references to background jobs so Python doesn't drop them half-way.
_background_jobs: set[asyncio.Task] = set()


@app.post("/reports")
async def create_report(body: ReportIn):
    """A neighbour sends a message.

    1. Save it straight away and tell every screen ("AI reading...").
    2. Answer the phone immediately, so the sender sees "Sent" with no waiting.
    3. In the background, the AI turns it into a structured alert, and every
       screen gets a `report_updated` message when it's done.
    """
    with get_session() as s:
        report = Report(
            block_id=body.block_id,
            sender_id=body.sender_id,
            sender_phone=body.sender_phone,
            text=body.text,
            status="reading",
        )
        s.add(report)
        s.commit()
        s.refresh(report)
        out = report_out(report, None)

    await hub.broadcast({"type": "report_new", "report": out})
    job = asyncio.create_task(_read_report(out["id"]))
    _background_jobs.add(job)
    job.add_done_callback(_background_jobs.discard)
    return out


async def _read_report(report_id: int) -> None:
    """Background job: ask the AI to read one report, then update every screen."""
    with get_session() as s:
        report = s.get(Report, report_id)
        if report is None:
            return
        block_id, text = report.block_id, report.text
        known_units = [u.label for u in s.exec(select(Unit).where(Unit.block_id == block_id)).all()]
        residents = [(r.name, r.unit) for r in s.exec(select(Resident).where(Resident.block_id == block_id)).all()]

    # The Claude call is blocking, so run it off the main loop.
    parsed = await asyncio.to_thread(ai.parse_report, text, known_units, residents)

    with get_session() as s:
        report = s.get(Report, report_id)
        if report is None:  # the demo was reset while the AI was reading
            return
        resident = None
        if parsed.get("unit"):
            resident = s.exec(
                select(Resident).where(Resident.block_id == block_id, Resident.unit == parsed["unit"])
            ).first()
        report.parsed = parsed
        report.resident_id = resident.id if resident else None
        s.add(report)
        s.commit()
        s.refresh(report)

    # Trust check: can we act on this report, or does a human need to look first?
    level, reasons = await asyncio.to_thread(trust.check, report)
    with get_session() as s:
        report = s.get(Report, report_id)
        if report is None:
            return
        report.trust_level = level
        report.trust_reasons = reasons
        report.status = "waiting_for_human" if level == "low" else "new"
        s.add(report)
        s.commit()
        s.refresh(report)
        # Look the resident up again in this session (the earlier copy is closed).
        resident = s.get(Resident, report.resident_id) if report.resident_id else None
        out = report_out(report, resident)

    log_event(
        block_id,
        "report_read",
        {"report_id": report_id, "unit": parsed.get("unit"), "source": parsed.get("source"), "trust": level},
    )
    await hub.broadcast({"type": "report_updated", "report": out})

    # Second wave: is a rumour spreading?
    await rumours.check(block_id)

    # Live adaptation: once helpers have been assigned, a trusted new report about
    # someone without a task gets them a helper straight away.
    if level != "low" and STATE.get("assigned") and crisis.current_incident(block_id):
        await crisis.assign_all(block_id)
    await hub.broadcast({"type": "ranking_changed", "block_id": block_id})


class DecisionIn(BaseModel):
    decision: str  # approve, reject


@app.post("/reports/{report_id}/decision")
async def report_decision(report_id: int, body: DecisionIn):
    """A human on the dashboard decides about a low-trust report."""
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be 'approve' or 'reject'")
    with get_session() as s:
        report = s.get(Report, report_id)
        if report is None:
            raise HTTPException(404, "Report not found")
        report.status = "approved" if body.decision == "approve" else "rejected"
        s.add(report)
        s.commit()
        s.refresh(report)
        resident = s.get(Resident, report.resident_id) if report.resident_id else None
        block_id = report.block_id
        out = report_out(report, resident)
    log_event(block_id, f"report_{report.status}", {"report_id": report_id, "by": "official (dashboard)"})
    await hub.broadcast({"type": "report_updated", "report": out})
    if body.decision == "approve" and STATE.get("assigned") and crisis.current_incident(block_id):
        await crisis.assign_all(block_id)
        await hub.broadcast({"type": "ranking_changed", "block_id": block_id})
    return out


# ---------------------------------------------------------------------------
# Time to Last Knock (simulation) and "what if"
# ---------------------------------------------------------------------------


@app.get("/sim/overview")
def sim_overview(block_id: int = 123):
    """7pm and 3am numbers, the 24-hour curve, the biggest gap, and the assumptions."""
    return sim.overview(block_id, STATE["sim_version"])


class WhatIfIn(BaseModel):
    block_id: int = 123
    time: str = "03:00"


@app.post("/sim/what-if")
async def sim_what_if(body: WhatIfIn):
    """Try small changes and rank them by minutes saved, plus a plain-English summary."""
    result = await asyncio.to_thread(sim.what_if, body.block_id, body.time)
    o = sim.overview(body.block_id, STATE["sim_version"])
    with get_session() as s:
        name = s.get(Block, body.block_id).name
    summary = await asyncio.to_thread(ai.summarise_what_if, name, o["evening"], o["night"], o["gap"], result["options"])
    return {**result, "summary": summary}


# ---------------------------------------------------------------------------
# Official responders, handover brief, after-action, family cover
# ---------------------------------------------------------------------------


class ReallocateIn(BaseModel):
    block_id: int
    team: str = "SCDF Team B"


@app.post("/responders/reallocate")
async def reallocate(body: ReallocateIn):
    """An official sends a responder team to the block that needs it most."""
    sent = await crisis.send_responders(body.block_id, body.team)
    await hub.broadcast({"type": "responders_moved", "team": body.team, "block_id": body.block_id, "residents": sent})
    return {"ok": True, "team": body.team, "block_id": body.block_id, "residents": sent}


@app.get("/handover-brief")
def get_brief():
    return STATE["brief"]


@app.get("/after-action")
def get_after_action():
    return STATE["after_action"]


@app.get("/family-cover")
def get_family_cover(block_id: int = 123):
    return crisis.family_cover(block_id)


@app.get("/family/{worker_id}")
def get_family_status(worker_id: str):
    """An essential worker's phone: how is my family member doing?"""
    with get_session() as s:
        worker = s.get(Resident, worker_id)
        if worker is None or not worker.dependent_unit:
            return None
        incident = crisis.current_incident(worker.block_id)
        task = (
            s.exec(select(Task).where(Task.incident_id == incident.id, Task.family_of == worker_id).order_by(Task.id.desc())).first()
            if incident
            else None
        )
    if task is None:
        return {"dependent_unit": worker.dependent_unit, "status": "none"}
    out = crisis.task_out(task)
    status = "reached" if task.status == "reached" else "escalated" if task.status in {"escalated", "need_help"} else "on_the_way"
    return {"dependent_unit": out["resident_unit"], "dependent_name": out["resident_name"], "helper_name": out["helper_name"] or out["responder"], "status": status}


# ---------------------------------------------------------------------------
# Rumours
# ---------------------------------------------------------------------------


@app.get("/rumours")
def list_rumours(block_id: int = 123):
    with get_session() as s:
        rows = s.exec(select(Rumour).where(Rumour.block_id == block_id).order_by(Rumour.id.desc())).all()
    return [rumours.rumour_out(r) for r in rows]


class AnswerIn(BaseModel):
    answer: str


@app.post("/rumours/{rumour_id}/approve")
async def approve_rumour(rumour_id: int, body: AnswerIn):
    """An official approves the verified answer; it goes out through familiar neighbours."""
    if not body.answer.strip():
        raise HTTPException(400, "Write the verified answer first")
    try:
        return await rumours.approve(rumour_id, body.answer.strip())
    except KeyError:
        raise HTTPException(404, "Rumour not found")


@app.post("/rumours/{rumour_id}/dismiss")
async def dismiss_rumour(rumour_id: int):
    try:
        return await rumours.dismiss(rumour_id)
    except KeyError:
        raise HTTPException(404, "Rumour not found")


@app.get("/reports")
def list_reports(block_id: int = 123):
    with get_session() as s:
        reports = s.exec(
            select(Report).where(Report.block_id == block_id).order_by(Report.id.desc())
        ).all()
        residents = {r.id: r for r in s.exec(select(Resident).where(Resident.block_id == block_id)).all()}
        return [report_out(r, residents.get(r.resident_id)) for r in reports]


# ---------------------------------------------------------------------------
# Silence Alert check-ins ("I'm okay today")
# ---------------------------------------------------------------------------


class CheckinIn(BaseModel):
    resident_id: str


def _last_checkin(resident_id: str) -> Optional[str]:
    with get_session() as s:
        ev = s.exec(
            select(Event)
            .where(Event.type == "checkin")
            .order_by(Event.id.desc())
        ).all()
        for e in ev:
            if e.details.get("resident_id") == resident_id:
                return utc(e.created_at).isoformat()
    return None


@app.post("/checkins")
async def create_checkin(body: CheckinIn):
    """An opted-in senior taps "I'm okay today". Person 4 scores missed check-ins in Week 5."""
    with get_session() as s:
        r = s.get(Resident, body.resident_id)
        if r is None:
            raise HTTPException(404, "Resident not found")
        if not r.silence_opt_in:
            raise HTTPException(400, "This resident hasn't opted in to Silence Alert")
        block_id, unit = r.block_id, r.unit
    log_event(block_id, "checkin", {"resident_id": body.resident_id, "unit": unit})
    at = _last_checkin(body.resident_id)
    await hub.broadcast({"type": "checkin", "resident_id": body.resident_id, "unit": unit})
    await silence.check_all(block_id)  # a check-in can close an open Silence Alert
    return {"ok": True, "resident_id": body.resident_id, "checked_in_at": at}


class NotSeenIn(BaseModel):
    reporter_id: str
    unit: str
    days: int = 2


@app.post("/silence/not-seen")
async def not_seen(body: NotSeenIn):
    """A neighbour taps "haven't seen" for an opted-in senior. Anonymous to the senior."""
    with get_session() as s:
        reporter = s.get(Resident, body.reporter_id)
        if reporter is None:
            raise HTTPException(404, "Reporter not found")
        block_id = reporter.block_id
    log_event(block_id, "not_seen", {"reporter_id": body.reporter_id, "unit": body.unit, "days": body.days})
    changed = await silence.check_all(block_id)
    return {"ok": True, "cases": changed}


@app.get("/silence/cases")
def silence_cases():
    return silence.open_cases()


@app.get("/silence/seniors")
def silence_seniors(block_id: int = 123):
    """Opted-in units neighbours can tap 'haven't seen' for (unit numbers and names only)."""
    with get_session() as s:
        rows = s.exec(select(Resident).where(Resident.block_id == block_id, Resident.silence_opt_in == True)).all()  # noqa: E712
    return [{"resident_id": r.id, "name": r.name, "unit": r.unit} for r in rows]


@app.post("/silence/{case_id}/approve")
async def silence_approve(case_id: int):
    try:
        return await silence.approve_next(case_id)
    except KeyError:
        raise HTTPException(404, "Case not found")


class OutcomeIn(BaseModel):
    outcome: str  # okay, no_answer


@app.post("/silence/{case_id}/resolve")
async def silence_resolve(case_id: int, body: OutcomeIn):
    try:
        return await silence.resolve(case_id, body.outcome)
    except KeyError:
        raise HTTPException(404, "Case not found")


# ---------------------------------------------------------------------------
# The printed block card (works with no phone at all)
# ---------------------------------------------------------------------------


@app.get("/block-card/{block_id}")
def block_card(block_id: int):
    """Unit numbers only, never names or medical details: safe to stick in a lift lobby."""
    from .risk import floor_of

    with get_session() as s:
        block = s.get(Block, block_id)
        if block is None:
            raise HTTPException(404, "Block not found")
        residents = s.exec(select(Resident).where(Resident.block_id == block_id)).all()
        helpers = {h.resident_id: h for h in s.exec(select(Helper)).all()}
    knock_first = [r.unit for r in sorted((r for r in residents if r.has_profile), key=lambda r: (r.knock_priority or 99, r.unit))]
    helper_units = sorted(
        ({"unit": r.unit, "skills": helpers[r.id].skills} for r in residents if r.id in helpers and not r.is_essential_worker),
        key=lambda h: (-floor_of(h["unit"]), h["unit"]),
    )
    return {"block": block.name, "knock_first": knock_first, "helpers": helper_units, "updated": "sample data (prototype)"}


# ---------------------------------------------------------------------------
# Voice notes
# ---------------------------------------------------------------------------


@app.post("/reports/voice")
async def voice_report(audio: UploadFile = File(...), sender_id: Optional[str] = Form(None), block_id: int = Form(123)):
    """A voice note: Whisper turns it into text on this laptop, then it's read like any report."""
    data = await audio.read()
    suffix = "." + (audio.filename or "note.webm").rsplit(".", 1)[-1]
    try:
        text = await asyncio.to_thread(voice.transcribe, data, suffix)
    except voice.VoiceUnavailable as exc:
        raise HTTPException(501, str(exc))
    if not text:
        raise HTTPException(422, "Couldn't hear anything in that voice note. Try again, a bit closer to the phone.")
    report = await create_report(ReportIn(text=text, sender_id=sender_id, block_id=block_id))
    return {**report, "transcript": text}


# ---------------------------------------------------------------------------
# Incidents and tasks (the crisis engine lives in crisis.py)
# ---------------------------------------------------------------------------


@app.get("/incidents/current")
def incident_current(block_id: int = 123):
    """The active incident (if any), everyone ranked by urgency, and every task."""
    incident = crisis.current_incident(block_id)
    if incident is None:
        return {"incident": None, "ranked": [], "tasks": []}
    with get_session() as s:
        tasks = s.exec(select(Task).where(Task.incident_id == incident.id).order_by(Task.id)).all()
    return {
        "incident": {
            "id": incident.id,
            "type": incident.type,
            "cause": incident.cause,
            "mode": incident.mode,
            "status": incident.status,
            "started_at": utc(incident.started_at),
        },
        "ranked": crisis.rank(block_id),
        "tasks": [crisis.task_out(t) for t in tasks],
    }


@app.get("/tasks")
def list_tasks(helper_id: str):
    """A helper's tasks, newest first (the phone loads these on start)."""
    with get_session() as s:
        tasks = s.exec(select(Task).where(Task.helper_id == helper_id).order_by(Task.id.desc())).all()
    return [crisis.task_out(t) for t in tasks]


@app.get("/tasks/{task_id}/profile")
def task_profile(task_id: int, helper_id: str):
    """The assigned helper's need-to-know view of the resident's Sealed Profile.
    Opens only during an active incident and only for the assigned helper."""
    with get_session() as s:
        task = s.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    try:
        view, _ = vault.open_for_helper(task.resident_id, task.incident_id, helper_id)
    except vault.VaultLocked as exc:
        return {"keys": {"incident": False, "assigned": task.helper_id == helper_id}, "need_to_know": None, "message": str(exc)}
    return {"keys": {"incident": True, "assigned": True}, "need_to_know": view}


@app.get("/unlock-log")
def unlock_log():
    """Every time a Sealed Profile was opened, newest first."""
    with get_session() as s:
        rows = s.exec(select(UnlockLog).order_by(UnlockLog.id.desc())).all()
    return [vault.log_out(r) for r in rows]


class TaskStatusIn(BaseModel):
    status: str  # on_the_way, reached, need_help


@app.post("/tasks/{task_id}/status")
async def update_task_status(task_id: int, body: TaskStatusIn):
    if body.status not in {"on_the_way", "reached", "need_help"}:
        raise HTTPException(400, "status must be 'on_the_way', 'reached' or 'need_help'")
    try:
        return await crisis.set_task_status(task_id, body.status)
    except KeyError:
        raise HTTPException(404, "Task not found")


# ---------------------------------------------------------------------------
# Demo control panel
# ---------------------------------------------------------------------------


async def mark_beat_done(beat: str) -> None:
    """Remember which demo beats have run, so the control panel survives a page refresh."""
    if beat not in STATE["done"]:
        STATE["done"].append(beat)
    await hub.broadcast({"type": "control_progress", "done": STATE["done"]})


@app.post("/control/reset")
async def control_reset():
    """Wipe everything and reload the seed data. Used before every rehearsal."""
    from seed.seed import run as seed_run

    crisis.cancel_all()  # stop timers and simulated neighbours from the last run
    await asyncio.to_thread(seed_run)
    STATE["scene"] = "idle"
    STATE["done"] = []
    STATE["assigned"] = False
    STATE["brief"] = None
    STATE["after_action"] = None
    STATE["sim_version"] += 1  # the block may have changed (seed file edited), so recompute
    people.clear()  # judges who joined are let go; Telegram chat IDs are deleted on "reset"
    await hub.broadcast({"type": "reset"})
    await hub.broadcast({"type": "scene", "name": "idle"})
    await hub.broadcast({"type": "control_progress", "done": []})
    return {"ok": True, "scene": "idle"}


@app.post("/control/start-evening")
async def control_start_evening():
    STATE["scene"] = "evening"
    log_event(123, "scene", {"name": "evening"})
    await hub.broadcast({"type": "scene", "name": "evening", "block_id": 123})
    await mark_beat_done("start-evening")
    return {"ok": True, "scene": "evening"}


DEMO_VOICE_NOTE = {"sender_id": "meiling", "text": "Eh the auntie at 9-12 never open door, got smell leh"}


@app.post("/control/cyberattack")
async def control_cyberattack():
    """Beat 2: a cyberattack takes down the grid. Crisis mode on."""
    incident = await crisis.start_incident(123, "blackout", "grid cyberattack")
    STATE["scene"] = "crisis"
    await hub.broadcast({"type": "scene", "name": "crisis", "block_id": 123})
    await mark_beat_done("cyberattack")
    return {"ok": True, "scene": "crisis", "incident_id": incident.id}


@app.post("/control/voice-note")
async def control_voice_note():
    """Beat 3: the scripted neighbour message arrives (typed for now; real voice notes in Week 5)."""
    report = await create_report(ReportIn(text=DEMO_VOICE_NOTE["text"], sender_id=DEMO_VOICE_NOTE["sender_id"]))
    await mark_beat_done("voice-note")
    return {"ok": True, "report_id": report["id"]}


@app.post("/control/assign-helper")
async def control_assign_helper():
    """Beat 4: rank everyone, match helpers, send tasks."""
    if crisis.current_incident(123) is None:
        return {"ok": False, "message": "Press Cyberattack first."}
    tasks = await crisis.assign_all(123)
    STATE["assigned"] = True
    await mark_beat_done("assign-helper")
    return {"ok": True, "tasks": len(tasks)}


@app.post("/control/mdm-tan-reached")
async def control_mdm_tan_reached():
    """Beat 9: Aziz taps "Reached". Use this if his phone isn't in the demo."""
    incident = crisis.current_incident(123)
    if incident is None:
        return {"ok": False, "message": "No active incident."}
    with get_session() as s:
        task = s.exec(
            select(Task).where(Task.incident_id == incident.id, Task.resident_id == "tan").order_by(Task.id.desc())
        ).first()
    if task is None:
        return {"ok": False, "message": "Mdm Tan has no task yet. Press Assign helper first."}
    if task.status != "reached":
        await crisis.set_task_status(task.id, "reached")
    await mark_beat_done("mdm-tan-reached")
    return {"ok": True}


# The attacker's second wave: one fake report, then a rumour spreading.
FAKE_REPORT = {"sender_phone": "+65 8000 9999", "text": "URGENT!!! auntie at 14-03 collapsed, come now!!! hurry"}
RUMOUR_MESSAGES = [
    ("lee", "my sister say tap water contaminated after the blackout, dont drink!!"),
    ("hassan", "Air paip dah tercemar lepas blackout, jangan minum"),
    ("jo", "is it true the water is poisoned? group chat all saying dont drink tap water"),
]


@app.post("/control/fake-report")
async def control_fake_report():
    """Beat 6: a fake report from an unknown number, then a water rumour spreads."""

    async def second_wave():
        await create_report(ReportIn(text=FAKE_REPORT["text"], sender_phone=FAKE_REPORT["sender_phone"]))
        for sender, text in RUMOUR_MESSAGES:
            await asyncio.sleep(1.2)
            await create_report(ReportIn(text=text, sender_id=sender))

    crisis.spawn(second_wave())
    await mark_beat_done("fake-report")
    return {"ok": True}


@app.post("/control/block-125")
async def control_block_125():
    """Beat 7: the blackout also hits Block 125, where nobody can help at night."""
    await crisis.start_incident(125, "blackout", "grid cyberattack")
    tasks = await crisis.assign_all(125)
    unreached = sum(1 for t in tasks if t["status"] == "escalated")
    await hub.broadcast({"type": "block_alert", "block_id": 125, "unreached": unreached, "suggested_team": "SCDF Team B"})
    await mark_beat_done("block-125")
    return {"ok": True, "unreached": unreached}


@app.post("/control/scdf-arrives")
async def control_scdf_arrives():
    """Beat 8: SCDF arrives at Block 123 and gets the handover brief."""
    if crisis.current_incident(123) is None:
        return {"ok": False, "message": "No active incident."}
    brief = await briefing.handover_brief(123)
    STATE["brief"] = brief
    await hub.broadcast({"type": "brief_ready", "brief": brief})
    await mark_beat_done("scdf-arrives")
    return {"ok": True}


@app.post("/control/after-action")
async def control_after_action():
    """Beat 10: after the crisis, the automatic report and the "what if" planning view."""
    try:
        report = briefing.after_action(123)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    STATE["after_action"] = report
    await hub.broadcast({"type": "after_action", "report": report})
    await mark_beat_done("after-action")
    return {"ok": True}


@app.post("/control/network-down")
async def control_network_down():
    """Beat 5: mobile data fails. The next instruction arrives as an SMS."""
    try:
        result = await messaging.set_mode(123, "low_data")
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    await mark_beat_done("network-down")
    return {"ok": True, **result}


@app.post("/control/silence-demo")
async def control_silence_demo():
    """Extra: Mr Lim hasn't checked in for 2 days and a neighbour taps 'haven't seen'."""
    silence.backdate_checkin("lim", 2)
    log_event(123, "not_seen", {"reporter_id": "farah", "unit": "#05-08", "days": 2})
    changed = await silence.check_all(123)
    return {"ok": True, "cases": changed}


class TestJobIn(BaseModel):
    helper_id: Optional[str] = None  # empty = everyone who joined


@app.post("/control/test-job")
async def control_test_job(body: TestJobIn = TestJobIn()):
    """Practice: send a job straight to whoever joined by QR or Telegram. No beats needed."""
    targets = [body.helper_id] if body.helper_id else list(people.CLAIMS)
    if not targets:
        return {"ok": False, "message": "Nobody has joined yet. Ask them to scan the QR code or open the bot first."}
    if STATE["scene"] != "crisis":
        STATE["scene"] = "crisis"
        await hub.broadcast({"type": "scene", "name": "crisis", "block_id": 123})
    sent, skipped = [], []
    for helper_id in targets:
        task = await crisis.test_job(123, helper_id)
        (sent if task else skipped).append(helper_id)
    await hub.broadcast({"type": "ranking_changed", "block_id": 123})
    msg = f"Sent a job to {len(sent)} {'person' if len(sent) == 1 else 'people'}"
    if skipped:
        msg += f" (couldn't reach: {', '.join(skipped)})"
    return {"ok": bool(sent), "message": msg, "sent": sent, "skipped": skipped}


@app.get("/ai/status")
def ai_status():
    """Is Claude on, and how many backup answers are saved for when the internet drops?"""
    return ai.cache_status()


class ModeIn(BaseModel):
    mode: str  # full, low_data, relay, no_phone
    block_id: int = 123


@app.post("/control/mode")
async def control_mode(body: ModeIn):
    """Switch between the four modes (for rehearsals and the Q&A)."""
    try:
        return {"ok": True, **(await messaging.set_mode(body.block_id, body.mode))}
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}


# Beats that arrive in later weeks. They answer clearly instead of failing silently.
FUTURE_BEATS: dict[str, str] = {}


@app.post("/control/{beat}")
async def control_future_beat(beat: str):
    if beat in FUTURE_BEATS:
        return {"ok": False, "message": f"'{beat}' is planned for {FUTURE_BEATS[beat]}."}
    raise HTTPException(404, f"Unknown beat '{beat}'")


# ---------------------------------------------------------------------------
# Live updates
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await hub.connect(ws)
    # Tell the new screen where the demo currently is.
    await ws.send_json({"type": "scene", "name": STATE["scene"]})
    await ws.send_json({"type": "control_progress", "done": STATE["done"]})
    try:
        while True:
            await ws.receive_text()  # we don't expect messages; this keeps it open
    except WebSocketDisconnect:
        hub.disconnect(ws)
