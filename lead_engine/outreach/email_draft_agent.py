from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

DRAFT_VERSION = "v16"

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
]

_SUBJECT_BANNED_PHRASES = [
    "ai", "automation", "automate", "solution", "opportunity", "support",
    "checking in", "increase revenue", "grow your business", "urgent",
    "last chance", "free audit", "free consultation",
]

_VAGUE_POSITIONING_PHRASES = [
    "workflow gap", "from the business side", "not the agency side",
    "another set of eyes", "operational stuff", "compare notes sometime",
    "worth comparing notes", "site is pretty explicit about", "the mess shows up",
    "if that is a live issue there", "where i'd start", "what i'd look at first",
    "first place i'd look",
]

_FORMAL_OPENER_SUBS = [
    ("I noticed that ", ""), ("I wanted to reach out ", ""), ("I wanted to reach out", ""),
    ("my name is", ""), ("We are a leading", ""), ("we are a leading", ""),
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

_CONCRETE_SERVICE_SIGNALS = [
    "missed-call text back", "text-back", "missed calls",
    "after-hours response", "after-hours reply", "after-hours calls",
    "lead tracking", "contact form routing", "inquiry routing",
    "estimate follow-up", "quote follow-up", "callback recovery",
    "intake capture", "pipeline", "calls", "callbacks", "estimate requests",
    "quotes", "follow-up", "slow follow-up", "inquiries", "new leads",
    "new requests", "service requests", "getting back to people",
    "response side", "sit", "stack up", "pile up", "slip", "fall through",
    "text that goes out", "quick reply", "quick follow-up", "response path",
    "text back", "fires when", "consistent response", "know it landed",
    "know you got it", "know it's coming",
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
            "First-touch draft blocked: business_specific_observation is required."
        )
    if len(obs) < 15:
        raise ObservationMissingError(
            "Observation too short. Write a specific detail about this business."
        )
    return obs


def _is_generic_observation(obs: str) -> bool:
    return any(phrase in obs.lower() for phrase in _GENERIC_OBSERVATION_PHRASES)


def validate_draft(body: str, observation: str) -> None:
    body_lower = body.lower()

    hits = [w for w in _BANNED_WORDS if w in body_lower]
    if hits:
        raise DraftInvalidError(f"Banned word(s) in draft: {hits}")

    filler_openers = [
        "i wanted to reach out", "my name is", "we are a leading",
        "we help businesses like yours", "i help businesses like",
    ]
    for filler in filler_openers:
        if body_lower.startswith(filler):
            raise DraftInvalidError(f"Draft opens with sender-centered filler: '{filler}'")

    vague_hits = [p for p in _VAGUE_POSITIONING_PHRASES if p in body_lower]
    if vague_hits:
        raise DraftInvalidError(f"Vague positioning found in draft: {vague_hits}")

    hard_cta = [
        "schedule a call", "book a call", "book a meeting",
        "let's hop on", "hop on a call", "set up a call",
        "click here", "visit our website", "check out our",
    ]
    for cta in hard_cta:
        if cta in body_lower:
            raise DraftInvalidError(f"Hard CTA found: '{cta}'")

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
    if not (obs_tokens & body_tokens):
        raise DraftInvalidError(
            "Draft does not materially reflect the observation."
        )

    if not any(s in body_lower for s in _CONCRETE_SERVICE_SIGNALS):
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
    hits = [p for p in _SUBJECT_BANNED_PHRASES if p in subj]
    if hits:
        raise DraftInvalidError(f"Banned phrase(s) in subject: {hits}")


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

_WORD_TARGET_MAX = 90
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
        body_text = trimmed[:last_punct + 1] if last_punct > 0 else trimmed
    body_text = body_text.rstrip(" ,;-")
    if body_text and body_text[-1] not in ".?!":
        body_text += "."
    return body_text


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


def _normalize_observation_sentence(observation: str) -> str:
    obs = observation.strip().rstrip(".")
    obs = re.sub(
        r"^(saw|noticed|looks like|came across|saw that|noticed that)\s+",
        "", obs, flags=re.IGNORECASE,
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
        ("they are ", "you're "), ("they're ", "you're "), ("their ", "your "),
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
        if any(kw in obs_lower for kw in keywords):
            return angle
    likely = (prospect.get("likely_opportunity") or "").lower()
    if "after" in likely or "missed" in likely or "call" in likely:
        return "callback_recovery"
    if "estimate" in likely or "quote" in likely or "follow" in likely:
        return "estimate_follow_up"
    return "owner_workflow"


def _build_reactive_consequence(obs: str, angle: str) -> str:
    """
    Consequence sentence derived from the specific observation.
    Priority-ordered signal matching. Falls back to short angle sentence.
    """
    o = obs.lower()

    if any(p in o for p in (
        "no confirmation", "no immediate confirmation", "no response",
        "nothing back", "no follow", "unclear", "no next step",
        "no acknowledgment",
    )):
        if any(p in o for p in ("contact form", "form", "submit", "inquiry")):
            return "someone fills that out and gets nothing back — no confirmation, no idea if it went anywhere"
        return "when there's no confirmation after someone reaches out, a lot of those just slip through"

    if any(p in o for p in ("voicemail", "dispatch number", "dispatch line")):
        return "requests that go to voicemail often don't get followed up until the next morning at the earliest"

    if any(p in o for p in (
        "only contact", "primary contact", "only way to reach",
        "no other contact", "just a phone", "single phone",
        "phone number prominently", "phone is the main",
    )):
        return "if someone calls and you're mid-job, that goes to voicemail and may not get returned same day"

    if any(p in o for p in (
        "estimate request form", "quote request form", "estimate form",
        "request form as the primary", "free estimate as the primary",
        "free quote as the primary", "primary call to action",
    )):
        return "the gap is usually after someone submits — those tend to sit until someone has time to get back to them"

    if any(p in o for p in (
        "push free quote", "pushes free quote", "quote on every page",
        "quote button", "quote requests on every",
    )):
        return "quote requests tend to sit until someone gets around to following up, especially once the schedule fills"

    if any(p in o for p in ("24/7", "24 7", "emergency service", "same-day response", "same day response")):
        return "that works when someone picks up, but after-hours calls and same-day requests can stack up between jobs"

    if any(p in o for p in (
        "after-hours", "after hours", "weekend availability",
        "weekend and evening", "nights and weekend", "nights and week",
    )):
        return "nights and weekends are when people actually need help, and that's also when follow-up tends to slip"

    if any(p in o for p in (
        "chat widget", "text-back", "text back",
        "couple different places", "few different places",
        "multiple contact", "more than one way",
    )):
        return "the tricky part is staying on top of messages coming from a couple different places at the same time"

    if any(p in o for p in ("online booking", "booking widget", "scheduling widget", "book online")):
        return "the booking side is covered, but requests that come in outside the widget tend to sit"

    if any(p in o for p in ("proposal request", "proposal form", "free in-home")):
        return "the gap is usually after someone requests — those tend to sit until someone circles back"

    fallbacks = {
        "after_hours_response":  "after-hours calls and follow-up tend to slip once the day gets busy",
        "estimate_follow_up":    "estimate requests tend to sit longer than they should once the schedule fills up",
        "service_requests":      "new requests pile up faster than it looks, especially once the schedule is full",
        "inquiry_routing":       "inquiries coming in from different places tend to get missed or handled late",
        "callback_recovery":     "a lot of those calls don't get returned until the next opening in the schedule",
        "owner_workflow":        "calls and requests tend to sit longer than they should once the job load picks up",
    }
    return fallbacks.get(angle, fallbacks["owner_workflow"])


def _build_reactive_offer(obs: str, angle: str) -> str:
    """
    Offer sentence that names the practical fix implied by the specific observation.
    Reads like a person who already thought about this one business, not a service pitch.
    Falls back to a short plain angle sentence when no specific signal found.
    """
    o = obs.lower()

    # No confirmation after form submission
    if any(p in o for p in (
        "no confirmation", "no immediate confirmation", "nothing back",
        "no next step", "no acknowledgment",
    )) and any(p in o for p in ("form", "submit", "inquiry", "contact")):
        return "pretty easy fix on the response side — usually just a quick reply that goes out the moment someone submits, so they know it landed and what to expect next"

    # Phone-only / no other contact path
    if any(p in o for p in (
        "only contact", "primary contact", "no other contact",
        "just a phone", "single phone", "phone number prominently", "phone is the main",
    )):
        return "the fix is usually just a text that goes out when a call gets missed, so people know you saw it and are getting back to them"

    # Voicemail / dispatch
    if any(p in o for p in ("voicemail", "dispatch number", "dispatch line")):
        return "the fix is usually just a text that fires when a call goes to voicemail, so people know you got it and aren't calling around"

    # 24/7 or emergency
    if any(p in o for p in ("24/7", "24 7", "emergency service", "same-day response", "same day response")):
        return "usually just needs a text back when a call or request comes in after hours, so people know you got it and aren't left waiting"

    # After-hours / weekend
    if any(p in o for p in (
        "after-hours", "after hours", "weekend availability",
        "weekend and evening", "nights and weekend",
    )):
        return "usually just needs a text that goes out when a call or message comes in after hours, so people know you got it and aren't left wondering"

    # Estimate form as primary CTA
    if any(p in o for p in (
        "estimate request form", "estimate form", "request form as the primary",
        "free estimate as the primary", "primary call to action",
    )):
        return "the fix is usually a quick follow-up that goes out as soon as someone submits — acknowledges the request and gives them a rough timeline so they don't go looking elsewhere"

    # Quote buttons / every page
    if any(p in o for p in (
        "push free quote", "pushes free quote", "quote on every page", "quote button",
    )):
        return "usually just needs a quick acknowledgment after someone requests, so they know it's coming and don't reach out to three other companies in the meantime"

    # Proposal / free in-home
    if any(p in o for p in ("proposal request", "proposal form", "free in-home")):
        return "the fix is usually a quick reply after someone requests, giving them a timeline and a next step so the lead doesn't go cold"

    # Chat widget / text-back / multiple channels
    if any(p in o for p in (
        "chat widget", "text-back", "text back",
        "couple different places", "few different places",
    )):
        return "usually just needs one consistent response path so messages from different places don't fall through — doesn't have to be complicated"

    # Online booking widget
    if any(p in o for p in ("online booking", "booking widget", "scheduling widget", "book online")):
        return "usually just needs a quick follow-up for requests that come in outside the booking tool — phone, form, walk-in — so nothing sits"

    # Scheduling link
    if any(p in o for p in ("scheduling link", "pick a service window", "pick a time")):
        return "usually just needs a quick reply when someone uses the scheduling link, so they know what to expect before the window arrives"

    # Angle fallbacks — short, plain, no template opener
    fallbacks = {
        "after_hours_response":
            "usually just needs a text back when after-hours calls come in, so people know you got it",
        "estimate_follow_up":
            "usually just a quick acknowledgment after someone requests, so the lead doesn't go cold while you're finishing a job",
        "service_requests":
            "usually just needs a quick reply when new requests come in, so they don't sit until someone happens to check",
        "inquiry_routing":
            "usually just needs one consistent path for inquiries so nothing gets missed when things get busy",
        "callback_recovery":
            "usually just a text when a call gets missed, so people know you're getting back to them",
        "owner_workflow":
            "usually just needs a quick reply path so new requests don't depend on someone remembering to follow up",
    }
    return fallbacks.get(angle, fallbacks["owner_workflow"])


def _build_reactive_close(obs: str, angle: str, channel: str) -> str:
    """
    Closing sentence that gives the owner a specific reason to reply
    rather than a generic permission phrase. Soft ask, no hard CTA.
    References something from the observation where possible.
    """
    o = obs.lower()
    is_dm = channel == "dm"

    # Form / no confirmation
    if any(p in o for p in ("form", "submit", "inquiry", "contact form")) and \
       any(p in o for p in ("no confirmation", "unclear", "nothing back", "no next step", "primary")):
        return "happy to walk through how that'd work for your setup if it's useful"

    # Phone-only
    if any(p in o for p in ("only contact", "no other contact", "just a phone", "single phone", "phone number prominently")):
        return "if that's worth a look, happy to show you how it works for setups like yours"

    # Voicemail / dispatch
    if any(p in o for p in ("voicemail", "dispatch number", "dispatch line")):
        return "happy to walk through what that looks like for a dispatch setup if useful"

    # Emergency / 24-7
    if any(p in o for p in ("24/7", "24 7", "emergency service", "same-day response")):
        return "happy to walk through what that looks like for an emergency-response operation if useful"

    # After-hours / weekend
    if any(p in o for p in ("after-hours", "after hours", "weekend availability", "weekend and evening", "nights")):
        return "happy to walk through how that works for a shop running nights and weekends if useful"

    # Estimate form
    if any(p in o for p in ("estimate request form", "estimate form", "primary call to action", "free estimate")):
        return "if that's worth a look, happy to walk through how it'd work for your setup"

    # Quote buttons
    if any(p in o for p in ("push free quote", "quote on every page", "quote button")):
        return "happy to show you what that follow-up looks like if it's useful"

    # Chat / text-back / multi-channel
    if any(p in o for p in ("chat widget", "text-back", "text back", "few different places", "couple different")):
        return "happy to show you how that'd work alongside what you've already got set up"

    # Online booking
    if any(p in o for p in ("online booking", "booking widget", "scheduling widget")):
        if "dental" in o or "medical" in o or "clinic" in o or "practice" in o:
            return "happy to walk through what that looks like for your practice if useful"
        return "happy to walk through what that looks like for your setup if useful"

    # Generic soft closes varied by channel
    if is_dm:
        return "happy to share a couple ideas based on what i saw if useful"
    return "happy to share a few ideas specific to your setup if useful"


def _subject_options_for_angle(angle: str, observation: str) -> List[str]:
    obs_lower = observation.lower()
    if angle == "after_hours_response":
        if "emergency" in obs_lower or "urgent" in obs_lower:
            return ["emergency calls", "after-hours calls", "after-hours follow-up"]
        if "weekend" in obs_lower or "nights" in obs_lower:
            return ["after-hours calls", "after-hours follow-up", "weekend calls"]
        return ["after-hours calls", "after-hours follow-up", "after-hours response"]
    if angle == "estimate_follow_up":
        if "quote" in obs_lower or "quotes" in obs_lower:
            return ["quote requests", "estimate follow-up", "quote follow-up"]
        return ["estimate follow-up", "estimate requests", "quote follow-up"]
    if angle == "service_requests":
        if "appointment" in obs_lower or "booking" in obs_lower:
            return ["appointment requests", "new bookings", "service requests"]
        if "scheduling" in obs_lower or "schedule" in obs_lower:
            return ["scheduling follow-up", "service requests", "new requests"]
        return ["service requests", "new requests", "service request follow-up"]
    if angle == "inquiry_routing":
        if "contact form" in obs_lower or "contact-form" in obs_lower:
            return ["contact form follow-up", "form inquiries", "contact form inquiries"]
        if "text" in obs_lower or "chat" in obs_lower or "message" in obs_lower:
            return ["new messages", "incoming inquiries", "inquiry follow-up"]
        return ["new inquiries", "inquiry follow-up", "incoming inquiries"]
    if angle == "callback_recovery":
        if "voicemail" in obs_lower or "dispatch" in obs_lower:
            return ["missed calls", "voicemail follow-up", "callback follow-up"]
        return ["missed calls", "callback follow-up", "call follow-up"]
    if any(kw in obs_lower for kw in ("missed call", "missed-call", "callback", "voicemail", "phone")):
        return ["missed calls", "callback follow-up", "call follow-up"]
    if any(kw in obs_lower for kw in ("estimate", "quote", "proposal")):
        return ["estimate follow-up", "estimate requests", "quote follow-up"]
    if any(kw in obs_lower for kw in ("contact form", "inquiry", "inquiries", "message", "form")):
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
    obs_norm = _normalize_observation_sentence(observation)
    angle = _pick_offer_angle(prospect, observation)

    # Expanded opener variety — not all starting with same verb
    if obs_norm.startswith("your site "):
        email_openers = [
            f"i noticed {obs_norm}.",
            f"came across your site — {obs_norm}.",
            f"was looking at your site and noticed {obs_norm}.",
        ]
        dm_openers = [
            f"hey — i noticed {obs_norm}.",
            f"hey — came across your page and noticed {obs_norm}.",
            f"hey — was looking at your site and noticed {obs_norm}.",
        ]
    else:
        email_openers = [
            f"i was checking out your site and noticed {obs_norm}.",
            f"came across your site — noticed {obs_norm}.",
            f"was looking at your site and noticed {obs_norm}.",
        ]
        dm_openers = [
            f"hey — was checking out your site and noticed {obs_norm}.",
            f"hey — came across your page and noticed {obs_norm}.",
            f"hey — noticed {obs_norm}.",
        ]

    opener_pool = email_openers if channel == "email" else dm_openers
    opener_pick = _component_variant_index(
        prospect, observation, angle, "opener", len(opener_pool), channel=channel,
    )
    opener_text = opener_pool[opener_pick]

    # All three body sentences now observation-reactive
    consequence = _build_reactive_consequence(observation, angle)
    offer      = _build_reactive_offer(observation, angle)
    close      = _build_reactive_close(observation, angle, channel)

    body = f"{opener_text} {consequence}. {offer}. {close}."
    if len(body.split()) <= _WORD_TARGET_MAX:
        return body

    # Fit fallback: shorten offer if needed (consequence and close preserved)
    offer_short = _build_reactive_offer.__doc__ and offer  # reuse; try trimming to first clause
    # Take text up to first em-dash or comma-clause as shorter form
    offer_trimmed = re.split(r" — | so they | so the | so nothing | doesn't have", offer)[0].rstrip(",;")
    body = f"{opener_text} {consequence}. {offer_trimmed}. {close}."
    if len(body.split()) <= _WORD_TARGET_MAX:
        return body

    # Final fallback: drop offer entirely, keep observation + consequence + close
    return f"{opener_text} {consequence}. {close}."


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
    """
    Generate a first-touch email draft.
    Requires observation. Raises ObservationMissingError if absent.
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
            "Observation is too generic. Write something specific to this business."
        )

    angle = _pick_offer_angle(prospect, obs)
    subject = _subject_from_observation(prospect, obs, angle)
    body_text = _build_email_body(prospect, obs)
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
    return {"subject": subject, "email_body": body, "tone": "casual"}


def draft_social_messages(
    prospect: Dict[str, str],
    email_body: str,
    observation: Optional[str] = None,
) -> Tuple[str, str, str]:
    """DM companion drafts. Requires observation."""
    raw_obs = observation or prospect.get("business_specific_observation") or ""
    obs = _require_observation(raw_obs)
    if _is_generic_observation(obs):
        raise ObservationMissingError(
            "Observation is too generic for DM generation."
        )
    dm_body = _build_dm_body(prospect, obs)
    dm_body = enforce_human_style(dm_body)
    validate_draft(dm_body, obs)
    return dm_body, dm_body, dm_body


# ---------------------------------------------------------------------------
# Pipeline compatibility shims
# ---------------------------------------------------------------------------

def pick_best_pitch_angle(likely_opportunity: str) -> str:
    return (likely_opportunity or "booking automation").strip() or "booking automation"
