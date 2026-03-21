from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

DRAFT_VERSION = "v12"

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

_SUBJECT_BANNED_PHRASES = [
    "ai", "automation", "automate", "solution", "opportunity", "support",
    "checking in", "increase revenue", "grow your business", "urgent",
    "last chance", "free audit", "free consultation",
]

_VAGUE_POSITIONING_PHRASES = [
    "workflow gap",
    "from the business side",
    "not the agency side",
    "another set of eyes",
    "operational stuff",
    "compare notes sometime",
    "worth comparing notes",
    "site is pretty explicit about",
    "the mess shows up",
    "if that is a live issue there",
    "where i'd start",
    "what i'd look at first",
    "first place i'd look",
]

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
    "missed calls",
    "after-hours response",
    "after-hours reply",
    "after-hours calls",
    "lead tracking",
    "contact form routing",
    "inquiry routing",
    "estimate follow-up",
    "quote follow-up",
    "callback recovery",
    "intake capture",
    "pipeline",
    "calls",
    "callbacks",
    "estimate requests",
    "quotes",
    "follow-up",
    "slow follow-up",
    "inquiries",
    "new leads",
    "new requests",
    "service requests",
    "getting back to people",
    "response side",
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
    body_text = re.sub(r"\n\n-\s*\w+\s*$", "", body, flags=re.IGNORECASE)
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


def validate_subject(subject: str) -> None:
    subj = (subject or "").strip().lower()
    if not subj:
        raise DraftInvalidError("First-touch subject must not be empty.")
    if len(subj) > 48:
        raise DraftInvalidError("First-touch subject is too long.")
    if len(subj.split()) > 6:
        raise DraftInvalidError("First-touch subject uses too many words.")
    if "!" in subj:
        raise DraftInvalidError("First-touch subject must not use hype punctuation.")
    hits = [phrase for phrase in _SUBJECT_BANNED_PHRASES if phrase in subj]
    if hits:
        raise DraftInvalidError(f"Banned phrase(s) in subject: {hits}")


# ---------------------------------------------------------------------------
# Post-processing: human style enforcement
# ---------------------------------------------------------------------------

_WORD_TARGET_MAX = 86
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
    obs_lower = obs.lower()
    replacements = [
        ("site is pretty explicit about ", "you put a lot of emphasis on "),
        ("site is explicit about ", "you put a lot of emphasis on "),
        ("site is clear about ", "you put a lot of emphasis on "),
        ("they are pushing ", "you put a lot of emphasis on "),
        ("they're pushing ", "you put a lot of emphasis on "),
        ("your site leans hard on ", "you put a lot of emphasis on "),
        ("your site pushes ", "you put a lot of emphasis on "),
        ("your site keeps ", "you keep "),
        ("your site splits ", "you split "),
        ("they are ", "you're "),
        ("they're ", "you're "),
        ("their ", "your "),
        ("contact form ", "your contact form "),
        ("phone number ", "your phone number "),
        ("site ", "your site "),
    ]
    for old, new in replacements:
        if obs_lower.startswith(old):
            obs = new + obs[len(old):]
            break
    obs = obs.replace(" pretty hard on the homepage", " on the homepage")
    if obs and obs[0].isalpha():
        obs = obs[0].lower() + obs[1:]
    return obs


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


def _subject_options_for_angle(angle: str, observation: str) -> List[str]:
    obs_lower = observation.lower()
    if angle == "after_hours_response":
        return [
            "after-hours calls",
            "question about emergency calls",
            "emergency calls",
        ]
    if angle == "estimate_follow_up":
        return [
            "estimate follow-up",
            "estimate follow-up question",
            "quote requests",
        ]
    if angle == "service_requests":
        if "scheduling" in obs_lower or "appointment" in obs_lower:
            return [
                "service requests",
                "question about scheduling",
                "new requests",
            ]
        return [
            "service requests",
            "question about scheduling",
            "new requests",
        ]
    if angle == "inquiry_routing":
        if "contact form" in obs_lower:
            return [
                "contact form follow-up",
                "question about inquiries",
                "new inquiries",
            ]
        return [
            "inquiries",
            "question about inquiries",
            "new inquiries",
        ]
    if angle == "callback_recovery":
        return [
            "call handling",
            "question about call handling",
            "missed calls",
        ]
    return [
        "call handling",
        "question about follow-up",
        "new inquiries",
    ]


def _subject_from_observation(observation: str, business_name: str, angle: str) -> str:
    """Pick a short subject that fits the body angle without sounding spammy."""
    options = _subject_options_for_angle(angle, observation)
    pick = _variant_index(business_name, len(options))
    return options[pick]


def _angle_consequence(angle: str, variant: int) -> str:
    options = {
        "after_hours_response": [
            "usually the hard part is not the work itself, it's making sure after-hours calls and follow-up do not get missed once the day gets busy",
            "a lot of shops pushing that kind of work run into missed calls and slow follow-up after hours",
            "that kind of setup often creates pressure around after-hours calls, callbacks, and getting people a response quickly",
        ],
        "estimate_follow_up": [
            "usually the hard part is not the work itself, it's estimate requests sitting too long once the day gets busy",
            "a lot of shops in that position run into slow quote follow-up even when the work itself is solid",
            "that kind of setup often turns into estimate requests and callbacks stacking up when the schedule gets full",
        ],
        "service_requests": [
            "usually the hard part is not the work itself, it's new service requests not getting handled consistently once the day gets busy",
            "a lot of shops in that position run into slow follow-up on new requests when the schedule fills up",
            "that kind of setup often leads to appointment requests and callbacks piling up faster than anyone can stay on them",
        ],
        "inquiry_routing": [
            "usually the hard part is not the work itself, it's web inquiries and messages slipping through once the day gets busy",
            "a lot of shops in that position run into slow follow-up when new inquiries come in from a few different places",
            "that kind of setup often means new inquiries sit too long or get handled inconsistently",
        ],
        "callback_recovery": [
            "usually the hard part is not the work itself, it's missed calls and callbacks piling up once the phone starts going",
            "a lot of shops in that position run into slow follow-up when calls come in faster than anyone can get back to them",
            "that kind of setup often leaves missed calls and new inquiries sitting longer than they should",
        ],
        "owner_workflow": [
            "usually the hard part is not the work itself, it's missed calls, slow follow-up, and estimate requests sitting too long once the day gets busy",
            "a lot of shops in that position run into new inquiries slipping through when everyone is focused on the work in front of them",
            "that kind of setup often creates missed calls, delayed quotes, or inconsistent follow-up once things get busy",
        ],
    }
    family = options.get(angle) or options["owner_workflow"]
    return family[variant % len(family)]


def _angle_offer(angle: str, variant: int) -> str:
    if angle == "after_hours_response":
        offers = [
            "i work one-on-one with owners to figure out where that handoff is breaking down and put something practical in place",
            "i work directly with owners on the follow-up side, usually around missed calls, callbacks, and after-hours coverage",
            "i help owners tighten the response side so new calls do not just sit until someone has time",
        ]
    elif angle == "estimate_follow_up":
        offers = [
            "i work one-on-one with owners to figure out where follow-up is stalling and tighten it up without changing how the shop already runs",
            "i help owners clean up the part between an incoming request and an actual follow-up",
            "i work directly with owners on the follow-up side, usually around estimate requests, callbacks, and keeping good leads from cooling off",
        ]
    elif angle == "inquiry_routing":
        offers = [
            "i work one-on-one with owners to figure out where inquiries are slipping through and make the follow-up side more consistent",
            "i help owners clean up the part between a web inquiry coming in and somebody actually getting back to it",
            "i work directly with owners on the response side when messages are coming in from a few different places",
        ]
    elif angle == "service_requests":
        offers = [
            "i work one-on-one with owners to figure out where new requests are getting hung up and make the response side easier to stay on top of",
            "i help owners clean up the handoff from the first inquiry to the first real follow-up",
            "i work directly with owners on the response side so new requests do not depend on whoever happens to notice them first",
        ]
    elif angle == "callback_recovery":
        offers = [
            "i work one-on-one with owners to figure out where missed calls and follow-up are breaking down and make that easier to stay on top of",
            "i help owners clean up the part after the phone rings, especially when callbacks start getting pushed",
            "i work directly with owners on missed calls, slow follow-up, and making sure good inquiries do not just sit",
        ]
    else:
        offers = [
            "i work one-on-one with owners to figure out where calls, estimate requests, or follow-up are breaking down once the day gets busy",
            "i help owners clean up the response side so new inquiries do not depend on somebody remembering them later",
            "i work directly with owners on the part after the lead comes in - missed calls, slow follow-up, and estimate requests sitting too long",
        ]
    return offers[variant % len(offers)]


def _soft_close(channel: str, variant: int) -> str:
    if channel == "dm":
        closers = [
            "happy to share a couple ideas if useful",
            "if useful, i can send a few thoughts based on what i saw",
            "if you'd like, i can send over a couple ideas that might fit your setup",
        ]
    else:
        closers = [
            "happy to share a few ideas specific to your setup if useful",
            "if useful, i'm happy to send a couple thoughts based on what i saw",
            "if you'd like, i can send over a few ideas that might fit the way you already run things",
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
    if obs_norm.startswith("your site "):
        email_openers = [
            f"i noticed {obs_norm}.",
            f"saw that {obs_norm}.",
            f"noticed that {obs_norm}.",
        ]
        dm_openers = [
            f"hey - i noticed {obs_norm}.",
            f"hey - saw that {obs_norm}.",
            f"hey - noticed that {obs_norm}.",
        ]
    else:
        email_openers = [
            f"i was checking out your site and noticed {obs_norm}.",
            f"saw on your site that {obs_norm}.",
            f"noticed on your site that {obs_norm}.",
        ]
        dm_openers = [
            f"hey - i was checking out your site and noticed {obs_norm}.",
            f"hey - saw on your site that {obs_norm}.",
            f"hey - noticed on your site that {obs_norm}.",
        ]
    opener = {
        "email": email_openers,
        "dm": dm_openers,
    }[channel][variant % 3]
    consequence = _angle_consequence(angle, variant)
    offer = _angle_offer(angle, variant)
    close = _soft_close(channel, variant)
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
    validate_subject(subject)
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
