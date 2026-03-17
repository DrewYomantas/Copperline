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
    # Variant A — missed call / lead loss angle
    "quick one — when someone calls and no one picks up, does that lead just go cold, or do you guys have a way to follow up?",
    # Variant B — after-hours / gap angle
    "random question — do leads ever fall through after hours or when everyone's tied up on a job?",
    # Variant C — general operational gap angle
    "hey — do you find you lose work from calls or follow-ups that just don't happen fast enough?",
]

# Fixed body, shared by all variants
_BODY_FIXED = (
    "I help service businesses capture the work that slips through — "
    "calls that don't get answered, estimates that go cold, follow-ups that never happen.\n\n"
    "happy to take a quick look at how things run and point out where the easy fixes are.\n\n"
    "worth a few minutes if any of that's a real problem for you."
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
DRAFT_VERSION = "v7"

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
    "ai-powered", "ai powered",
    "system integration", "platform", "solution", "lead capture",
]

# Phrase substitutions applied by enforce_human_style.
# Each entry is (exact_match_string, replacement).
# Empty replacement means strip the phrase.
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
]

_WORD_TARGET_MAX = 50  # target word ceiling for final body (sign-off excluded)

# ── Industry-aware context phrase ─────────────────────────────────────────────

def _industry_phrase(industry: str) -> str:
    """Return a short situational phrase relevant to the industry."""
    return {
        "hvac":        "when you're out on jobs",
        "plumbing":    "when you're out in the field",
        "garage_door": "when you're on installs",
        "auto":        "when the shop gets busy",
        "electrical":  "when you're out on jobs",
        "locksmith":   "when you're out on calls",
        "towing":      "when you're out on a run",
        "roofing":     "when you're on a job site",
    }.get(industry, "when you're busy during the day")


# ── Opener and second-sentence variation pools ────────────────────────────────

OPENERS = [
    "quick question",
    "random but",
    "not sure if this happens to you but",
    "was thinking about this earlier",
]

_SECOND_SENTENCES = [
    "feels like those usually just go to the next company",
    "guessing most people don't try again",
    "seems like those turn into lost jobs pretty quick",
]


def enforce_human_style(body_text: str) -> str:
    """
    Post-processing layer applied to body_text (sign-off excluded) after
    draft generation.

    What it does:
      1. Strips/replaces residual formal or banned phrases.
      2. Lowercases the opener on lines starting with "Hey" (not "Hi" —
         "Hi" is intentional and reads fine capitalised).
      3. Trims to _WORD_TARGET_MAX words if exceeded by dropping the last
         paragraph block. Never trims mid-sentence.

    What it does NOT do:
      - Does not sentence-split across paragraph breaks (\\n\\n). The
        existing template uses deliberate multi-paragraph structure; naive
        sentence-splitting corrupts it.
      - Does not hard-cap to exactly 2 sentences when the output already
        reads naturally across 3-4 short sentences in 3 paragraphs.
        The paragraph structure already achieves the human-style target.

    Safe to call on any string. Returns input unchanged if nothing applies.
    """
    if not body_text:
        return body_text

    # 1. Strip/replace formal and banned phrases
    for pattern, replacement in _FORMAL_OPENER_SUBS:
        if pattern in body_text:
            body_text = body_text.replace(pattern, replacement)

    # 2. Lowercase opener — only lines starting with "Hey "
    lines = body_text.split("\n")
    if lines and lines[0].startswith("Hey "):
        lines[0] = lines[0][0].lower() + lines[0][1:]
        body_text = "\n".join(lines)

    # 3. Collapse all paragraph breaks into single spaces (Step 1A).
    #    Produces one continuous block — the final required format.
    body_text = body_text.replace("\n\n", " ").replace("\n", " ")

    # 4. Sentence clamp — keep max 2 sentences (Step 1B).
    #    Split on sentence-ending punctuation, preserve the delimiter.
    import re as _re
    parts = _re.split(r'(?<=[.?!])\s+', body_text.strip())
    if len(parts) > 2:
        body_text = " ".join(parts[:2])
        # Ensure final punctuation
        if body_text and body_text[-1] not in ".?!":
            body_text += "."

    # 5. Word trim — enforce hard ~50-word ceiling (Step 1C).
    words = body_text.split()
    if len(words) > _WORD_TARGET_MAX:
        # Walk back to the last sentence boundary within the limit
        trimmed = " ".join(words[:_WORD_TARGET_MAX])
        # Find last punctuation and cut there cleanly
        last_punct = max(trimmed.rfind("."), trimmed.rfind("?"), trimmed.rfind("!"))
        body_text = trimmed[:last_punct + 1] if last_punct > 0 else trimmed

    return body_text

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

    # Step 6 — Subject selection from updated pool
    subject = random.choice([
        "quick question",
        "random thought",
        business_name,
        "hey",
    ])

    # Steps 4+5 — Build 2-sentence body using industry-aware opener
    opener       = random.choice(OPENERS)
    ind_phrase   = _industry_phrase(industry)
    second       = random.choice(_SECOND_SENTENCES)
    sentence_one = f"hey {business_name} — {opener}, {ind_phrase} do calls just get missed sometimes"
    sentence_two = second
    body_text    = f"{sentence_one}. {sentence_two}."

    # Legacy word-count guard (kept for safety; enforce_human_style trims harder below)
    wc = _word_count(body_text)
    if wc > _WORD_LIMIT:
        words = body_text.split()
        body_text = " ".join(words[:_WORD_LIMIT]).rstrip(",;") + "."

    # Enforce human style BEFORE appending sign-off
    body_text = enforce_human_style(body_text)

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
