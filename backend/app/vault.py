"""The two-key vault for Sealed Profiles. (Person 4 owns this.)

How it works, in one picture: each profile is locked in its own box with its own
key (the data key). The data key is cut into two halves (XOR: each half alone is
random noise). Half A is locked by the AUTHORITY's incident key, half B by the
SYSTEM key. Rebuilding the data key needs both halves, so opening a profile needs
both keys, and the authority only hands over its half during an active incident.

What a stolen database contains: scrambled profiles and two locked halves.
Nothing readable. (See tests/test_vault.py, the "stolen database" test.)

Who can open a profile, and when:
  - the crisis engine, during an active incident, to rank who needs help first;
  - an assigned helper, during an active incident, and they see ONLY the
    need-to-know fields (equipment, mobility, hearing, languages, how to knock).
Every opening is written to the unlock log.
"""

import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlmodel import select

from . import authority
from .db import get_session
from .keys import load_or_create
from .models import SealedProfile, Task, UnlockLog

_SYSTEM_KEY = load_or_create("system", "KG_SYSTEM_KEY")

NEED_TO_KNOW_FIELDS = ["powered_equipment", "equipment_battery_hours", "mobility", "hearing", "languages", "how_to_knock"]

# Profiles the engine has opened for the current incident (cleared when it ends or on Reset),
# so ranking doesn't re-open and re-log every profile on every dashboard refresh.
_engine_cache: dict[tuple[int, str], dict] = {}


class VaultLocked(Exception):
    """The profile can't be opened right now (no incident, or not your resident)."""


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


# ---- Sealing (when an RC volunteer saves a profile) --------------------------


def seal(resident_id: str, profile: dict) -> SealedProfile:
    """Encrypt a profile. The plain profile and the data key are never stored."""
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)  # a fresh one-time number for every encryption
    aad = resident_id.encode()  # ties the ciphertext to this resident: it can't be swapped onto another
    ciphertext = AESGCM(data_key).encrypt(nonce, json.dumps(profile).encode(), aad)

    share_a = os.urandom(32)
    share_b = _xor(data_key, share_a)

    a_nonce, a_locked = authority.lock_share(share_a, resident_id)
    b_nonce = os.urandom(12)
    b_locked = AESGCM(_SYSTEM_KEY).encrypt(b_nonce, share_b, aad)

    return SealedProfile(
        resident_id=resident_id,
        nonce=nonce,
        ciphertext=ciphertext,
        share_a_nonce=a_nonce,
        share_a=a_locked,
        share_b_nonce=b_nonce,
        share_b=b_locked,
    )


# ---- Unsealing ----------------------------------------------------------------


def _unseal(resident_id: str, incident_id: int | None) -> dict:
    with get_session() as s:
        row = s.get(SealedProfile, resident_id)
    if row is None:
        raise VaultLocked(f"No Sealed Profile for {resident_id}")
    aad = resident_id.encode()
    try:
        share_a = authority.release_share(row.share_a_nonce, row.share_a, resident_id, incident_id)
    except authority.IncidentNotActive as exc:
        raise VaultLocked(str(exc)) from exc
    share_b = AESGCM(_SYSTEM_KEY).decrypt(row.share_b_nonce, row.share_b, aad)
    data_key = _xor(share_a, share_b)
    # AES-GCM also checks nothing was tampered with: a changed byte raises an error here.
    return json.loads(AESGCM(data_key).decrypt(row.nonce, row.ciphertext, aad))


def _log(resident_id: str, incident_id: int | None, opened_for: str, purpose: str, fields: list[str]) -> dict:
    with get_session() as s:
        entry = UnlockLog(
            resident_id=resident_id, incident_id=incident_id, opened_for=opened_for, purpose=purpose, fields_shown=fields
        )
        s.add(entry)
        s.commit()
        s.refresh(entry)
        return log_out(entry)


def log_out(entry: UnlockLog) -> dict:
    from datetime import timezone

    created = entry.created_at.replace(tzinfo=timezone.utc) if entry.created_at.tzinfo is None else entry.created_at
    return {
        "id": entry.id,
        "resident_id": entry.resident_id,
        "incident_id": entry.incident_id,
        "opened_for": entry.opened_for,
        "purpose": entry.purpose,
        "fields_shown": entry.fields_shown,
        "created_at": created,
    }


def open_for_engine(resident_id: str, incident_id: int | None) -> dict:
    """The crisis engine reads a profile to rank who needs help first.
    Only works during an active incident. Logged once per profile per incident."""
    key = (incident_id or -1, resident_id)
    if key in _engine_cache:
        return _engine_cache[key]
    profile = _unseal(resident_id, incident_id)
    _engine_cache[key] = profile
    _log(resident_id, incident_id, "crisis engine", "ranking", sorted(profile.keys()))
    return profile


def need_to_know(profile: dict) -> dict:
    """Only what a helper needs right now. Never the full record."""
    return {k: profile[k] for k in NEED_TO_KNOW_FIELDS if profile.get(k)}


def open_for_helper(resident_id: str, incident_id: int, helper_id: str) -> tuple[dict, dict | None]:
    """An assigned helper gets the need-to-know view.

    Checks, in order: (1) the incident is active (the authority's key), and
    (2) this helper really is assigned to this resident in this incident.
    Returns (need_to_know_fields, new_log_entry_or_None_if_already_logged).
    """
    with get_session() as s:
        assigned = s.exec(
            select(Task).where(
                Task.incident_id == incident_id,
                Task.resident_id == resident_id,
                Task.helper_id == helper_id,
                Task.status.in_(["sent", "on_the_way", "reached", "need_help"]),
            )
        ).first()
        already = s.exec(
            select(UnlockLog).where(
                UnlockLog.resident_id == resident_id,
                UnlockLog.incident_id == incident_id,
                UnlockLog.opened_for == helper_id,
            )
        ).first()
    if assigned is None:
        raise VaultLocked(f"{helper_id} is not assigned to {resident_id}")
    view = need_to_know(_unseal(resident_id, incident_id))
    entry = None if already else _log(resident_id, incident_id, helper_id, "helper task", sorted(view.keys()))
    return view, entry


def clear_cache() -> None:
    _engine_cache.clear()


def open_for_responder(resident_id: str, incident_id: int, who: str) -> dict:
    """Official responders (e.g. SCDF on arrival) get the need-to-know view. Always logged."""
    view = need_to_know(_unseal(resident_id, incident_id))
    _log(resident_id, incident_id, who, "responder handover", sorted(view.keys()))
    return view
