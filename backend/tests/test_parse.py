"""Score parse_report against the messy-message test set.

Run from the backend/ folder:
    python -m tests.test_parse

With ANTHROPIC_API_KEY set in .env this tests Claude. Without it, it tests the
rule-based fallback (which is expected to score much lower: that's the point).
Re-run after every prompt change. Goal: at least 18/20 once the set has 20 messages.
"""

import json
from pathlib import Path

from app.ai import parse_report
from app.db import get_session
from app.models import Resident, Unit
from sqlmodel import select

MESSAGES = json.loads((Path(__file__).parent / "messages.json").read_text(encoding="utf-8"))


def check(case: dict, result: dict) -> list[str]:
    problems = []
    if result.get("unit") != case.get("expect_unit"):
        problems.append(f"unit {result.get('unit')!r}, expected {case.get('expect_unit')!r}")
    urgency = result.get("urgency", 0)
    if "min_urgency" in case and urgency < case["min_urgency"]:
        problems.append(f"urgency {urgency} < {case['min_urgency']}")
    if "max_urgency" in case and urgency > case["max_urgency"]:
        problems.append(f"urgency {urgency} > {case['max_urgency']}")
    return problems


def load_block(block_id: int = 123):
    with get_session() as s:
        units = [u.label for u in s.exec(select(Unit).where(Unit.block_id == block_id)).all()]
        residents = [(r.name, r.unit) for r in s.exec(select(Resident).where(Resident.block_id == block_id)).all()]
    return units, residents


def main() -> int:
    units, residents = load_block()
    if not units:
        print("No units found. Run `python -m seed.seed` first.")
        return 1

    passed, source = 0, None
    for i, case in enumerate(MESSAGES, 1):
        result = parse_report(case["text"], units, residents)
        source = result.get("source")
        problems = check(case, result)
        mark = "PASS" if not problems else "FAIL"
        passed += not problems
        print(f"{mark} {i:2d}. {case['text'][:60]}")
        if problems:
            print("        " + "; ".join(problems))
            print(f"        got: {result}")

    print(f"\n{passed}/{len(MESSAGES)} correct (parser: {source})")
    return 0


def test_demo_message_finds_mdm_tan():
    """pytest: the demo message must always find #09-12, even with the fallback."""
    units, residents = load_block()
    result = parse_report(MESSAGES[0]["text"], units, residents)
    assert result["unit"] == "#09-12"
    assert result["urgency"] >= 4


if __name__ == "__main__":
    raise SystemExit(main())


def test_fallback_matches_titled_name():
    """pytest: 'Mdm Wong' with no unit is matched through the residents list."""
    units, residents = load_block()
    from app.ai import _fallback_parse

    assert _fallback_parse("Mdm Wong never answer phone", units, residents)["unit"] == "#12-02"
