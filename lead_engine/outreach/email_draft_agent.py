from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

DRAFT_VERSION = "v10"

# ---------------------------------------------------------------------------
# Industry detection (pipeline-compatible, unchanged)
# ---------------------------------------------------------------------------

INDUSTRY_SIGNALS: List[Tuple[str, List[str]]] = [
    ("plumbing", ["plumb", "sewer", "drain", "pipe", "rooter", "septic"]),
    ("hvac", ["hvac", "heating", "cooling", "air condition", "furnace", "refrigerat"]),
    ("electrical", ["electric", "wiring", "electrician", "panel", "generator"]),
    ("locksmith", ["locksmith", "lock", "key", "lockout", "rekey"]),
    ("garage_door", ["garage door", "garage", "overhead door"]),
    ("towing", ["tow", "towing", "roadside", "wrecker", "recovery"]),
    ("roofing", ["roof", "gutter", "siding", "shingle"]),
    ("pest_control", ["pest", "exterminator", "termite", "rodent", "bug"]),
    ("auto", ["auto", "mechanic", "car repair", "tire", "collision", "body shop"]),
    ("construction", ["construction", "contractor", "remodel", "renovation", "carpent", "mason"]),
    ("dental", ["dental", "dentist", "orthodont", "oral"]),
    ("medical", ["medical", "clinic", "doctor", "physician", "urgent care", "chiro"]),
    ("legal", ["law", "attorney", "lawyer", "legal", "firm"]),
    ("real_estate", ["real estate", "realty", "realtor", "property management"]),
    ("restaurant", ["restaurant", "diner", "cafe", "catering", "bistro", "eatery", "pizza", "grill"]),
    ("cleaning", ["cleaning", "janitorial", "maid", "housekeeping", "pressure wash"]),
    ("insurance", ["insurance", "insur", "agency", "broker"]),
    ("accounting", ["account", "bookkeep", "tax", "cpa", "payroll"]),
    ("salon", ["salon", "barber", "hair", "nail", "spa", "beauty"]),
    ("gym", ["gym", "fitness", "personal train", "yoga", "pilates"]),
    ("moving", ["moving", "mover", "storage", "relocation"]),
    ("landscaping", ["landscap", "lawn", "garden", "tree", "mow", "sod"]),
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
# Banned language - applies to all first-touch drafts
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
    "free audit", "free consultation", "streamline operations",
    "maximize efficiency", "unlock growth", "transform your business",
]

_VAGUE_POSITIONING_PHRASES = [
    "workflow gap",
    "from the business side",
    "not the agency side",
    "another set of eyes",
    "operational stuff",
    "compare notes sometime",
    "worth comparing notes",
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
# Genericity detection - swappability test
# ---------------------------------------------------------------------------

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

_CONCRETE_SERVICE_SIGNALS = [
    "missed-call text back",
    "text-back",
    "after-hours response",
    "after-hours reply",
    "lead tracking",
    "contact form routing",
    "inquiry routing",
    "estimate follow-up",
    "quote follow-up",
    "callback recovery",
    "intake capture",
    "pipeline",
    "calls",
    "call",
    "callbacks",
    "callback",
    "estimate requests",
    "quotes",
    "follow-up",
    "inquiries",
    "scheduling",
]


# ---------------------------------------------------------------------------
# Observation validation
# ---------------------------------------------------------------------------

class ObservationMissingError(ValueError):
    """Raised when first-touch generation is attempted without an observation."""


class DraftInvalidError(ValueError):
    """Raised when a generated draft fails validation rules."""


def _require_observation(observation: Optional[str]) -> str:
    """Normalize and require a non-empty observation. Raises if absent."""
    obs = (observation or "").strip()
    if not obs:
        raise ObservationMissingError(
            "First-touch draft blocked: business_specific_observation is required. "
            "Add a concrete, business-specific detail before generating."
        )
    if len(obs) < 15:
        raise ObservationMissingError(
            "Observation too short to be meaningful. "
            "Write a specific detail about this business - not a category label."
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

    hits = [w for w in _BANNED_WORDS if w in body_lower]
    if hits:
        raise DraftInvalidError(f"Banned word(s) in draft: {hits}")

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

    vague_hits = [phrase for phrase in _VAGUE_POSITIONING_PHRASES if phrase in body_lower]
    if vague_hits:
        raise DraftInvalidError(f"Vague positioning found in draft: {vague_hits}")

    hard_cta = [
        "schedule a call", "book a call", "book a meeting",
        "let's hop on", "hop on a call", "set up a call",
        "click here", "visit our website", "check out our",
    ]
    for cta in hard_cta:
        if cta in body_lower:
            raise DraftInvalidError(f"Hard CTA found in first-touch draft: '{cta}'")

    if re.search(r"https?://", body):
        raise DraftInvalidError("First-touch draft must not contain links.")

    if re.search(r"\$\d+|\bper month\b|\b/mo\b|\bmonthly\b", body_lower):
        raise DraftInvalidError("First-touch draft must not mention pricing.")

    stop_words = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
        "with", "is", "are", "was", "were", "you", "your", "i", "it", "its",
        "that", "this", "they", "them", "their", "have", "has", "be", "been",
        "not", "do", "does", "did", "from", "by", "as", "so", "if", "we", "my",
    }
    obs_tokens = {
        w.lower().strip(".,;:!?\"'()")
        for w in observation.split()
        if w.lower().strip(".,;:!?\"'()") not in stop_words and len(w) > 3
    }
    body_text = re.sub(r"\n\n[-–—]\s*\w+\s*$", "", body, flags=re.IGNORECASE)
    body_tokens = {w.lower().strip(".,;:!?\"'()") for w in body_text.split()}
    overlap = obs_tokens & body_tokens
    if not overlap:
        raise DraftInvalidError(
            "Draft does not materially reflect the observation. "
            "The observation must meaningfully appear in the message."
        )

    if not any(signal in body_lower for signal in _CONCRETE_SERVICE_SIGNALS):
        raise DraftInvalidError(
            "Draft does not mention a concrete service-business bottleneck or fix."
        )


# ---------------------------------------------------------------------------
# Post-processing: human style enforcement
# ---------------------------------------------------------------------------

_WORD_TARGET_MAX = 68
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
# Deterministic first-touch offer framing
# ---------------------------------------------------------------------------

_ANGLE_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("after_hours_response", [
        "emergency", "after hours", "after-hours", "24/7", "24 7",
        "same day", "same-day", "urgent", "nights", "weekend",
    ]),
    ("estimate_follow_up", [
        "estimate", "estimates", "quote", "quotes", "financing",
        "proposal", "proposals",
    ]),
    ("service_requests", [
        "booking", "book online", "schedule", "scheduling",
        "appointment", "appointments",
    ]),
    ("inquiry_routing", [
        "contact form", "form", "chat", "message", "messages",
        "text", "texting",
    ]),
    ("callback_recovery", [
        "phone", "phones", "call", "calls", "callback", "callbacks",
        "voicemail", "dispatch",
    ]),
]


def _variant_index(business_name: str, n: int = 3) -> int:
    digest = hashlib.sha256(business_name.strip().lower().encode()).hexdigest()
    return int(digest[:8], 16) % n


def _normalize_observation_sentence(observation: str) -> str:
    obs = observation.strip().rstrip(".")
    obs = re.sub(
        r"^(saw|noticed|looks like|came across|saw that|noticed that)\s+",
        "",
        obs,
        flags=re.IGNORECASE,
    ).strip()
    if obs and obs[0].isalpha():
        obs = obs[0].lower() + obs[1:]
    return obs


def _sentence_case(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def _pick_offer_angle(prospect: Dict[str, str], observation: str) -> str:
    obs_lower = observation.lower()
    for angle, keywords in _ANGLE_KEYWORDS:
        if any(keyword in obs_lower for keyword in keywords):
            return angle

    likely = (prospect.get("likely_opportunity") or "").lower()
    if "after" in likely or "missed" in likely or "call" in likely:
        return "callback_recovery"
    if "estimate" in likely or "quote" in likely or "follow" in likely:
        return "estimate_follow_up"
    return "owner_workflow"


def _subject_from_observation(observation: str, business_name: str, angle: str) -> str:
    """Pick a short subject that reflects the real offer without sounding salesy."""
    if angle == "after_hours_response":
        return "after-hours question"
    if angle == "estimate_follow_up":
        return "estimate follow-up question"
    if angle == "service_requests":
        return "service request question"
    if angle == "inquiry_routing":
        return "contact flow question"
    if angle == "callback_recovery":
        return "missed calls question"
    return "quick question"


def _angle_consequence(angle: str, variant: int) -> str:
    options = {
        "after_hours_response": [
            "usually the breakdown is calls and after-hours requests getting answered consistently",
            "usually the mess shows up when emergency calls come in after the day is already packed",
            "usually the strain is keeping late calls and urgent follow-up from slipping",
        ],
        "estimate_follow_up": [
            "usually the breakdown is quote requests and follow-up sitting too long",
            "usually the mess shows up once estimates go out and nobody has time to stay on them",
            "usually the strain is keeping estimate requests and callbacks moving once the day gets busy",
        ],
        "service_requests": [
            "usually the breakdown is new service requests and callbacks slipping once the day gets busy",
            "usually the mess shows up when appointment requests start stacking up without a clean follow-up path",
            "usually the strain is keeping new requests from getting a quick response once the day fills up",
        ],
        "inquiry_routing": [
            "usually the breakdown is web inquiries landing in the wrong place or sitting too long",
            "usually the mess shows up when form fills and booking requests are not getting routed cleanly",
            "usually the strain is keeping new inquiries from disappearing once jobs start stacking up",
        ],
        "callback_recovery": [
            "usually the breakdown is calls and callbacks slipping once the phone starts stacking up",
            "usually the mess shows up when the day gets busy and new inquiries stop getting quick follow-up",
            "usually the strain is keeping missed calls from turning into dead ends",
        ],
        "owner_workflow": [
            "usually the breakdown is calls, estimate requests, or follow-up slipping once the day fills up",
            "usually the mess shows up when a busy day leaves no clean handoff for new inquiries",
            "usually the strain is keeping callbacks, quotes, and follow-up moving once work starts piling up",
        ],
    }
    family = options.get(angle) or options["owner_workflow"]
    return family[variant % len(family)]


def _angle_offer(angle: str, variant: int, *, channel: str) -> str:
    if angle == "after_hours_response":
        offers = [
            "i work one-on-one with owners on practical fixes like missed-call text back or after-hours response",
            "i help owners tighten things up with simple missed-call text back and after-hours reply coverage",
            "i work one-on-one with owners on simple after-hours response and callback recovery",
        ]
    elif angle == "estimate_follow_up":
        offers = [
            "i work one-on-one with owners on practical fixes like estimate follow-up or simple lead tracking",
            "i help owners clean up quote follow-up and the basic pipeline around it",
            "i work one-on-one with owners on estimate reminders and simple lead tracking that fits how they already run",
        ]
    elif angle == "inquiry_routing":
        offers = [
            "i work one-on-one with owners on practical fixes like contact form routing or basic intake capture",
            "i help owners clean up inquiry routing, text-back, and basic intake without changing the whole shop",
            "i work one-on-one with owners on simple intake capture and contact routing so good inquiries do not disappear",
        ]
    elif angle == "service_requests":
        offers = [
            "i work one-on-one with owners on practical fixes like callback recovery, text-back, or basic intake capture",
            "i help owners tighten how new service requests get answered and handed off",
            "i work one-on-one with owners on simple intake and callback follow-up that fits how they already run",
        ]
    elif angle == "callback_recovery":
        offers = [
            "i work one-on-one with owners on practical fixes like callback recovery or missed-call text back",
            "i help owners tighten missed-call follow-up and simple inquiry handling",
            "i work one-on-one with owners on callback recovery and after-hours response that fits how the business already runs",
        ]
    else:
        offers = [
            "i work one-on-one with owners on practical fixes like missed-call text back, estimate follow-up, or inquiry routing",
            "i help owners figure out where calls, quotes, or follow-up are breaking down and tighten the weak spot",
            "i work one-on-one with owners on simple intake, callback, or follow-up fixes that fit how they already run",
        ]

    offer = offers[variant % len(offers)]
    if channel == "dm" and "one-on-one with owners" in offer:
        offer = offer.replace("one-on-one with owners", "directly with owners")
    return offer


def _soft_close(angle: str, variant: int, *, channel: str) -> str:
    if channel == "dm":
        closers = [
            "happy to share what i'd check first if useful",
            "if that is a live issue there, happy to send over what i'd look at first",
            "if useful, i can send the first fix i'd usually look at",
        ]
    elif angle == "estimate_follow_up":
        closers = [
            "happy to share what i'd check first if useful",
            "if that is a live issue there, happy to send over where i'd start",
            "if helpful, i can send the first thing i'd look at",
        ]
    else:
        closers = [
            "happy to share what i'd check first if useful",
            "if that is a live issue there, happy to send over where i'd start",
            "if helpful, i can send the first place i'd look",
        ]
    return closers[variant % len(closers)]


def _build_first_touch_body(
    prospect: Dict[str, str],
    observation: str,
    variant: int,
    *,
    channel: str,
) -> str:
    obs_norm = _normalize_observation_sentence(observation)
    angle = _pick_offer_angle(prospect, observation)
    opener = {
        "email": [
            f"saw that {obs_norm}.",
            f"noticed {obs_norm}.",
            f"{_sentence_case(obs_norm)}.",
        ],
        "dm": [
            f"hey - saw that {obs_norm}.",
            f"hey - noticed {obs_norm}.",
            f"hey - {obs_norm}.",
        ],
    }[channel][variant % 3]
    consequence = _angle_consequence(angle, variant)
    offer = _angle_offer(angle, variant, channel=channel)
    close = _soft_close(angle, variant, channel=channel)
    return f"{opener} {consequence}. {offer}. {close}."


def _build_email_body(
    prospect: Dict[str, str],
    observation: str,
    variant: int,
) -> str:
    return _build_first_touch_body(prospect, observation, variant, channel="email")


def _build_dm_body(
    prospect: Dict[str, str],
    observation: str,
    variant: int,
) -> str:
    return _build_first_touch_body(prospect, observation, variant, channel="dm")


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

    Requires `observation` - either passed directly or read from
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

    raw_obs = observation or prospect.get("business_specific_observation") or ""
    obs = _require_observation(raw_obs)

    if _is_generic_observation(obs):
        raise ObservationMissingError(
            "Observation is too generic - it could apply to most businesses in this category. "
            "Write something specific to this business."
        )

    variant = _variant_index(business_name)
    angle = _pick_offer_angle(prospect, obs)
    subject = _subject_from_observation(obs, business_name, angle)
    body_text = _build_email_body(prospect, obs, variant)
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

    Requires observation - either explicit or from prospect field.
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
    dm_body = _build_dm_body(prospect, obs, variant)
    dm_body = enforce_human_style(dm_body)

    validate_draft(dm_body, obs)

    return dm_body, dm_body, dm_body


# ---------------------------------------------------------------------------
# Pipeline compatibility shims (unchanged signatures)
# ---------------------------------------------------------------------------

def pick_best_pitch_angle(likely_opportunity: str) -> str:
    return (likely_opportunity or "booking automation").strip() or "booking automation"
