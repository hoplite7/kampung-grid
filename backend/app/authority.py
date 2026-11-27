"""The authority: holds the INCIDENT key, and releases its half of a profile's key
only while an official incident is active.

In real life this would be a separate server run by the agency (e.g. the one
that declares the incident), so Kampung Grid could never open a profile alone.
Here it is a separate module with its own key file, and nothing else in the
code reads that key.
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlmodel import select

from .db import get_session
from .keys import load_or_create
from .models import Incident

_AUTHORITY_KEY = load_or_create("authority", "KG_AUTHORITY_KEY")


class IncidentNotActive(Exception):
    """The authority refuses: no active incident, so no key."""


def lock_share(share: bytes, resident_id: str) -> tuple[bytes, bytes]:
    """When a profile is created, the authority locks share A with its key."""
    nonce = os.urandom(12)
    return nonce, AESGCM(_AUTHORITY_KEY).encrypt(nonce, share, resident_id.encode())


def incident_is_active(incident_id: int | None) -> bool:
    if incident_id is None:
        return False
    with get_session() as s:
        incident = s.get(Incident, incident_id)
        return incident is not None and incident.status == "active"


def release_share(nonce: bytes, locked: bytes, resident_id: str, incident_id: int | None) -> bytes:
    """Give back share A, but ONLY for an active, officially declared incident."""
    if not incident_is_active(incident_id):
        raise IncidentNotActive(f"No active incident {incident_id}: the authority will not release the key")
    return AESGCM(_AUTHORITY_KEY).decrypt(nonce, locked, resident_id.encode())


def any_active_incident() -> int | None:
    with get_session() as s:
        incident = s.exec(select(Incident).where(Incident.status == "active")).first()
        return incident.id if incident else None
