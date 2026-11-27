"""Wipe the database and load the fictional blocks from block123.json.

Run it from the backend/ folder:
    python -m seed.seed

The Reset button on the control panel calls run() too.
"""

import json
from pathlib import Path

from app.db import get_session, reset_tables
from app.models import Block, Helper, Resident, Unit
from app.vault import clear_cache, seal

SEED_FILE = Path(__file__).resolve().parent / "block123.json"


def unit_label(floor: int, number: int) -> str:
    return f"#{floor:02d}-{number:02d}"


def run(seed_file: Path = SEED_FILE) -> dict:
    data = json.loads(seed_file.read_text(encoding="utf-8"))
    reset_tables()
    clear_cache()
    counts = {"blocks": 0, "units": 0, "residents": 0, "helpers": 0}

    with get_session() as s:
        for b in data["blocks"]:
            s.add(
                Block(
                    id=b["id"],
                    name=b["name"],
                    floors=b["floors"],
                    units_per_floor=b["units_per_floor"],
                    stairwells=b["stairwells"],
                )
            )
            counts["blocks"] += 1

            stairwell_of = {n: name for name, nums in b["stairwells"].items() for n in nums}
            vacant = set(b.get("vacant", []))
            for floor in range(1, b["floors"] + 1):
                for number in range(1, b["units_per_floor"] + 1):
                    label = unit_label(floor, number)
                    s.add(
                        Unit(
                            id=f"{b['id']}-{label}",
                            block_id=b["id"],
                            label=label,
                            floor=floor,
                            number=number,
                            stairwell=stairwell_of.get(number, "A"),
                            occupied=label not in vacant,
                        )
                    )
                    counts["units"] += 1

            for r in b["residents"]:
                r = dict(r)
                # The "vulnerable" details are what an RC volunteer records during a home
                # visit. They are sealed straight away: only the encrypted profile is stored.
                profile = r.pop("vulnerable", None)
                s.add(Resident(block_id=b["id"], has_profile=profile is not None, **r))
                if profile is not None:
                    s.add(seal(r["id"], profile))
                    counts["sealed_profiles"] = counts.get("sealed_profiles", 0) + 1
                counts["residents"] += 1

            # Knock-first order for the lift-lobby card: worked out from the profiles in a
            # blackout (power out, lifts down) at the moment they're sealed. Only the order is kept.
            from app.risk import Conditions, risk_score

            order = sorted(
                ((risk_score(r["vulnerable"], r["unit"], Conditions(power_out=True, lifts_down=True))[0], r["id"]) for r in b["residents"] if r.get("vulnerable")),
                reverse=True,
            )
            for i, (_score, rid) in enumerate(order, 1):
                s.get(Resident, rid).knock_priority = i

            for h in b.get("helpers", []):
                s.add(Helper(**h))
                counts["helpers"] += 1

        s.commit()
    return counts


if __name__ == "__main__":
    print("Loaded:", run())
