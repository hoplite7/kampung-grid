"""Checks for Time to Last Knock and the Week 4 beats. Run: python -m pytest -q"""

import time

from fastapi.testclient import TestClient

from app import sim
from app.main import app


def test_night_is_slower_than_evening_and_repeatable():
    with TestClient(app) as c:
        c.post("/control/reset")
        o = c.get("/sim/overview").json()
        assert o["night"]["median"] > o["evening"]["median"]
        assert o["night"]["p90"] >= o["night"]["median"]
        # Same seed, same answer: rehearsals always show the same numbers.
        again = sim.ttlk(sim.load_block(123), "03:00")
        assert again["median"] == o["night"]["median"]


def test_gap_and_what_if_point_at_floors_10_to_14():
    with TestClient(app) as c:
        c.post("/control/reset")
        assert "floors 10 to 14" in c.get("/sim/overview").json()["gap"]
        result = c.post("/sim/what-if", json={"time": "03:00"}).json()
        best = result["options"][0]
        assert "10 to 14" in best["label"] and best["saved"] > 0
        assert result["summary"]["text"]


def test_block_125_reallocation_and_handover_brief():
    with TestClient(app) as c:
        c.post("/control/reset")
        for beat in ["start-evening", "cyberattack", "voice-note"]:
            c.post(f"/control/{beat}")
        time.sleep(0.5)
        c.post("/control/assign-helper")

        alert = c.post("/control/block-125").json()
        assert alert["unreached"] >= 3  # nobody home to help in Block 125 at night
        moved = c.post("/responders/reallocate", json={"block_id": 125}).json()
        assert moved["residents"] == alert["unreached"]

        assert c.post("/control/scdf-arrives").json()["ok"]
        brief = c.get("/handover-brief").json()
        assert "Block 123" in brief["text"] and "NOT REACHED" in brief["text"].upper()

        # Family cover: the nurse's father is on a neighbour's list.
        fam = c.get("/family/priya").json()
        assert fam["dependent_unit"] == "#11-04" and fam["status"] in {"on_the_way", "reached"}
        c.post("/control/reset")
