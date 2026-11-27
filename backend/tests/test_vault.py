"""Prove the two-key vault works. Run: python -m pytest -q tests/test_vault.py

These are the tests to show a judge who asks "what if someone hacks your database?"
"""

import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import vault
from app.db import DB_PATH, get_session
from app.main import app
from app.models import SealedProfile


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.post("/control/reset")
        yield c
        c.post("/control/reset")


def _start_incident_and_assign(c):
    c.post("/control/start-evening")
    c.post("/control/cyberattack")
    c.post("/control/voice-note")
    time.sleep(0.5)
    c.post("/control/assign-helper")
    return c.get("/incidents/current").json()["incident"]["id"]


def test_stolen_database_reveals_nothing(client):
    """Copy the database file, as a hacker would, and search it for Mdm Tan's details."""
    stolen = Path(tempfile.mkdtemp()) / "stolen.db"
    shutil.copy(DB_PATH, stolen)
    raw = stolen.read_bytes()
    for secret in [b"oxygen", b"concentrator", b"walker", b"hard of hearing", b"knock loudly"]:
        assert secret not in raw, f"found {secret!r} in plain text in the database!"

    # What the attacker sees for her profile: scrambled bytes.
    row = sqlite3.connect(stolen).execute("SELECT ciphertext FROM sealedprofile WHERE resident_id='tan'").fetchone()
    print("\nWhat a hacker sees for Mdm Tan's profile:", row[0][:32].hex(), "...")
    assert row is not None and b"oxygen" not in row[0]


def test_system_key_alone_cannot_open_without_an_incident(client):
    """No incident declared: the authority won't release its half, so nothing opens."""
    with pytest.raises(vault.VaultLocked):
        vault.open_for_engine("tan", incident_id=None)


def test_wrong_helper_cannot_open(client):
    incident_id = _start_incident_and_assign(client)
    with pytest.raises(vault.VaultLocked):
        vault.open_for_helper("tan", incident_id, "benjamin")  # not Mdm Tan's helper


def test_assigned_helper_sees_only_need_to_know_and_is_logged(client):
    incident_id = _start_incident_and_assign(client)
    time.sleep(0.5)  # let the background unlock happen
    view, _ = vault.open_for_helper("tan", incident_id, "aziz")
    assert view["powered_equipment"] == "oxygen concentrator"
    assert "lives_alone" not in view  # not needed by the helper, so not shown
    log = client.get("/unlock-log").json()
    assert any(e["resident_id"] == "tan" and e["opened_for"] == "aziz" for e in log)


def test_tampering_is_detected(client):
    incident_id = _start_incident_and_assign(client)
    vault.clear_cache()
    with get_session() as s:
        row = s.get(SealedProfile, "tan")
        changed = bytearray(row.ciphertext)
        changed[0] ^= 0xFF  # flip one byte
        row.ciphertext = bytes(changed)
        s.add(row)
        s.commit()
    with pytest.raises(Exception):
        vault.open_for_engine("tan", incident_id)


def test_seed_file_details_never_reach_the_dashboard(client):
    """GET /blocks only says 'has a profile', never what's in it."""
    text = json.dumps(client.get("/blocks/123").json())
    assert "oxygen" not in text and "walker" not in text
