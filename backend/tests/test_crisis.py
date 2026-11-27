"""Checks for the crisis engine. Run: python -m pytest -q

These protect the demo: if a change to the seed data or the scoring breaks
"Mdm Tan is #1 and Aziz is her helper", these tests fail before the pitch does.
"""

import time

from fastapi.testclient import TestClient

from app.crisis import is_home
from app.main import app
from app.risk import Conditions, risk_score


def test_is_home_wraps_past_midnight():
    assert is_home(["18:00-08:00"], "21:00")
    assert is_home(["18:00-08:00"], "03:00")
    assert not is_home(["18:00-08:00"], "12:00")
    assert is_home(["00:00-24:00"], "15:30")
    assert not is_home(["08:00-23:00"], "23:30")


def test_risk_score_explains_itself():
    vulnerable = {"lives_alone": True, "powered_equipment": "oxygen concentrator", "mobility": "walker"}
    score, reasons = risk_score(vulnerable, "#09-12", Conditions(power_out=True, lifts_down=True))
    assert score == 20 + 40 + 15 + 10
    assert "lives alone" in reasons and "lifts down" in reasons and "level 9" in reasons


def test_reached_resident_scores_zero():
    score, reasons = risk_score({"lives_alone": True}, "#05-08", Conditions(already_reached=True))
    assert score == 0 and reasons == []


def test_demo_flow_mdm_tan_first_and_aziz_helps():
    with TestClient(app) as c:
        c.post("/control/reset")
        assert c.post("/control/assign-helper").json()["ok"] is False  # needs an incident first
        c.post("/control/start-evening")
        c.post("/control/cyberattack")
        c.post("/control/voice-note")
        time.sleep(0.5)  # let the report be read
        assert c.post("/control/assign-helper").json()["ok"] is True

        state = c.get("/incidents/current").json()
        assert state["ranked"][0]["resident_id"] == "tan"
        tan_task = next(t for t in state["tasks"] if t["resident_id"] == "tan")
        assert tan_task["helper_id"] == "aziz"
        assert tan_task["simulated"] is False  # Aziz is the real phone in the demo

        # Essential workers are never asked: they're reporting for duty.
        helpers = {t["helper_id"] for t in state["tasks"]}
        assert "priya" not in helpers and "daniel" not in helpers

        # Aziz taps through.
        assert c.post(f"/tasks/{tan_task['id']}/status", json={"status": "on_the_way"}).json()["status"] == "on_the_way"
        assert c.post(f"/tasks/{tan_task['id']}/status", json={"status": "reached"}).json()["status"] == "reached"
        unit = next(u for u in c.get("/blocks/123").json()["units"] if u["label"] == "#09-12")
        assert unit["status"] == "reached"
        c.post("/control/reset")
