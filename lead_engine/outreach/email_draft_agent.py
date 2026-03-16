from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Optional, Tuple

DRAFT_VERSION = "v2_signal_templates"

# ---------------------------------------------------------------------------
# Industry detection (unchanged — used by pipeline)
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
    # Below are kept for detection only — low fit for this product
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


# ---------------------------------------------------------------------------
# Email templates — After-Hours Lead Capture (Missed Call Text-Back)
#
# Structure:
#   - Subject randomly selected from _SUBJECTS (3–4 words, no marketing language)
#   - Greeting: Hi {name},
#   - Opening question rotates across 3 variants (random selection)
#   - Body lines 2–3 are fixed across all variants
#   - Sign-off: – Drew  (full signature appended by email_sender_agent)
#
# All three variants share identical body lines after the opening question.
# Only the first line changes. This makes the email feel personal without
# requiring city or industry interpolation.
#
# Word count target: ≤ 70 words in body text (sign-off excluded).
# Banned words enforced below in _check_banned.
# ---------------------------------------------------------------------------

# Opening question variants — only line 1 rotates
_OPENING_QUESTIONS = [
    # Variant A
    "Do you guys ever miss calls when the crew is out on jobs?",
    # Variant B
    "Do you ever miss calls when everyone's out working jobs?",
    # Variant C
    "Quick question — what happens when someone calls after hours and nobody answers?",
]

# Fixed body, shared by all variants
_BODY_FIXED = (
    "A lot of service companies lose those leads because the customer "
    "just calls the next number if nobody answers.\n\n"
    "I set up a simple text-back line that replies to missed callers automatically "
    "so you can follow up instead of losing the job.\n\n"
    "Happy to send a quick example if you're curious."
)

# Subject line pool — short, natural, no marketing language
_SUBJECTS = [
    "missed calls?",
    "quick question",
    "after-hours calls",
    None,   # sentinel → generates "quick question for {business_name}" at draft time
]

# Increment this string whenever the template copy changes.
# Stored in pending_emails.csv so stale rows can be identified.
DRAFT_VERSION = "v4"

_TEMPLATES: Dict[str, List[Tuple[str, str]]] = {
    # Kept for routing compatibility — all keys now produce the same structure.
    # The opening question is randomised at draft time regardless of key.
    "missed_after_hours": [("missed calls", "{opening}\n\n{body}")],
    "unknown":            [("missed calls", "{opening}\n\n{body}")],
}


# ---------------------------------------------------------------------------
# Core draft function
# ---------------------------------------------------------------------------

_BANNED = [
    "optimize", "revolutionize", "leverage", "synergy", "streamline",
    "game-changer", "game changer", "cutting-edge", "cutting edge",
    "robust", "scalable", "seamlessly", "seamless",
    "automation", "automate", "workflow", "ai-powered", "ai powered",
    "system integration", "platform", "solution", "lead capture",
]

# High-fit industries always get the missed_after_hours template
_HIGH_FIT_INDUSTRIES = {
    "plumbing", "hvac", "electrical", "locksmith",
    "garage_door", "towing",
}

_WORD_LIMIT = 70


def _variant(business_name: str, n: int = 3) -> int:
    """Deterministic variant index — kept for internal use and testing."""
    digest = hashlib.sha256(business_name.strip().lower().encode()).hexdigest()
    return int(digest[:8], 16) % n


_SIGN_OFF = "\n\n– Drew"


def _fill(template: str, name: str, city: str, industry: str) -> str:
    industry_display = industry.replace("_", " ")
    return (
        template
        .replace("{name}", name)
        .replace("{city}", city)
        .replace("{industry}", industry_display)
    )


def _word_count(text: str) -> int:
    return len(text.split())


def _check_banned(text: str) -> None:
    text_lower = text.lower()
    hits = [w for w in _BANNED if w in text_lower]
    if hits:
        raise ValueError(f"Banned word(s) in generated email: {hits}")


def draft_email(prospect: Dict[str, str], final_priority_score: int) -> Tuple[str, str]:
    """
    Generate a product-focused cold email for After-Hours Lead Capture.

    Routing:
    - High-fit industries (plumbing, hvac, electrical, locksmith, garage_door,
      towing) → always use "missed_after_hours" template.
    - All others → use automation_opportunity field, fall back to "unknown".

    Returns (subject, body) — pipeline-compatible.
    """
    business_name = (prospect.get("business_name") or "").strip()
    city          = (prospect.get("city") or "").strip()

    if not business_name:
        raise ValueError("Cannot draft email without business_name.")
    if not city:
        raise ValueError(f"Cannot draft email for {business_name} without city.")

    industry = detect_industry(business_name, prospect.get("industry", ""))

    # High-fit trades always get the missed_after_hours pitch
    if industry in _HIGH_FIT_INDUSTRIES:
        opportunity = "missed_after_hours"
    else:
        opportunity = (prospect.get("automation_opportunity") or "unknown").strip().lower()
        if opportunity not in _TEMPLATES:
            opportunity = "unknown"

    variants = _TEMPLATES[opportunity]
    # Pick subject — None sentinel produces the personalised variant
    _chosen = random.choice(_SUBJECTS)
    subject = f"quick question for {business_name}" if _chosen is None else _chosen
    opening = random.choice(_OPENING_QUESTIONS)
    body_text = f"Hi {business_name},\n\n{opening}\n\n{_BODY_FIXED}"

    # Guard: word count (sign-off excluded from limit)
    wc = _word_count(body_text)
    if wc > _WORD_LIMIT:
        sentences = body_text.replace("?", ".").split(".")
        trimmed = []
        running = 0
        for s in sentences:
            words = len(s.split())
            if running + words > _WORD_LIMIT:
                break
            trimmed.append(s)
            running += words
        body_text = ". ".join(trimmed).strip() + "."

    body = body_text + _SIGN_OFF

    # Guard: banned words
    _check_banned(body)

    return subject, body


def draft_email_json(prospect: Dict[str, str], final_priority_score: int) -> Dict:
    """
    Same as draft_email but returns the full JSON payload.

    {
        "subject": "...",
        "email_body": "...",
        "tone": "casual"
    }
    """
    subject, body = draft_email(prospect, final_priority_score)
    return {
        "subject": subject,
        "email_body": body,
        "tone": "casual",
    }


# ── Legacy helpers ────────────────────────────────────────────────────────────

def pick_best_pitch_angle(likely_opportunity: str) -> str:
    """Kept for backward compatibility."""
    return (likely_opportunity or "booking automation").strip() or "booking automation"



def draft_social_messages(prospect: Dict[str, str], email_body: str) -> Tuple[str, str, str]:
    """Return basic social/contact-form drafts derived from the email body."""
    business_name = (prospect.get("business_name") or "there").strip()
    base = (email_body or "").replace("\n\nBest,\nDrew", "").strip()
    if not base:
        base = (
            f"Hi {business_name} — quick note. "
            "I can help with missed-call follow-up and lead capture. "
            "Open to a quick chat?"
        )

    fb = base
    ig = base
    form = base
    return fb, ig, form
