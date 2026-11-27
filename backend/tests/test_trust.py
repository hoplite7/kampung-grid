"""Checks for the trust check and rumour spotting. Run: python -m pytest -q"""

import time

from fastapi.testclient import TestClient

from app.ai import find_rumour
from app.main import app
from app.trust import starting_level


def facts(**kw):
    base = {"known_sender": True, "confirmations": 0, "unit": "#09-12", "unit_occupied": True, "resident_listed": True, "sender_recent_reports": 1}
    return {**base, **kw}


def test_known_neighbour_is_high_trust():
    level, reasons = starting_level(facts())
    assert level == "high" and "known resident" in reasons


def test_fake_report_is_low_trust_with_reasons():
    level, reasons = starting_level(facts(known_sender=False, unit="#14-03", unit_occupied=False, resident_listed=False))
    assert level == "low"
    assert reasons == ["unknown sender", "no second report", "unit #14-03 is vacant"]


def test_unknown_sender_confirmed_by_neighbour_is_trusted():
    level, _ = starting_level(facts(known_sender=False, confirmations=1))
    assert level == "high"


def test_burst_of_reports_lowers_trust():
    level, reasons = starting_level(facts(known_sender=False, sender_recent_reports=5, unit=None))
    assert level == "low" and any("reports from one sender" in r for r in reasons)


def test_water_rumour_spotted_across_languages():
    msgs = [
        "my sister say tap water contaminated, dont drink!!",
        "Air paip dah tercemar, jangan minum",
        "group chat saying the water is poisoned",
        "auntie at 9-12 not answering",
    ]
    r = find_rumour(msgs)
    assert r["found"] and sorted(r["message_numbers"]) == [1, 2, 3]


def test_second_wave_in_the_demo():
    with TestClient(app) as c:
        c.post("/control/reset")
        for beat in ["start-evening", "cyberattack", "voice-note"]:
            c.post(f"/control/{beat}")
        time.sleep(0.5)
        c.post("/control/assign-helper")
        c.post("/control/fake-report")
        time.sleep(5)
        reports = c.get("/reports").json()
        fake = next(r for r in reports if "14-03" in r["text"])
        assert fake["trust_level"] == "low" and fake["status"] == "waiting_for_human"
        rumours = c.get("/rumours").json()
        assert rumours and rumours[0]["count"] >= 3
        # The fake report must never get a helper sent.
        tasks = c.get("/incidents/current").json()["tasks"]
        assert all(t["resident_unit"] != "#14-03" for t in tasks)
        c.post("/control/reset")
