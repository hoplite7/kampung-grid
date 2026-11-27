"""Risk scoring: who most urgently needs a knock on the door. (Person 4 owns this.)

Kept as a simple, readable points table on purpose: judges trust a formula
they can read on a slide more than a mystery number. The AI's job is turning
messy reports into inputs for this formula and explaining the result, not
replacing it.

Every factor that counts is returned with a short plain-English label, so the
dashboard can show WHY someone is ranked where they are, e.g.
    "lives alone · oxygen concentrator · lifts down · level 9"
"""

from dataclasses import dataclass, field


@dataclass
class Conditions:
    """What is happening right now."""

    power_out: bool = False
    lifts_down: bool = False
    # Open reports about this resident: list of {"urgency": int, "concern": str}
    reports: list = field(default_factory=list)
    already_reached: bool = False


# The points table. Discuss and tune these as a team; keep them on a slide.
POINTS = {
    "powered_equipment": 40,  # needs electricity for medical equipment, and the power is out
    "lives_alone": 20,
    "mobility": 15,  # wheelchair or walker, and the lifts are down
    "high_floor": 10,  # floor 8 or higher, and the lifts are down
    "hearing": 10,  # may not hear alarms or knocking
    "report_per_urgency": 5,  # × the report's urgency (1-5)
}
HIGH_FLOOR = 8


def floor_of(unit: str) -> int:
    """'#09-12' -> 9"""
    return int(unit.lstrip("#").split("-")[0])


def risk_score(vulnerable: dict | None, unit: str, c: Conditions) -> tuple[int, list[str]]:
    """Return (score, reasons). Higher score = check on them sooner."""
    if not vulnerable or c.already_reached:
        return 0, []

    score, reasons = 0, []
    floor = floor_of(unit)

    if vulnerable.get("lives_alone"):
        score += POINTS["lives_alone"]
        reasons.append("lives alone")

    equipment = vulnerable.get("powered_equipment")
    if equipment and c.power_out:
        score += POINTS["powered_equipment"]
        hours = vulnerable.get("equipment_battery_hours")
        reasons.append(f"{equipment}" + (f" (~{hours}h battery)" if hours else ""))

    mobility = vulnerable.get("mobility")
    if mobility and c.lifts_down:
        score += POINTS["mobility"]
        reasons.append(f"uses a {mobility}")

    if vulnerable.get("hearing"):
        score += POINTS["hearing"]
        reasons.append(vulnerable["hearing"])

    if c.lifts_down and floor >= HIGH_FLOOR:
        score += POINTS["high_floor"]
        reasons.append("lifts down")

    for r in c.reports:
        score += POINTS["report_per_urgency"] * int(r.get("urgency", 0))
        if r.get("concern"):
            reasons.append(f"neighbour report: {r['concern']}")

    reasons.append(f"level {floor}")
    return score, reasons
