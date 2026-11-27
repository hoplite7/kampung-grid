"""Time to Last Knock: how many minutes until neighbours reach EVERY vulnerable
resident in a block? (Person 4 owns this.)

We can't wait for a real crisis to measure it, so we SIMULATE one many times:
  1. Start from the block's real picture: where vulnerable residents and helpers
     live, and when each helper is usually home.
  2. Add the crisis conditions: lifts down, the time of day (helpers asleep at 3am
     respond slower), and a chance that some helpers don't respond at all.
  3. Play it out: each resident gets the helper who can reach them soonest.
  4. Repeat 500 times with some randomness (a "Monte Carlo simulation").
  5. Report the typical night (median) and a bad night (90th percentile:
     only 1 night in 10 is worse).

Then the "what if" search tries small changes (train someone, recruit a night
helper) and ranks them by minutes saved. That search is the optimisation part.

Privacy: the simulation only uses WHERE vulnerable residents live (a yes/no flag),
never what's in their Sealed Profiles, so it works outside an incident.
Every guess lives in sim/assumptions.yaml, shown honestly on a slide.
"""

import random
import statistics
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import yaml
from sqlmodel import select

from .crisis import is_home, stairwell_for
from .db import get_session
from .models import Block, Helper, Resident
from .risk import floor_of

ASSUMPTIONS_FILE = Path(__file__).resolve().parent.parent / "sim" / "assumptions.yaml"


def load_assumptions() -> dict:
    return yaml.safe_load(ASSUMPTIONS_FILE.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class SimHelper:
    name: str
    floor: int
    stairwell: str
    trained: bool
    home_hours: tuple[str, ...]


@dataclass(frozen=True)
class SimBlock:
    block_id: int
    residents: tuple[tuple[int, str], ...]  # (floor, stairwell) of each vulnerable resident
    helpers: tuple[SimHelper, ...]


def load_block(block_id: int) -> SimBlock:
    with get_session() as s:
        block = s.get(Block, block_id)
        residents = s.exec(select(Resident).where(Resident.block_id == block_id)).all()
        helpers = {h.resident_id: h for h in s.exec(select(Helper)).all()}
    vulnerable = tuple(
        sorted(((floor_of(r.unit), stairwell_for(block.stairwells, r.unit)) for r in residents if r.has_profile), reverse=True)
    )
    pool = tuple(
        SimHelper(
            name=r.name,
            floor=floor_of(r.unit),
            stairwell=stairwell_for(block.stairwells, r.unit),
            trained=bool({"cpr", "first_aid"} & set(helpers[r.id].skills)),
            home_hours=tuple(helpers[r.id].home_hours),
        )
        for r in residents
        if r.id in helpers and not r.is_essential_worker  # essential workers report for duty
    )
    return SimBlock(block_id, vulnerable, pool)


def _asleep(at: str, a: dict) -> bool:
    return is_home([a["reaction_minutes"]["asleep_hours"]], at)


def one_run(block: SimBlock, at: str, rng: random.Random, a: dict) -> float:
    """One simulated night. Returns minutes until the LAST vulnerable resident is reached."""
    asleep = _asleep(at, a)
    lo, hi = a["reaction_minutes"]["asleep" if asleep else "awake"]
    chance = a["answer_chance"]

    # Who is home, and who answers tonight? Each responder: [floor, stairwell, minute they're free]
    responders = []
    for h in block.helpers:
        if not is_home(list(h.home_hours), at):
            continue
        p = chance[f"{'trained' if h.trained else 'untrained'}_{'asleep' if asleep else 'awake'}"]
        if rng.random() < p:
            responders.append([h.floor, h.stairwell, rng.uniform(lo, hi)])

    per_floor = a["stairs"]["seconds_per_floor"] / 60
    switch = a["stairs"]["switch_stairwell_seconds"] / 60
    door = a["at_the_door_minutes"]

    last = 0.0
    for floor, stair in block.residents:  # highest floors first (lifts are down)
        best_i, best_t = None, None
        for i, (hf, hs, free_at) in enumerate(responders):
            travel = abs(hf - floor) * per_floor + (switch if hs != stair else 0)
            arrive = free_at + travel * rng.uniform(0.9, 1.3)
            if best_t is None or arrive < best_t:
                best_i, best_t = i, arrive
        if best_i is None:
            reached = a["official_responders_minutes"] + door
        else:
            reached = best_t
            # The helper is now on this floor, free again after checking at the door.
            responders[best_i] = [floor, stair, reached + door]
        last = max(last, reached)
    return last


def ttlk(block: SimBlock, at: str, a: dict | None = None) -> dict:
    a = a or load_assumptions()
    rng = random.Random(a["random_seed"])
    times = sorted(one_run(block, at, rng, a) for _ in range(a["runs"]))
    p90 = times[int(0.9 * (len(times) - 1))]
    return {"time": at, "median": round(statistics.median(times)), "p90": round(p90), "runs": len(times)}


def biggest_gap(block: SimBlock, at: str, a: dict | None = None) -> str | None:
    """A plain sentence about the weakest floor band at this time, if any."""
    a = a or load_assumptions()
    for lo, hi in reversed(a["gap"]["floor_bands"]):
        here = [h for h in block.helpers if lo <= h.floor <= hi and is_home(list(h.home_hours), at)]
        has_vulnerable = any(lo <= f <= hi for f, _ in block.residents)
        if has_vulnerable and not any(h.trained for h in here):
            return f"No trained first-aider home on floors {lo} to {hi} at {at}."
    return None


# ---- What if? -----------------------------------------------------------------


def candidate_changes(block: SimBlock, at: str, a: dict) -> list[tuple[str, SimBlock]]:
    """Small, realistic changes a town council could fund."""
    out = []
    for lo, hi in a["gap"]["floor_bands"]:
        mid = (lo + hi) // 2
        # Train helpers in this band who are home at this time but untrained.
        untrained = [h for h in block.helpers if lo <= h.floor <= hi and not h.trained and is_home(list(h.home_hours), at)]
        if untrained:
            trained = tuple(replace(h, trained=True) if h in untrained[:2] else h for h in block.helpers)
            n = min(2, len(untrained))
            out.append((f"Train {n} resident{'s' if n > 1 else ''} on floors {lo} to {hi} in first aid", replace(block, helpers=trained)))
        # Recruit new trained helpers here who are home at night (e.g. from the Void Deck Wargame).
        for count in (1, 2):
            new = tuple(
                SimHelper(f"new helper {i}", mid, "AB"[i % 2], True, ("18:00-08:00",)) for i in range(count)
            )
            out.append(
                (
                    f"Recruit {count} night-time first-aider{'s' if count > 1 else ''} on floors {lo} to {hi}",
                    replace(block, helpers=block.helpers + new),
                )
            )
    return out


def what_if(block_id: int, at: str = "03:00", top: int = 3) -> dict:
    a = load_assumptions()
    block = load_block(block_id)
    before = ttlk(block, at, a)
    results = []
    for label, changed in candidate_changes(block, at, a):
        after = ttlk(changed, at, a)
        results.append({"label": label, "before": before["median"], "after": after["median"], "saved": before["median"] - after["median"]})
    # Prefer bigger savings; on a tie, the cheaper option (training beats recruiting, 1 beats 2).
    results.sort(key=lambda r: (-r["saved"], "Recruit" in r["label"], "2" in r["label"]))
    return {"time": at, "before": before, "options": [r for r in results if r["saved"] > 0][:top]}


@lru_cache(maxsize=32)
def overview(block_id: int, version: int = 0) -> dict:
    """Everything the dashboard's Time to Last Knock panel needs. Cached: the block
    doesn't change during a demo. `version` lets callers bust the cache after a reset."""
    a = load_assumptions()
    block = load_block(block_id)
    hours = [f"{h:02d}:00" for h in range(24)]
    curve = [{"time": t, **ttlk(block, t, a)} for t in hours]
    evening, night = ttlk(block, "19:00", a), ttlk(block, "03:00", a)
    return {
        "block_id": block_id,
        "evening": evening,
        "night": night,
        "curve": curve,
        "gap": biggest_gap(block, "03:00", a),
        "vulnerable": len(block.residents),
        "helpers": len(block.helpers),
        "assumptions": a,
    }
