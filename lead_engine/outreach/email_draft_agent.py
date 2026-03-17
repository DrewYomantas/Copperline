from __future__ import annotations

import hashlib
import random
import re
from typing import Dict, List, Tuple

DRAFT_VERSION = "v8"

# ---------------------------------------------------------------------------
# Industry detection (kept compatible with the existing pipeline)
# ---------------------------------------------------------------------------

INDUSTRY_SIGNALS: List[Tuple[str, List[str]]] = [
    ("plumbing",     ["plumb", "sewer", "drain", "pipe", "rooter", "septic"]),
    ("hvac",         ["hvac", "heating", "cooling", "air condition", "furnace", "refrigerat"]),
    ("electrical",   ["electric", "wiring", "electrician", "panel", "generator"]),
    ("locksmith",    ["locksmith", "lock", "key", "lockout", "rekey"]),
    ("garage_door",  ["garage door", "garage", "overhead door"]),
    ("towing",       ["tow", "towing", "roadside", "wrecker", "recovery"]),
    ("roofing",      ["roof", "gutter", "siding", "shingle"]),
    ("pest_control", ["pest", "exterminator", "termite", "rodent", "bug"]),
    ("auto",         ["auto", "mechanic", "car repair", "tire", "collision", "body shop"]),
    ("construction", ["construction", "contractor", "remodel", "renovation", "carpent", "mason"]),
    ("dental",       ["dental", "dentist", "orthodont", "oral"]),
    ("medical",      ["medical", "clinic", "doctor", "physician", "urgent care", "chiro"]),
    ("legal",        ["law", "attorney", "lawyer", "legal", "firm"]),
    ("real_estate",  ["real estate", "realty", "realtor", "property management"]),
    ("restaurant",   ["restaurant", "diner", "cafe", "catering", "bistro", "eatery", "pizza", "grill"]),
    ("cleaning",     ["cleaning", "janitorial", "maid", "housekeeping", "pressure wash"]),
    ("insurance",    ["insurance", "insur", "agency", "broker"]),
    ("accounting",   ["account", "bookkeep", "tax", "cpa", "payroll"]),
    ("salon",        ["salon", "barber", "hair", "nail", "spa", "beauty"]),
    ("gym",          ["gym", "fitness", "personal train", "yoga", "pilates"]),
    ("moving",       ["moving", "mover", "storage", "relocation"]),
    ("landscaping",  ["landscap", "lawn", "garden", "tree", "mow", "sod"]),
]


def detect_industry(business_name: str, provided_industry: str = "") -> str:
    if provided_industry and provided_industry.strip().lower() not in ("", "unknown", "n/a"):
        return provided_industry.strip().lower()
    name_lower = (business_name or "").lower()
    for industry, signals in INDUSTRY_SIGNALS:
        if any(sig in name_lower for sig in signals):
            return industry
    return "general"


_TEMPLATES: Dict[str, List[Tuple[str, str]]] = {
    "missed_after_hours": [("missed calls", "{opening}")],
    "unknown":            [("missed calls", "{opening}")],
}

_HIGH_FIT_INDUSTRIES = {
    "plumbing", "hvac", "electrical", "locksmith", "garage_door", "towing",
}

_BANNED = [
    "optimize", "revolutionize", "leverage", "synergy", "streamline",
    "game-changer", "game changer", "cutting-edge", "cutting edge",
    "robust", "scalable", "seamlessly", "seamless",
    "ai-powered", "ai powered", "system integration", "platform",
    "solution", "lead capture",
]

_FORMAL_OPENER_SUBS = [
    ("I noticed that ", ""),
    ("I wanted to reach out ", ""),
    ("I wanted to reach out", ""),
    ("I help businesses ", "I help service businesses "),
    ("I help businesses", "I help service businesses"),
    ("We offer ", ""),
    ("We offer", ""),
    ("AI-powered", "simple"),
    ("ai-powered", "simple"),
    ("streamline", "speed up"),
    ("optimize", "improve"),
    ("solution", "fix"),
    ("platform", "system"),
    ("random but, ", ""),
    ("random but ", ""),
    ("not sure if this happens to you but ", ""),
    ("was thinking about this earlier, ", ""),
    ("kinda ", ""),
    ("probably ", ""),
    ("guessing ", ""),
]

_WORD_TARGET_MAX = 42
_WORD_LIMIT = 70
_SIGN_OFF = "\n\n- Drew"
_SUBJECT_OPTIONS = [
    "quick question",
    "missed calls",
    "after-hours follow-up",
]
_OPENERS = [
    "quick question",
    "curious",
    "wanted to ask",
    "checking",
]
_SECOND_SENTENCES = [
    "If that happens more than it should, I can send a quick example.",
    "If that's a real issue, happy to send a short example.",
    "If that sounds familiar, I can send over a quick example.",
    "If that's costing you jobs, I can send a quick example of the fix.",
]
_ANGLE_CLAUSE = {
    "missed_calls":   "when you're {context}, do missed calls ever turn into lost jobs",
    "response_delay": "when someone reaches out, does follow-up ever lag while you're {context}",
    "lead_loss":      "do leads ever go cold before anyone can get back to them when you're {context}",
}


def _industry_phrase(industry: str) -> str:
    return {
        "hvac": "out on jobs",
        "plumbing": "out in the field",
        "garage_door": "on installs",
        "auto": "in the shop",
        "electrical": "out on jobs",
        "locksmith": "out on calls",
        "towing": "out on a run",
        "roofing": "on a job site",
    }.get(industry, "busy during the day")


def _variant(business_name: str, n: int = 3) -> int:
    digest = hashlib.sha256(business_name.strip().lower().encode()).hexdigest()
    return int(digest[:8], 16) % n


def _word_count(text: str) -> int:
    return len(text.split())


def _check_banned(text: str) -> None:
    text_lower = text.lower()
    hits = [word for word in _BANNED if word in text_lower]
    if hits:
        raise ValueError(f"Banned word(s) in generated email: {hits}")


def _pick_subject(business_name: str) -> str:
    if business_name and len(business_name) <= 24 and random.random() < 0.2:
        return business_name
    return random.choice(_SUBJECT_OPTIONS)


def enforce_human_style(body_text: str) -> str:
    if not body_text:
        return body_text

    for pattern, replacement in _FORMAL_OPENER_SUBS:
        if pattern in body_text:
            body_text = body_text.replace(pattern, replacement)

    body_text = body_text.replace("\n\n", " ").replace("\n", " ")
    body_text = re.sub(r"\s+", " ", body_text).strip()
    body_text = re.sub(r"\s+([,.?!])", r"\1", body_text)
    body_text = re.sub(r"([?!.,]){2,}", r"\1", body_text)
    body_text = re.sub(r"(?i)^hey\s+", "hey ", body_text)

    parts = re.split(r"(?<=[.?!])\s+", body_text)
    cleaned_parts = [part.strip() for part in parts if part.strip()]
    if len(cleaned_parts) > 2:
        cleaned_parts = cleaned_parts[:2]
    body_text = " ".join(cleaned_parts)

    words = body_text.split()
    if len(words) > _WORD_TARGET_MAX:
        trimmed = " ".join(words[:_WORD_TARGET_MAX]).rstrip(",;:-")
        last_punct = max(trimmed.rfind("."), trimmed.rfind("?"), trimmed.rfind("!"))
        body_text = trimmed[: last_punct + 1] if last_punct > 0 else trimmed

    body_text = body_text.rstrip(" ,;-")
    if body_text and body_text[-1] not in ".?!":
        body_text += "."
    return body_text


def draft_email(prospect: Dict[str, str], final_priority_score: int) -> Tuple[str, str]:
    """
    Generate a short human outreach email.

    Routing scaffold is kept intact for pipeline compatibility, but copy is
    guarded to stay concise, natural, and less awkward.
    """
    business_name = (prospect.get("business_name") or "").strip()
    city = (prospect.get("city") or "").strip()

    if not business_name:
        raise ValueError("Cannot draft email without business_name.")
    if not city:
        raise ValueError(f"Cannot draft email for {business_name} without city.")

    industry = detect_industry(business_name, prospect.get("industry", ""))
    if industry in _HIGH_FIT_INDUSTRIES:
        opportunity = "missed_after_hours"
    else:
        opportunity = (prospect.get("automation_opportunity") or "unknown").strip().lower()
        if opportunity not in _TEMPLATES:
            opportunity = "unknown"

    opener = random.choice(_OPENERS)
    second = random.choice(_SECOND_SENTENCES)
    angle = random.choice(list(_ANGLE_CLAUSE.keys()))
    first = _ANGLE_CLAUSE[angle].replace("{context}", _industry_phrase(industry))
    if opportunity == "unknown":
        first = first.replace("missed calls", "calls or follow-up gaps")

    subject = _pick_subject(business_name)
    body_text = f"hey {business_name} - {opener}, {first}? {second}"

    if _word_count(body_text) > _WORD_LIMIT:
        words = body_text.split()
        body_text = " ".join(words[:_WORD_LIMIT]).rstrip(",;") + "."

    body_text = enforce_human_style(body_text)
    body = body_text + _SIGN_OFF
    _check_banned(body)
    return subject, body


def draft_email_json(prospect: Dict[str, str], final_priority_score: int) -> Dict:
    subject, body = draft_email(prospect, final_priority_score)
    return {
        "subject": subject,
        "email_body": body,
        "tone": "casual",
    }


def pick_best_pitch_angle(likely_opportunity: str) -> str:
    return (likely_opportunity or "booking automation").strip() or "booking automation"


def draft_social_messages(prospect: Dict[str, str], email_body: str) -> Tuple[str, str, str]:
    """Return short companion drafts for social/contact-form use."""
    business_name = (prospect.get("business_name") or "there").strip()
    base = re.sub(r"\n\n[-–—]\s*Drew\s*$", "", (email_body or "").strip(), flags=re.IGNORECASE)
    if not base:
        base = (
            f"hey {business_name} - quick question, "
            "do missed calls or slow follow-up ever turn into lost jobs? "
            "Happy to send a quick example if useful."
        )
    base = enforce_human_style(base)
    return base, base, base
