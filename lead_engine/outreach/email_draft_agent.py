from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

DRAFT_VERSION = "v9"

# ---------------------------------------------------------------------------
# Industry detection (pipeline-compatible, unchanged)
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


# ---------------------------------------------------------------------------
# Banned language — applies to all first-touch drafts
# ---------------------------------------------------------------------------

_BANNED_WORDS = [
    "optimize", "revolutionize", "leverage", "synergy", "streamline",
    "game-changer", "game changer", "cutting-edge", "cutting edge",
    "robust", "scalable", "seamlessly", "seamless",
    "ai-powered", "ai powered", "system integration", "platform",
    "solution", "lead capture", "lead gen", "automation", "automate",
    "book more", "book appointments", "booked appointments",
    "never miss a lead", "fill your calendar", "autopilot",
    "capture leads", "follow-up system", "follow up system",
    "business growth", "grow your business", "scale your",
    "schedule a call", "book a call", "let's hop on", "hop on a call",
    "free audit", "free consultation",
]

# Opener patterns to strip/rewrite during post-processing
_FORMAL_OPENER_SUBS = [
    ("I noticed that ", ""),
    ("I wanted to reach out ", ""),
    ("I wanted to reach out", ""),
    ("my name is", ""),
    ("We are a leading", ""),
    ("we are a leading", ""),
    ("we help businesses like yours", ""),
    ("We help businesses like yours", ""),
    ("I help businesses ", ""),
    ("We offer ", ""),
    ("We offer", ""),
    ("AI-powered", "simple"),
    ("ai-powered", "simple"),
    ("streamline", "speed up"),
    ("optimize", "improve"),
    ("solution", "fix"),
    ("platform", "system"),
]

# ---------------------------------------------------------------------------
# Genericity detection — swappability test
# ---------------------------------------------------------------------------

# Phrases so generic they could go to any business in the same category.
# If the body contains one of these as the *only* business-specific signal,
# the draft fails the genericity check.
_GENERIC_OBSERVATION_PHRASES = [
    "noticed you do ",
    "saw you're in ",
    "looks like you help homeowners",
    "noticed you offer ",
    "saw you do ",
    "you do landscaping",
    "you do roofing",
    "you do concrete",
    "you do plumbing",
    "you do hvac",
    "you do electrical",
]

# ---------------------------------------------------------------------------
# Observation validation
# ---------------------------------------------------------------------------

class ObservationMissingError(ValueError):
    """Raised when first-touch generation is attempted without an observation."""


class DraftInvalidError(ValueError):
    """Raised when a generated draft fails validation rules."""


def _require_observation(observation: Optional[str]) -> str:
    """Normalize and require a non-empty observation. Raises ObservationMissingError if absent."""
    obs = (observation or "").strip()
    if not obs:
        raise ObservationMissingError(
            "First-touch draft blocked: business_specific_observation is required. "
            "Add a concrete, business-specific detail before generating."
        )
    if len(obs) < 15:
        raise ObservationMissingError(
            "Observation too short to be meaningful. "
            "Write a specific detail about this business — not a category label."
        )
    return obs


def _is_generic_observation(obs: str) -> bool:
    obs_lower = obs.lower()
    return any(phrase in obs_lower for phrase in _GENERIC_OBSERVATION_PHRASES)


def validate_draft(body: str, observation: str) -> None:
    """
    Deterministic validation for first-touch drafts.
    Raises DraftInvalidError with a specific reason on any failure.
    """
    body_lower = body.lower()

    # 1. Banned language
    hits = [w for w in _BANNED_WORDS if w in body_lower]
    if hits:
        raise DraftInvalidError(f"Banned word(s) in draft: {hits}")

    # 2. Sender-centered filler openers
    filler_openers = [
        "i wanted to reach out",
        "my name is",
        "we are a leading",
        "we help businesses like yours",
        "i help businesses like",
    ]
    for filler in filler_openers:
        if body_lower.startswith(filler):
            raise DraftInvalidError(f"Draft opens with sender-centered filler: '{filler}'")

    # 3. Hard CTA language
    hard_cta = [
        "schedule a call", "book a call", "book a meeting",
        "let's hop on", "hop on a call", "set up a call",
        "click here", "visit our website", "check out our",
    ]
    for cta in hard_cta:
        if cta in body_lower:
            raise DraftInvalidError(f"Hard CTA found in first-touch draft: '{cta}'")

    # 4. Links in message
    if re.search(r"https?://", body):
        raise DraftInvalidError("First-touch draft must not contain links.")

    # 5. Pricing
    if re.search(r"\$\d+|\bper month\b|\b/mo\b|\bmonthly\b", body_lower):
        raise DraftInvalidError("First-touch draft must not mention pricing.")

    # 6. Observation must materially appear in the draft
    # Check that at least one meaningful token from the observation is in the body.
    # Strip stop words and punctuation, require >=1 content word overlap.
    _STOP = {"a","an","the","and","or","but","in","on","at","to","for","of",
              "with","is","are","was","were","you","your","i","it","its",
              "that","this","they","them","their","have","has","be","been",
              "not","do","does","did","from","by","as","so","if","we","my"}
    obs_tokens = {
        w.lower().strip(".,;:!?\"'()")
        for w in observation.split()
        if w.lower().strip(".,;:!?\"'()") not in _STOP and len(w) > 3
    }
    body_text = re.sub(r"\n\n[-–—]\s*\w+\s*$", "", body, flags=re.IGNORECASE)
    body_tokens = {
        w.lower().strip(".,;:!?\"'()")
        for w in body_text.split()
    }
    overlap = obs_tokens & body_tokens
    if not overlap:
        raise DraftInvalidError(
            "Draft does not materially reflect the observation. "
            "The observation must meaningfully appear in the message."
        )


# ---------------------------------------------------------------------------
# Post-processing: human style enforcement
# ---------------------------------------------------------------------------

_WORD_TARGET_MAX = 55   # soft ceiling on body_text (sign-off excluded)
_SIGN_OFF = "\n\n- Drew"


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

    # Trim to target word count — keep whole sentences
    words = body_text.split()
    if len(words) > _WORD_TARGET_MAX:
        trimmed = " ".join(words[:_WORD_TARGET_MAX]).rstrip(",;:-")
        last_punct = max(trimmed.rfind("."), trimmed.rfind("?"), trimmed.rfind("!"))
        body_text = trimmed[: last_punct + 1] if last_punct > 0 else trimmed

    body_text = body_text.rstrip(" ,;-")
    if body_text and body_text[-1] not in ".?!":
        body_text += "."
    return body_text


# ---------------------------------------------------------------------------
# Controlled variation patterns
# Three families only — no open-ended variation that drifts back into sales copy.
#
# Family A: observation → grounded sentence → soft open
# Family B: observation → grounded sentence with light operational implication → soft open
# Family C: observation → soft grounded note → soft open
# ---------------------------------------------------------------------------

def _variant_index(business_name: str, n: int = 3) -> int:
    digest = hashlib.sha256(business_name.strip().lower().encode()).hexdigest()
    return int(digest[:8], 16) % n


def _subject_from_observation(observation: str, business_name: str) -> str:
    """Pick a subject that doesn't reveal the observation but stays non-generic."""
    obs_lower = observation.lower()
    if any(w in obs_lower for w in ("snow", "winter", "seasonal")):
        return "seasonal work question"
    if any(w in obs_lower for w in ("repair", "service call", "small job")):
        return "service call question"
    if any(w in obs_lower for w in ("install", "big job", "project")):
        return "install work question"
    if any(w in obs_lower for w in ("mixed", "lineup", "niche", "range")):
        return "quick question"
    if business_name and len(business_name) <= 24:
        return "quick question"
    return "quick question"


def _build_email_body(
    business_name: str,
    observation: str,
    variant: int,
) -> str:
    """
    Assemble the email body from the observation using one of three controlled
    variation families. Returns raw body text (no sign-off).

    Family 0 (A): observation → grounded sentence → soft open
    Family 1 (B): observation → operational implication → soft open
    Family 2 (C): observation → soft grounded note → soft open
    """

    obs = observation.strip().rstrip(".")
    # Normalize: strip leading "saw"/"noticed"/"looks like" so prefixes don't stack
    obs_norm = re.sub(r"^(saw|noticed|looks like|saw that|noticed that)\s+", "", obs, flags=re.IGNORECASE).strip()

    if variant == 0:
        # Family A
        body = (
            f"saw {obs_norm} — building something around that exact workflow gap "
            f"from the business side, not the agency side. "
            f"figured i'd reach out in case it was worth comparing notes sometime."
        )
    elif variant == 1:
        # Family B
        body = (
            f"noticed {obs_norm}. "
            f"i've been working hands-on with real service businesses on where that kind of thing "
            f"gets messy in practice. "
            f"not sure if it's even a thing on your end, but figured i'd ask."
        )
    else:
        # Family C
        body = (
            f"came across your business — {obs_norm}. "
            f"coming at it from the operator side so i've seen where this tends to "
            f"create gaps. "
            f"figured i'd mention it in case another set of eyes would be useful."
        )

    return body


def _build_dm_body(
    business_name: str,
    observation: str,
    variant: int,
) -> str:
    """
    Assemble a DM body. Slightly shorter than email; same structural families.
    """
    obs = observation.strip().rstrip(".")
    obs_norm = re.sub(r"^(saw|noticed|looks like|saw that|noticed that)\s+", "", obs, flags=re.IGNORECASE).strip()

    if variant == 0:
        body = (
            f"hey — saw {obs_norm}. "
            f"been working with service businesses on that exact kind of workflow problem. "
            f"figured i'd reach out in case it was worth a quick conversation."
        )
    elif variant == 1:
        body = (
            f"noticed {obs_norm} — "
            f"i've been helping owner-operators where that kind of thing creates gaps day to day. "
            f"not sure if it's even a problem on your end, figured i'd ask."
        )
    else:
        body = (
            f"came across your page — {obs_norm}. "
            f"i work on this kind of operational stuff from the business side. "
            f"figured i'd mention it in case another set of eyes would be useful."
        )

    return body


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_SUBJECT_OPTIONS = [
    "quick question",
    "missed calls",
    "after-hours follow-up",
]

_HIGH_FIT_INDUSTRIES = {
    "plumbing", "hvac", "electrical", "locksmith", "garage_door", "towing",
}


def draft_email(
    prospect: Dict[str, str],
    final_priority_score: int,
    observation: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Generate a first-touch email draft.

    Requires `observation` — either passed directly or read from
    `prospect["business_specific_observation"]`.

    Raises ObservationMissingError if observation is absent.
    Raises DraftInvalidError if the generated draft fails validation.
    """
    business_name = (prospect.get("business_name") or "").strip()
    city = (prospect.get("city") or "").strip()

    if not business_name:
        raise ValueError("Cannot draft email without business_name.")
    if not city:
        raise ValueError(f"Cannot draft email for {business_name} without city.")

    # Observation: explicit argument takes priority over prospect field
    raw_obs = observation or prospect.get("business_specific_observation") or ""
    obs = _require_observation(raw_obs)

    if _is_generic_observation(obs):
        raise ObservationMissingError(
            "Observation is too generic — it could apply to most businesses in this category. "
            "Write something specific to this business."
        )

    variant = _variant_index(business_name)
    subject = _subject_from_observation(obs, business_name)
    body_text = _build_email_body(business_name, obs, variant)
    body_text = enforce_human_style(body_text)

    full_body = body_text + _SIGN_OFF
    validate_draft(full_body, obs)

    return subject, full_body


def draft_email_json(
    prospect: Dict[str, str],
    final_priority_score: int,
    observation: Optional[str] = None,
) -> Dict:
    subject, body = draft_email(prospect, final_priority_score, observation=observation)
    return {
        "subject": subject,
        "email_body": body,
        "tone": "casual",
    }


def draft_social_messages(
    prospect: Dict[str, str],
    email_body: str,
    observation: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Return short companion drafts for Facebook DM, Instagram DM, and contact-form use.

    Requires observation — either explicit or from prospect field.
    Raises ObservationMissingError if absent.
    Raises DraftInvalidError if generated draft fails validation.
    """
    business_name = (prospect.get("business_name") or "there").strip()

    raw_obs = observation or prospect.get("business_specific_observation") or ""
    obs = _require_observation(raw_obs)

    if _is_generic_observation(obs):
        raise ObservationMissingError(
            "Observation is too generic for DM generation. "
            "Write something specific to this business."
        )

    variant = _variant_index(business_name)
    dm_body = _build_dm_body(business_name, obs, variant)
    dm_body = enforce_human_style(dm_body)

    validate_draft(dm_body, obs)

    return dm_body, dm_body, dm_body


# ---------------------------------------------------------------------------
# Pipeline compatibility shims (unchanged signatures)
# ---------------------------------------------------------------------------

def pick_best_pitch_angle(likely_opportunity: str) -> str:
    return (likely_opportunity or "booking automation").strip() or "booking automation"
