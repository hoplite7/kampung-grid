"""Week 6: judges join from their own phones (web or Telegram)."""

import asyncio
import time

from fastapi.testclient import TestClient

from app import people, telegram_bot
from app.main import app


def _start(c):
    c.post("/control/reset")
    for beat in ["start-evening", "cyberattack", "voice-note"]:
        c.post(f"/control/{beat}")
    time.sleep(0.6)


def test_join_needs_consent_and_one_person_per_role():
    with TestClient(app) as c:
        c.post("/control/reset")
        roles = c.get("/join/roles").json()["roles"]
        ids = [r["helper_id"] for r in roles]
        assert "aziz" not in ids and "nurul" not in ids and "kavitha" in ids
        assert c.post("/join", json={"helper_id": "kavitha"}).status_code == 400
        assert c.post("/join", json={"helper_id": "kavitha", "consent": True}).status_code == 200
        assert c.post("/join", json={"helper_id": "aziz", "consent": True}).status_code == 409
        assert [r for r in c.get("/join/roles").json()["roles"] if r["helper_id"] == "kavitha"][0]["taken"]
        c.post("/control/reset")
        assert not people.CLAIMS


def test_a_judge_is_never_simulated():
    with TestClient(app) as c:
        _start(c)
        c.post("/join", json={"helper_id": "kavitha", "consent": True})
        c.post("/control/assign-helper")
        time.sleep(0.6)
        tasks = c.get("/tasks?helper_id=kavitha").json()
        assert tasks and all(not t["simulated"] for t in tasks)
        c.post("/control/reset")


def test_telegram_flow_with_a_fake_telegram(monkeypatch):
    sent = []

    async def fake_call(method, **params):
        sent.append((method, params))
        return {"ok": True, "result": []}

    monkeypatch.setattr(telegram_bot, "call", fake_call)
    with TestClient(app) as c:
        from app.live import hub

        if telegram_bot.on_live not in hub.listeners:
            hub.listeners.append(telegram_bot.on_live)
        try:
            _start(c)
            portal = c.portal  # run coroutines inside the app's event loop

            portal.call(telegram_bot.handle_update, {"message": {"chat": {"id": 42}, "text": "/start kavitha"}})
            assert telegram_bot.CHATS == {42: "kavitha"}
            assert "playing Kavitha" in sent[-1][1]["text"]

            c.post("/control/assign-helper")
            for _ in range(30):
                if any("A neighbour needs you" in p.get("text", "") for _, p in sent):
                    break
                time.sleep(0.2)
            task_msg = next(p for _, p in sent if "A neighbour needs you" in p.get("text", ""))
            data = task_msg["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
            assert data.endswith(":on_the_way")
            task_id = int(data.split(":")[1])

            # Someone else's chat can't press their buttons.
            portal.call(telegram_bot.handle_button, {"id": "x", "data": data, "message": {"chat": {"id": 7}}})
            assert c.get("/tasks?helper_id=kavitha").json()[0]["status"] == "sent"

            portal.call(telegram_bot.handle_button, {"id": "y", "data": data, "message": {"chat": {"id": 42}}})
            portal.call(telegram_bot.handle_button, {"id": "z", "data": f"t:{task_id}:reached", "message": {"chat": {"id": 42}}})
            assert [t for t in c.get("/tasks?helper_id=kavitha").json() if t["id"] == task_id][0]["status"] == "reached"

            c.post("/control/reset")
            time.sleep(0.3)
            assert telegram_bot.CHATS == {}
            assert any("chat ID has been deleted" in p.get("text", "") for _, p in sent)
        finally:
            hub.listeners.remove(telegram_bot.on_live)
            telegram_bot.CHATS.clear()


def test_test_job_reaches_a_judge_without_the_beats():
    with TestClient(app) as c:
        c.post("/control/reset")
        assert not c.post("/control/test-job", json={}).json()["ok"]  # nobody joined yet
        c.post("/join", json={"helper_id": "ryan", "consent": True})
        r = c.post("/control/test-job", json={}).json()
        assert r["ok"] and r["sent"] == ["ryan"]
        tasks = c.get("/tasks?helper_id=ryan").json()
        assert len(tasks) == 1 and not tasks[0]["simulated"] and tasks[0]["via"] == "web"
        assert tasks[0]["resident_id"] != "tan"  # Mdm Tan stays for the presenter
        assert tasks[0]["resident_unit"] in {"#13-07", "#12-02"}  # nearest to Ryan at #12-09
        # Pressing it again doesn't pile up jobs.
        c.post("/control/test-job", json={})
        assert len(c.get("/tasks?helper_id=ryan").json()) == 1
        c.post("/control/reset")


def test_saved_answers_stand_in_when_claude_is_unreachable(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app import ai

    monkeypatch.setattr(ai, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(ai, "_cache", None)

    class Online:
        class messages:
            @staticmethod
            def create(**kw):
                block = SimpleNamespace(type="tool_use", name="write_text", input={"text": "Saved brief"})
                return SimpleNamespace(stop_reason="tool_use", content=[block])

    class Offline:
        class messages:
            @staticmethod
            def create(**kw):
                raise ConnectionError("venue wifi down")

    monkeypatch.setattr(ai, "_client", ai._Client(Online))
    assert ai._text_call("system", "question") == "Saved brief"
    assert (tmp_path / "cache.json").exists()

    monkeypatch.setattr(ai, "_client", ai._Client(Offline))
    assert ai._text_call("system", "question") == "Saved brief"  # same question: saved answer
    assert ai._text_call("system", "a different question") is None  # never seen: normal backup rules
