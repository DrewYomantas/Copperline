from __future__ import annotations

import hashlib
from typing import Dict, Tuple

PITCH_ANGLES = [
    "booking automation",
    "after-hours lead capture",
    "quote follow-up",
    "maintenance reminder automation",
]

ANGLE_KEYWORDS = {
    "booking automation": ["book", "booking", "schedule", "appointment", "calendar"],
    "after-hours lead capture": ["after-hours", "after hours", "missed call", "night", "weekend"],
    "quote follow-up": ["quote", "estimate", "proposal", "follow-up", "follow up"],
    "maintenance reminder automation": ["maintenance", "tune-up", "tune up", "seasonal", "reminder"],
}


def pick_best_pitch_angle(likely_opportunity: str) -> str:
    """Pick the best pitch angle from likely_opportunity text."""
    text = (likely_opportunity or "").strip().lower()
    if not text:
        return "booking automation"

    for angle in PITCH_ANGLES:
        if any(keyword in text for keyword in ANGLE_KEYWORDS[angle]):
            return angle

    return "booking automation"


def _variant_index(business_name: str) -> int:
    digest = hashlib.sha256(business_name.strip().lower().encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 3


def draft_email(prospect: Dict[str, str], final_priority_score: int) -> Tuple[str, str]:
    """Generate deterministic, short outreach subject/body for local service businesses."""
    business_name = (prospect.get("business_name") or "").strip()
    city = (prospect.get("city") or "").strip()

    if not business_name:
        raise ValueError("Cannot draft email without business_name.")
    if not city:
        raise ValueError(f"Cannot draft email for {business_name} without city.")

    pitch_angle = pick_best_pitch_angle(prospect.get("likely_opportunity", ""))
    variant = _variant_index(business_name)

    subjects = [
        f"Quick idea for {business_name} in {city}",
        f"A simple {pitch_angle} idea for {business_name}",
        f"Local suggestion for {business_name}",
    ]

    bodies = [
        (
            f"Hi {business_name} team,\n\n"
            f"I work with local service businesses in {city}. I noticed you may have room to improve {pitch_angle}. "
            "I focus on practical automations that help owners respond faster and keep follow-up organized. "
            "If useful, I can send a quick example for your team.\n\n"
            "Best,\n"
            "Drew"
        ),
        (
            f"Hi {business_name} team,\n\n"
            f"I help HVAC companies around {city} tighten up day-to-day workflows. Based on what I saw, "
            f"{pitch_angle} could be a strong next step for your team. "
            "No big rebuild, just a focused improvement that supports staff and response times. "
            "Want a quick idea to review?\n\n"
            "Best,\n"
            "Drew"
        ),
        (
            f"Hi {business_name} team,\n\n"
            f"I run a local automation service and wanted to share one respectful suggestion: {pitch_angle}. "
            f"For businesses in {city}, this often helps reduce missed opportunities without adding admin work. "
            "If you want, I can send a quick example and you can decide if it is relevant.\n\n"
            "Best,\n"
            "Drew"
        ),
    ]

    return subjects[variant], bodies[variant]
