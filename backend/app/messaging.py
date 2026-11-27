"""The messaging layer: every instruction goes out the right way for the current mode.
(Person 1 owns this.)

    full      -> the full task card in the app
    low_data  -> one SMS of at most 160 characters ("Reply 1=reached 2=need help")
    relay     -> no network at all: phones pass the message to each other up the
                 stairwell (Bluetooth / Wi-Fi Direct). SIMULATED in the prototype:
                 the dashboard animates the hops and says so.
    no_phone  -> phones are dead: the printed block card in each lift lobby is the fallback

Real SMS through a provider (e.g. Twilio) is a stretch goal; for the demo the phone
shows an SMS-style view, which never depends on a real phone network.
"""

from sqlmodel import select

from .db import get_session
from .live import hub
from .models import Block, Event, Incident, Resident, Task
from .risk import floor_of

MODES = ["full", "low_data", "relay", "no_phone"]
MODE_LABEL = {"full": "Full", "low_data": "Low data: SMS", "relay": "Relay: no network", "no_phone": "No phones: block card"}


def _stairwell(block: Block, unit: str) -> str:
    n = int(unit.lstrip("#").split("-")[1])
    for name, nums in block.stairwells.items():
        if n in nums:
            return name
    return "A"


def relay_hops(block_id: int, helper_unit: str) -> list[str]:
    """The phones a message hops through to reach a helper: from the void deck up their
    stairwell, via neighbours' phones on the way. (Simulated: real relay is roadmap.)"""
    with get_session() as s:
        block = s.get(Block, block_id)
        residents = s.exec(select(Resident).where(Resident.block_id == block_id, Resident.has_smartphone == True)).all()  # noqa: E712
    stair = _stairwell(block, helper_unit)
    target = floor_of(helper_unit)
    path, last = [], 0
    for r in sorted(residents, key=lambda r: floor_of(r.unit)):
        f = floor_of(r.unit)
        if _stairwell(block, r.unit) == stair and last < f < target and f - last >= 2:
            path.append(r.unit)
            last = f
    return path + [helper_unit]


async def deliver(task: dict, mode: str) -> None:
    """Send one task in the way the current mode allows."""
    if not task.get("helper_id") or task["status"] not in {"sent", "on_the_way"}:
        return
    ins = task.get("instructions") or {}
    if mode == "low_data":
        text = ins.get("sms") or f"KG: Check {task['resident_name']} {task['resident_unit']} now. Reply 1=reached 2=need help"
        await hub.broadcast({"type": "sms", "helper_id": task["helper_id"], "task_id": task["id"], "text": text})
    elif mode == "relay":
        with get_session() as s:
            incident = s.get(Incident, task["incident_id"])
        hops = relay_hops(incident.block_id, task["helper_unit"])
        await hub.broadcast(
            {
                "type": "relay",
                "helper_id": task["helper_id"],
                "task_id": task["id"],
                "block_id": incident.block_id,
                "hops": hops,
                "text": ins.get("sms") or f"Check {task['resident_name']} {task['resident_unit']} now",
                "simulated": True,
            }
        )


async def set_mode(block_id: int, mode: str) -> dict:
    """Switch the incident's mode, tell every screen, and re-send open tasks the new way."""
    from .crisis import current_incident, task_out

    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    incident = current_incident(block_id)
    if incident is None:
        raise ValueError("No active incident")
    with get_session() as s:
        inc = s.get(Incident, incident.id)
        inc.mode = mode
        s.add(inc)
        s.add(Event(block_id=block_id, type="mode_change", details={"mode": mode}))
        s.commit()
        tasks = s.exec(select(Task).where(Task.incident_id == incident.id)).all()
        outs = [task_out(t) for t in tasks]
    await hub.broadcast({"type": "mode_change", "block_id": block_id, "mode": mode, "label": MODE_LABEL[mode]})
    for t in outs:
        await deliver(t, mode)
    return {"block_id": block_id, "mode": mode, "label": MODE_LABEL[mode]}
