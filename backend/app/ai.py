"""Every call to Claude lives in this file.

Week 1: parse_report() turns a messy neighbour message into a structured alert.

If there is no API key, or Claude can't be reached, we fall back to a simple
rule-based parser so the app keeps working. Every result says which one was
used ("source": "claude" or "fallback"), so we never pass off a rule as AI.
"""

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

load_dotenv()

FAST_MODEL = os.getenv("KG_FAST_MODEL", "claude-haiku-5-5")
STRONG_MODEL = os.getenv("KG_STRONG_MODEL", "claude-sonnet-5-5")
AI_TIMEOUT_SECONDS = float(os.getenv("KG_AI_TIMEOUT", "8"))
# Room for each answer. Newer models may think before answering, and that thinking
# counts towards this limit, so it's generous. Only tokens actually used are billed.
MAX_TOKENS = int(os.getenv("KG_AI_MAX_TOKENS", "4000"))
# Writing a whole instruction card takes longer than reading a short report, and it
# happens in the background, so it gets more time.
AI_WRITE_TIMEOUT_SECONDS = float(os.getenv("KG_AI_WRITE_TIMEOUT", "25"))

_client = None

# ---------------------------------------------------------------------------
# Backup answers: every good answer from Claude is saved to ai_cache.json.
# If a call fails later (venue internet down), the saved answer to the SAME question
# is used, so the demo looks identical. Rehearse once online and the file fills up.
# KG_AI_OFFLINE=true skips the internet completely (instant, saved answers only).
# ---------------------------------------------------------------------------

CACHE_PATH = Path(os.getenv("KG_AI_CACHE", Path(__file__).resolve().parent.parent / "ai_cache.json"))
AI_OFFLINE = os.getenv("KG_AI_OFFLINE", "false").lower() == "true"
_cache_lock = threading.Lock()
_cache: dict | None = None
CACHE_STATS = {"saved": 0, "used": 0}


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text())
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _cache_key(kw: dict) -> str:
    # The model and timeout aren't part of the question, so a fast-model answer can stand in.
    question = {k: kw.get(k) for k in ("system", "messages", "tool_choice")}
    question["tools"] = [t.get("name") for t in kw.get("tools", [])]
    return hashlib.sha1(json.dumps(question, sort_keys=True, default=str).encode()).hexdigest()


def _save(key: str, response) -> None:
    blocks = []
    for b in response.content:
        if b.type == "tool_use":
            blocks.append({"type": "tool_use", "name": b.name, "input": dict(b.input)})
        elif b.type == "text":
            blocks.append({"type": "text", "text": b.text})
    with _cache_lock:
        cache = _load_cache()
        cache[key] = {"stop_reason": response.stop_reason, "content": blocks}
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
        tmp.replace(CACHE_PATH)
    CACHE_STATS["saved"] = len(cache)


def _rebuild(saved: dict):
    CACHE_STATS["used"] += 1
    return SimpleNamespace(stop_reason=saved["stop_reason"], content=[SimpleNamespace(**b) for b in saved["content"]])


class _Messages:
    def __init__(self, real):
        self.real = real

    def create(self, **kw):
        key = _cache_key(kw)
        saved = _load_cache().get(key)
        if AI_OFFLINE or self.real is None:
            if saved:
                return _rebuild(saved)
            raise RuntimeError("offline and no saved answer for this question")
        try:
            response = self.real.messages.create(**kw)
        except Exception as exc:
            if saved:
                print(f"[ai] Claude unreachable ({exc.__class__.__name__}): using the saved answer")
                return _rebuild(saved)
            raise
        if response.stop_reason != "max_tokens":
            try:
                _save(key, response)
            except OSError as exc:
                print(f"[ai] couldn't save a backup answer: {exc}")
        return response


class _Client:
    def __init__(self, real):
        self.messages = _Messages(real)


def _get_client():
    """Create the Claude client once. In offline mode it only answers from saved answers."""
    global _client
    if _client is None:
        if os.getenv("ANTHROPIC_API_KEY") and not AI_OFFLINE:
            import anthropic

            _client = _Client(anthropic.Anthropic(timeout=AI_TIMEOUT_SECONDS, max_retries=1))
        elif AI_OFFLINE or _load_cache():
            _client = _Client(None)  # no key or offline: saved answers only
    return _client


def cache_status() -> dict:
    return {"offline": AI_OFFLINE, "saved_answers": len(_load_cache()), "used_this_run": CACHE_STATS["used"], "key_set": bool(os.getenv("ANTHROPIC_API_KEY"))}


# ---------------------------------------------------------------------------
# parse_report
# ---------------------------------------------------------------------------

RECORD_ALERT_TOOL = {
    "name": "record_alert",
    "description": "Record the structured alert extracted from a neighbour's crisis message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "unit": {
                "type": ["string", "null"],
                "description": "Unit in the form #FF-UU, e.g. #09-12. Must be one of the known units, or null if unclear.",
            },
            "person_hint": {
                "type": ["string", "null"],
                "description": "How the sender referred to the person, e.g. 'auntie', 'old man'.",
            },
            "concern": {
                "type": "string",
                "description": "Short plain-English summary of the problem, e.g. 'not answering door, bad smell'.",
            },
            "urgency": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "1 = minor, 5 = possible life-threatening emergency.",
            },
            "language": {
                "type": "string",
                "description": "Language of the message: Singlish, English, Mandarin, Malay, Tamil, Hokkien, mixed...",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "How sure you are about the unit and the concern.",
            },
        },
        "required": ["unit", "person_hint", "concern", "urgency", "language", "confidence"],
    },
}

PARSE_SYSTEM_PROMPT = """You read crisis messages sent by residents of a Singapore HDB block during an emergency.
Messages are often messy: Singlish, Mandarin, Malay, Tamil or a mix, with typos and no punctuation.

Extract one structured alert and record it with the record_alert tool.

Rules:
- Unit numbers may be written as "9-12", "#09-12", "09-12", "level 9 unit 12", "9楼12号" and so on.
  Always output them as #FF-UU with two digits each, e.g. #09-12.
- Only use a unit that appears in the list of known units. Never invent one.
  If the unit is unclear or not in the list, set unit to null and lower your confidence.
- If the message names a resident instead of a unit ("Mdm Tan", "Uncle Lim"), use the residents list
  to find their unit. Only do this if exactly one resident fits; if several could fit, set unit to null.
- Urgency 5 means a possible threat to life (not responding, bad smell, collapse, fire, smoke,
  cannot breathe, medical equipment without power). Urgency 1 means minor.
- The concern must be a short plain-English summary, not a translation of the whole message.
- If the message is a joke, spam or not about an emergency, use urgency 1 and confidence below 0.3."""


def parse_report(text: str, known_units: list[str], residents: list[tuple[str, str]] | None = None) -> dict:
    """Turn a messy message into a structured alert dict.

    known_units: every unit label in the block, e.g. ["#01-01", ...]
    residents:   (name, unit) pairs, so "Mdm Tan not answering" can be matched without a unit.
                 Names and units only: never pass medical details to this function.

    Returns: {unit, person_hint, concern, urgency, language, confidence, source}
    """
    residents = residents or []
    client = _get_client()
    if client is not None:
        try:
            resident_lines = "\n".join(f"- {name}: {unit}" for name, unit in residents)
            response = client.messages.create(
                model=FAST_MODEL,
                max_tokens=MAX_TOKENS,
                system=PARSE_SYSTEM_PROMPT,
                tools=[RECORD_ALERT_TOOL],
                tool_choice={"type": "tool", "name": "record_alert"},
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Known units in this block: {', '.join(known_units)}\n\n"
                            f"Residents (name: unit):\n{resident_lines or '- (none listed)'}\n\n"
                            f"Message:\n{text}"
                        ),
                    }
                ],
            )
            for block in response.content:
                if block.type == "tool_use" and block.name == "record_alert":
                    result = dict(block.input)
                    result["unit"] = _normalise_unit(result.get("unit"), known_units)
                    result["source"] = "claude"
                    return result
        except Exception as exc:  # network down, timeout, bad key...
            print(f"[ai] Claude call failed, using fallback: {exc}")
    return _fallback_parse(text, known_units, residents)


# ---------------------------------------------------------------------------
# Fallback: simple rules, used only when Claude is unavailable
# ---------------------------------------------------------------------------

_UNIT_PATTERNS = [
    re.compile(r"#?\s*(\d{1,2})\s*-\s*(\d{1,3})"),  # 9-12, #09-12
    re.compile(r"(?:level|lvl|floor|storey|tingkat)\s*(\d{1,2})\D{0,12}?(?:unit|#|no\.?)\s*(\d{1,3})", re.I),
    re.compile(r"(\d{1,2})\s*楼\s*(\d{1,3})"),  # 9楼12号
]

_URGENT_WORDS = [
    "smell", "never open", "not open", "no answer", "not answering", "collapse", "fall", "fell",
    "fire", "smoke", "blood", "cannot breathe", "can't breathe", "oxygen", "unconscious", "faint",
    "busuk", "tak buka", "pengsan", "api", "臭", "不开门", "晕", "火",
]


def _normalise_unit(unit: str | None, known_units: list[str]) -> str | None:
    if not unit:
        return None
    m = re.search(r"(\d{1,2})\s*-\s*(\d{1,3})", unit)
    if not m:
        return None
    label = f"#{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return label if label in known_units else None


_TITLES = ("mdm", "madam", "mr", "mrs", "ms", "uncle", "auntie", "aunty")


def _name_aliases(name: str) -> list[str]:
    """'Mdm Tan Ah Moi' -> ['mdm tan', 'madam tan', 'auntie tan', ...]. Only for titled names."""
    words = name.lower().split()
    if len(words) < 2 or words[0] not in _TITLES:
        return []
    surname = words[1]
    return [f"{t} {surname}" for t in _TITLES]


def _fallback_parse(text: str, known_units: list[str], residents: list[tuple[str, str]] | None = None) -> dict:
    unit = None
    for pattern in _UNIT_PATTERNS:
        m = pattern.search(text)
        if m:
            candidate = f"#{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            if candidate in known_units:
                unit = candidate
                break
    lowered = text.lower()
    if unit is None and residents:
        # Match a titled name like "Mdm Tan" only if exactly one resident fits.
        matches = {u for name, u in residents if any(a in lowered for a in _name_aliases(name))}
        if len(matches) == 1:
            unit = matches.pop()
    hits = [w for w in _URGENT_WORDS if w in lowered]
    urgency = 5 if len(hits) >= 2 else 4 if hits else 2
    return {
        "unit": unit,
        "person_hint": None,
        "concern": ", ".join(hits) if hits else "unclear",
        "urgency": urgency,
        "language": "unknown",
        "confidence": 0.5 if unit and hits else 0.3 if unit else 0.1,
        "source": "fallback",
    }


# ---------------------------------------------------------------------------
# write_instruction: a short task for a helper, in their own language
# ---------------------------------------------------------------------------

LANGUAGE_NAMES = {
    "en": "English",
    "ms": "Malay",
    "zh": "Simplified Chinese (Mandarin)",
    "ta": "Tamil",
    "hokkien": "Simplified Chinese (the reader speaks Hokkien)",
}

WRITE_TASK_TOOL = {
    "name": "write_task",
    "description": "Write the instruction card a neighbour sees on their phone.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "One short line: who to check on, where, how soon. E.g. 'Check on Mdm Tan, #09-12, now'.",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 4,
                "description": "2-4 short, concrete steps. Plain words, no jargon.",
            },
            "bring": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 3,
                "description": "Up to 3 things to bring (torch, phone, power bank...).",
            },
            "sms": {
                "type": "string",
                "description": "The same task as ONE text message of at most 160 characters, starting 'KG:' and ending 'Reply 1=reached 2=need help'.",
            },
        },
        "required": ["headline", "steps", "bring", "sms"],
    },
}

WRITE_TASK_SYSTEM_PROMPT = """You write short, calm instruction cards for neighbours helping each other during an emergency
in a Singapore HDB block. The helper is a volunteer, not a professional.

Rules:
- Write EVERYTHING in the helper's language (given below): the headline, every step, every item to
  bring, and the sms. Not a single English word unless the helper's language is English.
  Keep names, unit numbers and 995 as they are.
- The whole card must be readable in a few seconds: short sentences, about 40 words in total.
- Only use the facts given. Never invent medical details.
- Never tell the helper to do anything dangerous or beyond basic help. If someone is unresponsive or
  in danger, the steps must include calling 995 (SCDF).
- Lifts are down when stated: say to take the stairs and which stairwell.
- The sms must be at most 160 characters."""


def write_instruction(
    resident_name: str,
    unit: str,
    need_to_know: dict,
    helper_name: str,
    helper_language: str,
    helper_skills: list[str],
    stairwell: str,
    lifts_down: bool,
    report_concern: str | None = None,
) -> dict:
    """Return {headline, steps, bring, sms, language, source}.

    need_to_know: ONLY the fields a helper needs right now (equipment, mobility,
    hearing, languages, how to knock). From Week 3 these come out of the
    encrypted Sealed Profile at the moment of unlock.
    """
    language = LANGUAGE_NAMES.get(helper_language, "English")
    client = _get_client()
    if client is not None:
        facts = {
            "resident": resident_name,
            "unit": unit,
            "needs": need_to_know,
            "neighbour_report": report_concern,
            "helper": helper_name,
            "helper_skills": helper_skills or ["none"],
            "stairwell": stairwell,
            "lifts_down": lifts_down,
        }
        # Try the stronger writer first; if it fails (e.g. the account can't use it),
        # try the fast model, which already reads reports, before using the template.
        for model in dict.fromkeys([STRONG_MODEL, FAST_MODEL]):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=MAX_TOKENS,
                    system=WRITE_TASK_SYSTEM_PROMPT,
                    tools=[WRITE_TASK_TOOL],
                    tool_choice={"type": "tool", "name": "write_task"},
                    messages=[{"role": "user", "content": f"Helper's language: {language}\n\nFacts:\n{facts}"}],
                    timeout=AI_WRITE_TIMEOUT_SECONDS,
                )
                for block in response.content:
                    if block.type == "tool_use" and block.name == "write_task":
                        result = dict(block.input)
                        if len(result.get("sms", "")) > 160:
                            result["sms"] = result["sms"][:157] + "..."
                        result["language"] = helper_language
                        result["source"] = "claude"
                        result["model"] = model
                        return result
            except Exception as exc:
                print(f"[ai] write_instruction with {model} failed: {exc}")
    return _fallback_instruction(resident_name, unit, need_to_know, stairwell, lifts_down, report_concern)


def _fallback_instruction(resident_name, unit, need, stairwell, lifts_down, report_concern) -> dict:
    """Plain English template, used only when Claude is unavailable."""
    steps = []
    steps.append(f"Go to {unit}" + (f" by stairwell {stairwell} (lifts are down)." if lifts_down else "."))
    knock = need.get("how_to_knock") or "Knock and call their name."
    steps.append(knock[0].upper() + knock[1:] + ("" if knock.endswith(".") else "."))
    if need.get("powered_equipment"):
        steps.append(f"Check their {need['powered_equipment']} is working. If they are unwell or don't answer, call 995.")
    else:
        steps.append("If they don't answer or are unwell, call 995.")
    bring = ["torch", "phone"] + (["power bank"] if need.get("powered_equipment") else [])
    short_name = resident_name.split()[0] + " " + resident_name.split()[1] if len(resident_name.split()) > 1 else resident_name
    return {
        "headline": f"Check on {short_name}, {unit}, now",
        "steps": steps,
        "bring": bring,
        "sms": f"KG: Check {short_name} {unit} now. Stairwell {stairwell}. Bring torch. Reply 1=reached 2=need help"[:160],
        "language": "en",
        "source": "fallback",
    }


# ---------------------------------------------------------------------------
# review_trust: Claude can spot suspicious wording that rules can't
# ---------------------------------------------------------------------------

REVIEW_TRUST_TOOL = {
    "name": "review_trust",
    "description": "Say whether anything in the message itself makes it LESS trustworthy than the facts suggest.",
    "input_schema": {
        "type": "object",
        "properties": {
            "more_suspicious": {
                "type": "boolean",
                "description": "True only if the wording itself looks fake, copied, manipulative or like a lure.",
            },
            "reason": {
                "type": ["string", "null"],
                "description": "If more_suspicious, a reason of at most 6 words, e.g. 'urgent wording, no details'.",
            },
        },
        "required": ["more_suspicious", "reason"],
    },
}

REVIEW_TRUST_PROMPT = """You help check emergency reports sent by residents of a Singapore HDB block during a blackout
caused by a cyberattack. Attackers may send fake reports to waste helpers' time or lure them somewhere.

You are given the message and facts the system has already checked (who sent it, whether others
confirmed it, whether the unit is occupied). Only judge the WORDING: does it look fake, copied,
manipulative, or like a lure? Real neighbours are often messy, emotional and informal: that alone
is NOT suspicious. Never mark a message suspicious just because it is urgent or in Singlish."""


def review_trust(text: str, facts: dict) -> dict:
    """Return {more_suspicious: bool, reason: str|None, source}. Claude can only LOWER trust,
    never raise it: hard facts (unknown sender, vacant unit) always stand."""
    client = _get_client()
    if client is not None:
        try:
            response = client.messages.create(
                model=FAST_MODEL,
                max_tokens=MAX_TOKENS,
                system=REVIEW_TRUST_PROMPT,
                tools=[REVIEW_TRUST_TOOL],
                tool_choice={"type": "tool", "name": "review_trust"},
                messages=[{"role": "user", "content": f"Facts: {facts}\n\nMessage:\n{text}"}],
            )
            for block in response.content:
                if block.type == "tool_use":
                    return {**dict(block.input), "source": "claude"}
        except Exception as exc:
            print(f"[ai] review_trust failed, skipping the wording check: {exc}")
    return {"more_suspicious": False, "reason": None, "source": "fallback"}


# ---------------------------------------------------------------------------
# find_rumour: the same claim spreading through several messages
# ---------------------------------------------------------------------------

FIND_RUMOUR_TOOL = {
    "name": "report_rumour",
    "description": "Report whether several messages are spreading the same claim about public services or safety.",
    "input_schema": {
        "type": "object",
        "properties": {
            "found": {"type": "boolean"},
            "claim": {
                "type": ["string", "null"],
                "description": "The claim in plain English, under 10 words, e.g. 'tap water is contaminated'.",
            },
            "message_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "The numbers of the messages that repeat the claim.",
            },
        },
        "required": ["found", "claim", "message_numbers"],
    },
}

FIND_RUMOUR_PROMPT = """You watch neighbour messages during a blackout in a Singapore HDB block, to spot RUMOURS:
the same claim about public services or safety (water, power, transport, police, scams, evacuation)
repeated across several messages from different people, often unverified ("my friend say...", "group
chat says..."). Messages may be in Singlish, Malay, Mandarin or Tamil; the same claim in different
languages counts as the same claim.

Only report a rumour if at least 3 messages repeat the same claim. Reports about one specific person
needing help are NOT rumours. You only spot the claim: you never decide whether it is true."""

_RUMOUR_TOPICS = {
    "tap water is contaminated": (
        ["water", "air paip", "air ", "水", "தண்ணீர்"],
        ["contaminat", "poison", "dirty", "unsafe", "tercemar", "beracun", "kotor", "污染", "有毒", "不能喝", "dont drink", "don't drink", "jangan minum"],
    ),
}


def find_rumour(messages: list[str]) -> dict:
    """Return {found, claim, message_numbers (1-based), source}."""
    if len(messages) < 3:
        return {"found": False, "claim": None, "message_numbers": [], "source": "rule"}
    client = _get_client()
    if client is not None:
        try:
            numbered = "\n".join(f"{i}. {m}" for i, m in enumerate(messages, 1))
            response = client.messages.create(
                model=FAST_MODEL,
                max_tokens=MAX_TOKENS,
                system=FIND_RUMOUR_PROMPT,
                tools=[FIND_RUMOUR_TOOL],
                tool_choice={"type": "tool", "name": "report_rumour"},
                messages=[{"role": "user", "content": f"Recent messages:\n{numbered}"}],
            )
            for block in response.content:
                if block.type == "tool_use":
                    result = dict(block.input)
                    result["found"] = bool(result.get("found")) and len(result.get("message_numbers", [])) >= 3
                    return {**result, "source": "claude"}
        except Exception as exc:
            print(f"[ai] find_rumour failed, using fallback: {exc}")
    # Fallback: simple keyword match for the demo's water rumour.
    for claim, (topic_words, claim_words) in _RUMOUR_TOPICS.items():
        hits = [
            i
            for i, m in enumerate(messages, 1)
            if any(t in m.lower() for t in topic_words) and any(c in m.lower() for c in claim_words)
        ]
        if len(hits) >= 3:
            return {"found": True, "claim": claim, "message_numbers": hits, "source": "fallback"}
    return {"found": False, "claim": None, "message_numbers": [], "source": "fallback"}


# ---------------------------------------------------------------------------
# summarise_what_if: the plain-English line for an official
# ---------------------------------------------------------------------------


WRITE_TEXT_TOOL = {
    "name": "write_text",
    "description": "Return the finished text.",
    "input_schema": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "The finished text, exactly as it should be shown."}},
        "required": ["text"],
    },
}


def _text_call(system: str, user: str, max_tokens: int = MAX_TOKENS) -> str | None:
    """A text answer from Claude (strong model, falling back to the fast one).

    Uses the same structured "tool" answer as every other call in this file,
    which is the most reliable way to get exactly one clean piece of text back.
    """
    client = _get_client()
    if client is None:
        print("[ai] text call skipped: no ANTHROPIC_API_KEY found")
        return None
    for model in dict.fromkeys([STRONG_MODEL, FAST_MODEL]):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=[WRITE_TEXT_TOOL],
                tool_choice={"type": "tool", "name": "write_text"},
                messages=[{"role": "user", "content": user}],
                timeout=AI_WRITE_TIMEOUT_SECONDS,
            )
            if response.stop_reason == "max_tokens":
                print(f"[ai] text call with {model} was cut off (ran out of room); not using it")
                continue
            for block in response.content:
                if block.type == "tool_use" and block.input.get("text", "").strip():
                    return block.input["text"].strip()
            print(f"[ai] text call with {model} returned no text (stop reason: {response.stop_reason})")
        except Exception as exc:
            print(f"[ai] text call with {model} failed: {exc}")
    return None


def summarise_what_if(block_name: str, evening: dict, night: dict, gap: str | None, options: list[dict]) -> dict:
    """Two sentences an official can act on. Only uses the numbers given."""
    # Plain names only, so the words "median" and "p90" never reach the planner.
    def plain(t: dict) -> dict:
        return {"typical_night_minutes": t.get("median"), "bad_night_minutes": t.get("p90")}

    facts = {
        "block": block_name,
        "at_7pm": plain(evening),
        "at_3am": plain(night),
        "gap": gap,
        "best_options": [{"change": o["label"], "minutes_before": o["before"], "minutes_after": o["after"]} for o in options],
    }
    text = _text_call(
        "You write for a town council planner in Singapore. In at most two short sentences, say where this "
        "block is weakest and which option helps most, with the minutes. Use ONLY the numbers given. "
        "Say 'on a typical night' and 'on a bad night'. Never use statistics words such as median, p90, "
        "percentile or average. Write times as 3am and 7pm, never 03:00 or 19:00. No preamble.",
        str(facts),
        max_tokens=MAX_TOKENS,
    )
    if text:
        text = re.sub(r"\bp90\b", "bad-night", text, flags=re.I)
        text = re.sub(r"\bmedian\b", "typical", text, flags=re.I)
        text = text.replace("03:00", "3am").replace("19:00", "7pm")
    if text:
        return {"text": text, "source": "claude"}
    if options:
        best = options[0]
        lead = gap.rstrip(".") + ". " if gap else ""
        return {
            "text": f"{lead}{best['label']} would cut the {night['time'] if 'time' in night else '3am'} time from "
            f"{best['before']} to {best['after']} minutes.",
            "source": "fallback",
        }
    return {"text": "No single change makes a big difference to this block.", "source": "fallback"}


# ---------------------------------------------------------------------------
# write_handover_brief: one page for SCDF when they arrive
# ---------------------------------------------------------------------------

BRIEF_PROMPT = """You write the handover brief that SCDF officers read on arrival at a Singapore HDB block
during a blackout. They have seconds, so put the most urgent facts first.

Format, exactly (plain text, no markdown symbols except the line breaks):
Line 1: block and time, e.g. "Block 123 · 9:24pm"
Line 2: counts, e.g. "6 vulnerable residents · 5 reached by neighbours · 1 NOT reached"
Then "NOT REACHED:" and one line per person not reached (unit, need, what's been tried).
Then "STILL NEEDS ATTENTION:" and one short line per person in reached_needing_attention (they have been
reached but still need action, e.g. oxygen on a battery). Leave this section out if the list is empty.
Do not list anyone else who was reached; the counts line already covers them.
Then "ALSO:" for fake reports rejected or rumours answered, ONLY if there were any.
If there were none, leave out the ALSO line completely. Never write "No fake reports" or "No rumours".
At most about 120 words. Use ONLY the facts given; never invent hazards or medical details."""


def _drop_empty_also(text: str) -> str:
    """Remove an ALSO line that only says nothing happened ("No fake reports rejected...")."""
    keep = []
    for line in text.splitlines():
        body = line.strip()
        if body.upper().startswith("ALSO"):
            rest = body.split(":", 1)[-1].strip().lower()
            parts = [x.strip() for x in re.split(r"[.;]", rest) if x.strip()]
            if not parts or all(x.startswith(("no ", "none", "nil", "0 ")) for x in parts):
                continue
        keep.append(line)
    return "\n".join(keep).strip()


def write_handover_brief(facts: dict) -> dict:
    text = _text_call(BRIEF_PROMPT, str(facts))
    if text:
        text = _drop_empty_also(text)
    if text:
        return {"text": text, "source": "claude"}
    lines = [f"{facts['block']} · {facts['time']}", f"{facts['vulnerable']} vulnerable residents · {facts['reached_count']} reached by neighbours · {len(facts['not_reached'])} NOT reached"]
    if facts["not_reached"]:
        lines.append("NOT REACHED:")
        lines += [f"{p['unit']} {p['name']}" + (f": {p['need']}" if p["need"] else "") + f" ({p['status']})" for p in facts["not_reached"]]
    if facts.get("reached_needing_attention"):
        lines.append("STILL NEEDS ATTENTION:")
        lines += [f"{p['unit']} {p['name']}: {p['need']}, neighbour {p['helper']} with them" for p in facts["reached_needing_attention"]]
    extras = []
    if facts.get("fake_reports_rejected"):
        extras.append(f"{facts['fake_reports_rejected']} fake report(s) rejected")
    if facts.get("rumours_answered"):
        extras.append(f"rumour answered: {', '.join(facts['rumours_answered'])}")
    if extras:
        lines.append("ALSO: " + "; ".join(extras))
    return {"text": "\n".join(lines), "source": "fallback"}
