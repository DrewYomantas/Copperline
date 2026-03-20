from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

DRAFT_VERSION = "v17"

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
# Banned language
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
    "happy to", "worth a look", "doesn't have to be complicated",
]

_SUBJECT_BANNED_PHRASES = [
    "ai", "automation", "automate", "solution", "opportunity", "support",
    "checking in", "increase revenue", "grow your business", "urgent",
    "last chance", "free audit", "free consultation",
]

_VAGUE_POSITIONING_PHRASES = [
    "workflow gap", "from the business side", "not the agency side",
    "another set of eyes", "operational stuff", "compare notes sometime",
    "worth comparing notes", "site is pretty explicit about",
    "the mess shows up", "if that is a live issue there",
    "where i'd start", "what i'd look at first", "first place i'd look",
]

_FORMAL_OPENER_SUBS = [
    ("I noticed that ", ""), ("I wanted to reach out ", ""),
    ("I wanted to reach out", ""), ("my name is", "My name is"),
    ("We are a leading", ""), ("we are a leading", ""),
    ("we help businesses like yours", ""), ("We help businesses like yours", ""),
    ("I help businesses ", ""), ("We offer ", ""), ("We offer", ""),
    ("AI-powered", "simple"), ("ai-powered", "simple"),
    ("streamline", "speed up"), ("optimize", "improve"),
    ("solution", "fix"), ("platform", "system"),
]


# ---------------------------------------------------------------------------
# Genericity detection
# ---------------------------------------------------------------------------

_GENERIC_OBSERVATION_PHRASES = [
    "noticed you do ", "saw you're in ", "looks like you help homeowners",
    "noticed you offer ", "saw you do ", "you do landscaping", "you do roofing",
    "you do concrete", "you do plumbing", "you do hvac", "you do electrical",
]

# Concrete signals - expanded to cover natural consequence/offer language
_CONCRETE_SERVICE_SIGNALS = [
    "missed-call text back", "text-back", "missed calls",
    "after-hours response", "after-hours reply", "after-hours calls",
    "lead tracking", "contact form routing", "inquiry routing",
    "estimate follow-up", "quote follow-up", "callback recovery",
    "intake capture", "pipeline", "calls", "callbacks", "estimate requests",
    "quotes", "follow-up", "slow follow-up", "inquiries", "new leads",
    "new requests", "service requests", "getting back to people",
    "response side", "sit", "stack up", "pile up", "slip", "fall through",
    "go cold", "gone cold", "gone somewhere else", "moved on",
    "unanswered", "not get returned", "never sees", "no idea",
    "outside of that", "leaking", "falling through", "go unanswered",
]


# ---------------------------------------------------------------------------
# Observation validation
# ---------------------------------------------------------------------------

class ObservationMissingError(ValueError):
    """Raised when first-touch generation is attempted without an observation."""


class DraftInvalidError(ValueError):
    """Raised when a generated draft fails validation rules."""


def _require_observation(observation: Optional[str]) -> str:
    obs = (observation or "").strip()
    if not obs:
        raise ObservationMissingError(
            "First-touch draft blocked: observation is required."
        )
    if len(obs) < 15:
        raise ObservationMissingError(
            "Observation too short. Write a specific detail about this business."
        )
    return obs


def _is_generic_observation(obs: str) -> bool:
    return any(phrase in obs.lower() for phrase in _GENERIC_OBSERVATION_PHRASES)


def validate_draft(body: str, observation: str) -> None:
    """Deterministic validation. Raises DraftInvalidError with specific reason."""
    body_lower = body.lower()

    hits = [w for w in _BANNED_WORDS if w in body_lower]
    if hits:
        raise DraftInvalidError(f"Banned word(s) in draft: {hits}")

    filler_openers = [
        "i wanted to reach out", "we are a leading",
        "we help businesses like yours", "i help businesses like",
    ]
    for filler in filler_openers:
        if body_lower.startswith(filler):
            raise DraftInvalidError(f"Draft opens with filler: '{filler}'")

    vague_hits = [p for p in _VAGUE_POSITIONING_PHRASES if p in body_lower]
    if vague_hits:
        raise DraftInvalidError(f"Vague positioning in draft: {vague_hits}")

    hard_cta = [
        "schedule a call", "book a call", "book a meeting",
        "let's hop on", "hop on a call", "set up a call",
        "click here", "visit our website", "check out our",
    ]
    for cta in hard_cta:
        if cta in body_lower:
            raise DraftInvalidError(f"Hard CTA found: '{cta}'")

    if re.search(r"https?://", body):
        raise DraftInvalidError("Draft must not contain links.")

    if re.search(r"\$\d+|\bper month\b|\b/mo\b|\bmonthly\b", body_lower):
        raise DraftInvalidError("Draft must not mention pricing.")

    stop_words = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
        "with", "is", "are", "was", "were", "you", "your", "i", "it", "its",
        "that", "this", "they", "them", "their", "have", "has", "be", "been",
        "not", "do", "does", "did", "from", "by", "as", "so", "if", "we", "my",
        "saw", "just", "there", "those", "when", "out", "up", "no", "its",
    }
    obs_tokens = {
        w.lower().strip(".,;:!?\"'()")
        for w in observation.split()
        if w.lower().strip(".,;:!?\"'()") not in stop_words and len(w) > 3
    }
    body_text = re.sub(r"\n\n-\s*\w+\s*$", "", body, flags=re.IGNORECASE)
    body_tokens = {w.lower().strip(".,;:!?\"'()") for w in body_text.split()}
    if not (obs_tokens & body_tokens):
        raise DraftInvalidError("Draft does not reflect the observation.")

    if not any(s in body_lower for s in _CONCRETE_SERVICE_SIGNALS):
        raise DraftInvalidError(
            "Draft does not mention a concrete business problem or gap."
        )


def validate_subject(subject: str) -> None:
    subj = (subject or "").strip().lower()
    if not subj:
        raise DraftInvalidError("Subject must not be empty.")
    if len(subj) > 48:
        raise DraftInvalidError("Subject is too long.")
    if len(subj.split()) > 6:
        raise DraftInvalidError("Subject uses too many words.")
    if "!" in subj:
        raise DraftInvalidError("Subject must not use hype punctuation.")
    hits = [p for p in _SUBJECT_BANNED_PHRASES if p in subj]
    if hits:
        raise DraftInvalidError(f"Banned phrase(s) in subject: {hits}")


# ---------------------------------------------------------------------------
# Post-processing (light — voice does not need heavy cleanup)
# ---------------------------------------------------------------------------

_SIGN_OFF = "\n\nDrew"


def enforce_human_style(body_text: str) -> str:
    """Light cleanup only. Drew's voice is already direct — don't over-process."""
    if not body_text:
        return body_text
    # Kill any formal opener subs that sneak through
    for pattern, replacement in _FORMAL_OPENER_SUBS:
        if pattern in body_text:
            body_text = body_text.replace(pattern, replacement)
    # Clean up double spaces
    body_text = re.sub(r" {2,}", " ", body_text)
    body_text = re.sub(r"\s+([,.?!])", r"\1", body_text)
    return body_text.strip()


# ---------------------------------------------------------------------------
# Angle detection
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


def _component_variant_index(
    prospect: Dict[str, str],
    observation: str,
    angle: str,
    component: str,
    n: int,
    *,
    channel: str = "email",
) -> int:
    if n <= 0:
        return 0
    business_name = (prospect.get("business_name") or "").strip().lower()
    city = (prospect.get("city") or "").strip().lower()
    industry = (prospect.get("industry") or "").strip().lower()
    obs_norm = re.sub(r"\s+", " ", (observation or "").strip().lower())
    digest = hashlib.sha256(
        f"{component}|{channel}|{angle}|{business_name}|{city}|{industry}|{obs_norm}".encode()
    ).hexdigest()
    return int(digest[:8], 16) % n


def _pick_offer_angle(prospect: Dict[str, str], observation: str) -> str:
    obs_lower = observation.lower()
    for angle, keywords in _ANGLE_KEYWORDS:
        if any(kw in obs_lower for kw in keywords):
            return angle
    likely = (prospect.get("likely_opportunity") or "").lower()
    if "after" in likely or "missed" in likely or "call" in likely:
        return "callback_recovery"
    if "estimate" in likely or "quote" in likely or "follow" in likely:
        return "estimate_follow_up"
    return "owner_workflow"


# ---------------------------------------------------------------------------
# Voice-matched body construction (v17)
#
# Structure: 4 short paragraphs, line break between each.
# P1: "My name is Drew. Saw [specific observation]."
# P2: Consequence — "A lot of those probably..." natural, hedged.
# P3: Positioning — one on one, full picture, specific to how they run things.
# P4: Real close question. Never "happy to", never "worth a look".
#
# What Drew sells: personalized one-on-one consultation, looks at the whole
# operation, builds custom systems specific to that business. Not a product.
# ---------------------------------------------------------------------------

def _build_observation_opener(obs: str) -> str:
    """
    Convert the stored observation into a natural 'Saw you...' sentence.
    Direct, present tense, no 'I noticed that' or 'I was checking out'.
    """
    o = obs.strip().rstrip(".")
    o_lower = o.lower()

    # Strip redundant openers the operator may have typed
    o = re.sub(
        r"^(saw that|noticed that|saw |noticed |looks like |came across —?\s*)",
        "", o, flags=re.IGNORECASE,
    ).strip()

    # Normalize third-person site references to second-person
    replacements = [
        ("your site has ", "you have "),
        ("your site lists ", "you're listing "),
        ("your site pushes ", "you're pushing "),
        ("your site advertises ", "you're advertising "),
        ("your site keeps ", "you keep "),
        ("your site splits ", "you split "),
        ("your site leans ", "you lean "),
        ("your site is ", "your setup is "),
        ("your homepage has ", "you have "),
        ("your homepage centers ", "you're centering "),
        ("you put a lot of emphasis on ", "you're pushing "),
    ]
    for old, new in replacements:
        if o.lower().startswith(old):
            o = new + o[len(old):]
            break

    # Lowercase first char
    if o and o[0].isalpha():
        o = o[0].lower() + o[1:]

    return f"Saw {o}."


def _build_consequence_sentence(obs: str, angle: str) -> str:
    """
    One short natural sentence about what that specific thing probably means.
    Hedged with 'probably' or 'usually' — not stated as fact.
    Drew's pattern: 'A lot of those probably...' or 'When that happens...'
    """
    o = obs.lower()

    if any(p in o for p in (
        "no confirmation", "no immediate", "nothing back",
        "no next step", "no acknowledgment", "unclear",
    )) and any(p in o for p in ("form", "submit", "contact", "inquiry")):
        return "They fill it out and have no idea if anyone saw it. A lot of those just go cold."

    if any(p in o for p in ("voicemail", "dispatch number", "dispatch line")):
        return "A lot of those probably don't get returned until the next morning and by then most people have already moved on."

    if any(p in o for p in (
        "only contact", "only way", "no other contact",
        "just a phone", "single phone", "phone is the main", "phone number prominently",
    )):
        return "When you're out on a job and a call comes in, a lot of those just go cold before anyone gets back to them."

    if any(p in o for p in ("24/7", "24 7", "emergency service", "same-day response", "same day response")):
        return "That's a tough commitment to keep when you're short staffed or mid job. A lot of those after hours calls probably go unanswered more than people realize."

    if any(p in o for p in ("after-hours", "after hours", "weekend", "nights")):
        return "A lot of those probably don't get followed up until the next morning and by then most people have already moved on."

    if any(p in o for p in (
        "estimate request form", "estimate form", "primary call to action",
        "free estimate", "quote request form", "free quote",
    )):
        return "A lot of those probably just sit there until someone has time to get to them and by then people have already gone somewhere else."

    if any(p in o for p in ("quote button", "quote on every page", "push free quote")):
        return "A lot of those requests probably sit until someone gets around to following up, which is usually too late."

    if any(p in o for p in (
        "proposal request", "proposal form", "free in-home",
    )):
        return "A lot of those probably go cold while someone is waiting to hear back."

    if any(p in o for p in ("chat widget", "text-back", "text back", "few different places", "couple different")):
        return "When messages are coming in from a few places at once, a lot of them probably fall through."

    if any(p in o for p in ("online booking", "booking widget", "scheduling widget")):
        return "The booking side looks covered but requests that come in outside of that usually just sit until someone notices them."

    if any(p in o for p in ("scheduling link", "pick a service window")):
        return "A lot of people probably book and then don't hear anything back, which tends to create no-shows."

    # Angle fallbacks — short, hedged, natural
    fallbacks = {
        "after_hours_response":
            "A lot of those after hours calls probably go unanswered more than people realize.",
        "estimate_follow_up":
            "A lot of those probably just sit there until someone gets around to them.",
        "service_requests":
            "New requests tend to pile up faster than it looks, especially once the schedule fills.",
        "inquiry_routing":
            "A lot of those probably fall through when things get busy.",
        "callback_recovery":
            "When you're out on a job and a call comes in, a lot of those just go cold.",
        "owner_workflow":
            "A lot of those probably slip through when everyone is focused on the work in front of them.",
    }
    return fallbacks.get(angle, fallbacks["owner_workflow"])


def _build_offer_sentence(obs: str, angle: str, variant: int) -> str:
    """
    Drew's actual positioning: one on one, looks at the full picture,
    builds something specific to how they run things.
    Three variants that all say the same thing differently.
    No product pitch. No feature description.
    """
    variants = [
        "I work one on one with owners to find where things like that are slipping and put something together specific to how they run things.",
        "I work one on one with owners to look at the full picture and build something around how they actually run their business.",
        "I work one on one with owners to look at where things are falling through and put something in place that actually fits their setup.",
    ]
    return variants[variant % len(variants)]


def _build_close_sentence(obs: str, angle: str, variant: int, channel: str) -> str:
    """
    Real question. Not permission. Not 'happy to'. Not 'worth a look'.
    Drew closes with a direct soft question that invites a reply.
    """
    o = obs.lower()

    # Contextually specific closes based on observation
    if any(p in o for p in ("24/7", "emergency", "same-day", "same day")):
        closes = [
            "Worth a quick call to talk through it?",
            "Would it be worth jumping on a quick call?",
            "Curious if that's something worth talking through?",
        ]
    elif any(p in o for p in ("dental", "medical", "clinic", "practice", "doctor")):
        closes = [
            "Would it be worth a quick conversation?",
            "Worth a call to look at it together?",
            "Curious if that's worth a quick conversation?",
        ]
    elif channel == "dm":
        closes = [
            "Worth a quick conversation?",
            "Curious if that's worth talking through?",
            "Would it be worth a quick chat?",
        ]
    else:
        closes = [
            "Worth a quick call?",
            "Would it be worth a quick conversation?",
            "Curious if that's worth talking through?",
        ]

    return closes[variant % len(closes)]


def _subject_options_for_angle(angle: str, observation: str) -> List[str]:
    obs_lower = observation.lower()
    if angle == "after_hours_response":
        if "emergency" in obs_lower or "urgent" in obs_lower:
            return ["emergency calls", "after-hours calls", "after-hours follow-up"]
        if "weekend" in obs_lower or "nights" in obs_lower:
            return ["after-hours calls", "after-hours follow-up", "weekend calls"]
        return ["after-hours calls", "after-hours follow-up", "after-hours response"]
    if angle == "estimate_follow_up":
        if "quote" in obs_lower:
            return ["quote requests", "estimate follow-up", "quote follow-up"]
        return ["estimate follow-up", "estimate requests", "quote follow-up"]
    if angle == "service_requests":
        if "appointment" in obs_lower or "booking" in obs_lower:
            return ["appointment requests", "new bookings", "service requests"]
        if "scheduling" in obs_lower or "schedule" in obs_lower:
            return ["scheduling follow-up", "service requests", "new requests"]
        return ["service requests", "new requests", "service request follow-up"]
    if angle == "inquiry_routing":
        if "contact form" in obs_lower:
            return ["contact form follow-up", "form inquiries", "contact form inquiries"]
        if "text" in obs_lower or "chat" in obs_lower or "message" in obs_lower:
            return ["new messages", "incoming inquiries", "inquiry follow-up"]
        return ["new inquiries", "inquiry follow-up", "incoming inquiries"]
    if angle == "callback_recovery":
        if "voicemail" in obs_lower or "dispatch" in obs_lower:
            return ["missed calls", "voicemail follow-up", "callback follow-up"]
        return ["missed calls", "callback follow-up", "call follow-up"]
    if any(kw in obs_lower for kw in ("missed call", "callback", "voicemail", "phone")):
        return ["missed calls", "callback follow-up", "call follow-up"]
    if any(kw in obs_lower for kw in ("estimate", "quote", "proposal")):
        return ["estimate follow-up", "estimate requests", "quote follow-up"]
    if any(kw in obs_lower for kw in ("contact form", "inquiry", "message", "form")):
        return ["new inquiries", "inquiry follow-up", "contact follow-up"]
    return ["missed calls", "new inquiries", "follow-up timing"]


def _subject_from_observation(prospect: Dict[str, str], observation: str, angle: str) -> str:
    options = _subject_options_for_angle(angle, observation)
    pick = _component_variant_index(prospect, observation, angle, "subject", len(options))
    return options[pick]


def _build_first_touch_body(
    prospect: Dict[str, str],
    observation: str,
    *,
    channel: str,
) -> str:
    """
    Build the email body in Drew's voice: 4 short paragraphs, line-break separated.
    P1: My name is Drew. Saw [observation].
    P2: Consequence — hedged, specific to observation.
    P3: Offer — one on one, full picture, specific to their setup.
    P4: Real close question.
    """
    angle = _pick_offer_angle(prospect, observation)

    # Variant indices — deterministic per lead
    offer_v = _component_variant_index(prospect, observation, angle, "offer", 3, channel=channel)
    close_v = _component_variant_index(prospect, observation, angle, "close", 3, channel=channel)

    obs_sentence = _build_observation_opener(observation)
    consequence  = _build_consequence_sentence(observation, angle)
    offer        = _build_offer_sentence(observation, angle, offer_v)
    close        = _build_close_sentence(observation, angle, close_v, channel)

    if channel == "dm":
        p1 = f"Hey\n\nMy name is Drew. {obs_sentence}"
    else:
        p1 = f"My name is Drew. {obs_sentence}"

    return f"{p1}\n\n{consequence}\n\n{offer}\n\n{close}"


def _build_email_body(prospect: Dict[str, str], observation: str) -> str:
    return _build_first_touch_body(prospect, observation, channel="email")


def _build_dm_body(prospect: Dict[str, str], observation: str) -> str:
    return _build_first_touch_body(prospect, observation, channel="dm")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_SUBJECT_OPTIONS = ["quick question", "missed calls", "after-hours follow-up"]
_HIGH_FIT_INDUSTRIES = {
    "plumbing", "hvac", "electrical", "locksmith", "garage_door", "towing",
}


def draft_email(
    prospect: Dict[str, str],
    final_priority_score: int,
    observation: Optional[str] = None,
) -> Tuple[str, str]:
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
            "Observation is too generic. Write something specific to this business."
        )

    angle   = _pick_offer_angle(prospect, obs)
    subject = _subject_from_observation(prospect, obs, angle)
    body    = _build_email_body(prospect, obs)
    body    = enforce_human_style(body)
    full_body = body + _SIGN_OFF

    validate_subject(subject)
    validate_draft(full_body, obs)
    return subject, full_body


def draft_email_json(
    prospect: Dict[str, str],
    final_priority_score: int,
    observation: Optional[str] = None,
) -> Dict:
    subject, body = draft_email(prospect, final_priority_score, observation=observation)
    return {"subject": subject, "email_body": body, "tone": "casual"}


def draft_social_messages(
    prospect: Dict[str, str],
    email_body: str,
    observation: Optional[str] = None,
) -> Tuple[str, str, str]:
    raw_obs = observation or prospect.get("business_specific_observation") or ""
    obs = _require_observation(raw_obs)
    if _is_generic_observation(obs):
        raise ObservationMissingError("Observation is too generic for DM generation.")
    dm_body = _build_dm_body(prospect, obs)
    dm_body = enforce_human_style(dm_body)
    validate_draft(dm_body, obs)
    return dm_body, dm_body, dm_body


# ---------------------------------------------------------------------------
# Pipeline compatibility shims
# ---------------------------------------------------------------------------

def pick_best_pitch_angle(likely_opportunity: str) -> str:
    return (likely_opportunity or "booking automation").strip() or "booking automation"
