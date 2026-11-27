"""Database tables for Kampung Grid.

Each class below is one table. SQLModel lets us write tables as Python classes.
Lists and dicts (like a helper's skills) are stored as JSON columns.

Tables: blocks, units, residents, helpers, incidents, reports, tasks, events,
sealed_profiles + unlock_log (Week 3: the two-key vault), rumours (Week 3).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


class Block(SQLModel, table=True):
    id: int = Field(primary_key=True)  # e.g. 123
    name: str  # "Block 123"
    floors: int
    units_per_floor: int
    # Which units each stairwell serves, e.g. {"A": [1, 2, 3], "B": [4, 5, 6]}
    stairwells: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Unit(SQLModel, table=True):
    id: str = Field(primary_key=True)  # "123-#09-12" (block + label)
    block_id: int = Field(foreign_key="block.id", index=True)
    label: str  # "#09-12"
    floor: int
    number: int
    stairwell: str  # "A" or "B"
    occupied: bool = True
    # Live status shown on the dashboard: normal, task_sent, reached, escalated
    status: str = "normal"


class Resident(SQLModel, table=True):
    id: str = Field(primary_key=True)  # short id, e.g. "tan"
    name: str
    block_id: int = Field(foreign_key="block.id", index=True)
    unit: str  # "#09-12"
    phone: str  # fake numbers only
    language: str  # en, zh, ms, ta, hokkien ...
    age: Optional[int] = None
    has_smartphone: bool = True
    is_essential_worker: bool = False
    essential_role: Optional[str] = None  # "nurse", "utility engineer"
    dependent_unit: Optional[str] = None  # family member to cover in a crisis
    silence_opt_in: bool = False  # opted in to Silence Alert check-ins
    # True if this resident has a Sealed Profile. The details themselves are only
    # ever stored encrypted, in sealed_profiles (see vault.py).
    has_profile: bool = False
    # Knock-first order for the printed block card (1 = first), set when the profile is
    # sealed. A number, not a reason: it reveals nothing about the person's needs.
    knock_priority: Optional[int] = None


class Helper(SQLModel, table=True):
    resident_id: str = Field(primary_key=True, foreign_key="resident.id")
    skills: list = Field(default_factory=list, sa_column=Column(JSON))  # ["cpr", "first_aid"]
    languages: list = Field(default_factory=list, sa_column=Column(JSON))
    # When they are usually home, e.g. ["18:00-08:00"] (can wrap past midnight)
    home_hours: list = Field(default_factory=list, sa_column=Column(JSON))
    sgsecure_responder: bool = False


class Incident(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    block_id: int = Field(foreign_key="block.id")
    type: str  # "blackout"
    cause: str  # "grid cyberattack"
    mode: str = "full"  # full, low_data, relay, no_phone
    status: str = "active"  # active, closed
    started_at: datetime = Field(default_factory=now)
    ended_at: Optional[datetime] = None


class Report(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    block_id: int = Field(foreign_key="block.id")
    sender_id: Optional[str] = None  # resident id if known
    sender_phone: Optional[str] = None
    text: str
    # What the AI understood (filled by ai.parse_report)
    parsed: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    resident_id: Optional[str] = None  # who the report is about, if matched
    # Trust check (Week 3)
    trust_level: Optional[str] = None  # high, medium, low
    trust_reasons: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "new"  # new, acted_on, waiting_for_human, rejected
    created_at: datetime = Field(default_factory=now)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: int = Field(foreign_key="incident.id")
    resident_id: str  # person to check on
    helper_id: Optional[str] = None
    rank: int = 0  # 1 = most urgent
    score: int = 0
    reasons: list = Field(default_factory=list, sa_column=Column(JSON))  # ["lives alone", "oxygen concentrator", ...]
    # Written by Claude: {"headline": str, "steps": [str], "bring": [str], "language": str, "sms": str, "source": ...}
    # None while Claude is still writing it.
    instructions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    channel: str = "app"  # app, sms, relay
    # sent -> on_the_way -> reached | need_help ; or escalated (no helper) ; reassigned (moved to another helper)
    status: str = "sent"
    # True for fictional neighbours the demo plays automatically (only featured helpers use real phones).
    simulated: bool = False
    # Set when an official responder team goes instead of a neighbour, e.g. "SCDF Team B".
    responder: Optional[str] = None
    # Family cover: the essential worker whose family member this is (so they can report for duty).
    family_of: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Event(SQLModel, table=True):
    """Everything that happens, in order. Feeds the handover brief and debriefs."""

    id: Optional[int] = Field(default=None, primary_key=True)
    block_id: Optional[int] = None
    type: str
    details: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class SealedProfile(SQLModel, table=True):
    """A vulnerable resident's needs, encrypted. Unreadable without BOTH keys.

    ciphertext = the profile encrypted with its own random data key (AES-GCM).
    share_a    = half of the data key, locked with the AUTHORITY's incident key.
    share_b    = the other half, locked with the SYSTEM key.
    Either half alone is random noise; the plain profile and data key are never stored.
    """

    resident_id: str = Field(primary_key=True, foreign_key="resident.id")
    nonce: bytes
    ciphertext: bytes
    share_a_nonce: bytes
    share_a: bytes
    share_b_nonce: bytes
    share_b: bytes
    created_by: str = "RC volunteer (demo)"
    consent_at: datetime = Field(default_factory=now)


class UnlockLog(SQLModel, table=True):
    """Every time a Sealed Profile is opened: who, when, why, and what was shown."""

    id: Optional[int] = Field(default=None, primary_key=True)
    resident_id: str
    incident_id: Optional[int] = None
    opened_for: str  # "crisis engine (ranking)" or a helper id
    purpose: str  # "ranking", "helper task"
    fields_shown: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class Rumour(SQLModel, table=True):
    """A claim spreading through neighbour messages, flagged for an official to check."""

    id: Optional[int] = Field(default=None, primary_key=True)
    block_id: int
    claim: str  # "the tap water is contaminated"
    count: int  # how many messages repeat it
    report_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "flagged"  # flagged, answered, dismissed
    verified_answer: Optional[str] = None
    source: str = "claude"  # claude or fallback
    created_at: datetime = Field(default_factory=now)


class SilenceCase(SQLModel, table=True):
    """Silence Alert: an opted-in senior who may need a knock, and how far up the ladder we are."""

    id: Optional[int] = Field(default=None, primary_key=True)
    resident_id: str
    level: str  # watch, amber, red
    signals: list = Field(default_factory=list, sa_column=Column(JSON))  # ["missed check-in 2 days", ...]
    step: int = 0  # index into the escalation ladder; a person approves each next step
    status: str = "open"  # open, resolved
    outcome: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
