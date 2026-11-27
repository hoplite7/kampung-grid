"""Week 5: network modes, the printed block card, voice notes and Silence Alert."""

import io
import time

from fastapi.testclient import TestClient

from app.ai import _drop_empty_also
from app.main import app
from app.silence import score


def _start(c):
    c.post("/control/reset")
    for beat in ["start-evening", "cyberattack", "voice-note"]:
        c.post(f"/control/{beat}")
    time.sleep(0.6)
    c.post("/control/assign-helper")
    time.sleep(0.6)


def test_block_card_has_unit_numbers_only():
    with TestClient(app) as c:
        card = c.get("/block-card/123").json()
    assert card["knock_first"][0] == "#09-12"  # Mdm Tan: oxygen in a blackout
    text = str(card)
    for secret in ["Tan", "Rajan", "oxygen", "wheelchair", "walker", "hearing"]:
        assert secret not in text
    assert all("is_essential" not in h for h in card["helpers"])
    assert "#03-05" not in [h["unit"] for h in card["helpers"]]  # essential worker left off


def test_network_down_sends_sms_and_relay_hops():
    with TestClient(app) as c:
        _start(c)
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.receive_json()
            assert c.post("/control/network-down").json()["mode"] == "low_data"
            sms = None
            for _ in range(20):
                m = ws.receive_json()
                if m["type"] == "sms" and m["helper_id"] == "aziz":
                    sms = m
                    break
            assert sms and len(sms["text"]) <= 160 and "1" in sms["text"]
            c.post("/control/mode", json={"mode": "relay"})
            for _ in range(20):
                m = ws.receive_json()
                if m["type"] == "relay" and m["helper_id"] == "aziz":
                    assert m["simulated"] is True and m["hops"][-1] == "#07-10"
                    break
            else:
                raise AssertionError("no relay message")
        assert c.get("/incidents/current").json()["incident"]["mode"] == "relay"
        assert not c.post("/control/mode", json={"mode": "carrier pigeon"}).json()["ok"]


def test_silence_scoring():
    assert score(0, 0)[0] == "clear"
    assert score(1, 0)[0] == "watch"
    assert score(2, 0)[0] == "amber"
    assert score(0, 1)[0] == "amber"
    assert score(3, 0)[0] == "red"


def test_silence_alert_ladder_needs_a_person_and_checkin_clears_it():
    with TestClient(app) as c:
        c.post("/control/reset")
        case = c.post("/control/silence-demo").json()["cases"][0]
        assert case["resident_id"] == "lim" and case["level"] == "amber" and case["step"] == 0
        # Nothing moves on its own: still step 0 until someone approves.
        assert c.get("/silence/cases").json()[0]["step"] == 0
        step = c.post(f"/silence/{case['id']}/approve").json()
        assert step["step_label"] == "Ask a nearby neighbour to knock" and step["neighbour"]["id"] == "meiling"
        # Mr Lim taps "I'm okay": the case closes.
        c.post("/checkins", json={"resident_id": "lim"})
        assert c.get("/silence/cases").json()[0]["status"] == "resolved"


def test_voice_without_whisper_explains_how_to_turn_it_on():
    with TestClient(app) as c:
        r = c.post("/reports/voice", files={"audio": ("n.webm", io.BytesIO(b"x"), "audio/webm")}, data={"sender_id": "meiling"})
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        assert r.status_code == 501 and "faster-whisper" in r.json()["detail"]


def test_brief_drops_an_empty_also_line():
    assert "ALSO" not in _drop_empty_also("Block 123\nALSO: No fake reports rejected. No rumours answered.")
    assert "ALSO: 1 fake report rejected" in _drop_empty_also("Block 123\nALSO: 1 fake report rejected")
