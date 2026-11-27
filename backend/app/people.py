"""Real people in the demo: judges who scan the QR code and play a helper.

A claimed helper is treated like a real phone (never simulated, waits longer
before a task moves on). Claims live in memory only and vanish on Reset or restart:
we never store a judge's name or number, and a Telegram chat ID is deleted the
moment the demo is reset or they send /stop.
"""

import os

from sqlmodel import select

from .db import get_session
from .models import Helper, Resident

# Roles judges can take. Aziz is the presenter's phone; Nurul is the neighbour who
# never answers (so Mr Rajan is NOT REACHED). Neither is offered.
JOIN_ROLES = [r.strip() for r in os.getenv("KG_JOIN_ROLES", "kavitha,benjamin,meiling,ryan").split(",") if r.strip()]

# helper_id -> "web" or "telegram"
CLAIMS: dict[str, str] = {}


def is_real(helper_id: str | None) -> bool:
    from .crisis import FEATURED_HELPERS

    return bool(helper_id) and (helper_id in FEATURED_HELPERS or helper_id in CLAIMS)


def roles() -> list[dict]:
    with get_session() as s:
        out = []
        for rid in JOIN_ROLES:
            r, h = s.get(Resident, rid), s.get(Helper, rid)
            if r is None or h is None:
                continue
            out.append(
                {
                    "helper_id": rid,
                    "name": r.name,
                    "unit": r.unit,
                    "skills": h.skills,
                    "languages": h.languages,
                    "taken": rid in CLAIMS,
                }
            )
    return out


def claim(helper_id: str, via: str) -> dict:
    if helper_id not in JOIN_ROLES:
        raise ValueError("That role can't be taken")
    if CLAIMS.get(helper_id) not in (None, via):
        raise ValueError("Someone already took that role")
    CLAIMS[helper_id] = via
    return next(r for r in roles() if r["helper_id"] == helper_id)


def release(helper_id: str) -> None:
    CLAIMS.pop(helper_id, None)


def clear() -> None:
    CLAIMS.clear()


def helper_language(helper_id: str) -> str:
    with get_session() as s:
        h = s.get(Helper, helper_id)
    return (h.languages[0] if h and h.languages else "en") or "en"
