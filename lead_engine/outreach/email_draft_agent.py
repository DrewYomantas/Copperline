from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

DRAFT_VERSION = "v18"

# ---------------------------------------------------------------------------
# Industry-keyed fallback drafts (no observation available)
# Written in Drew's voice — specific to the trade, not generic.
# ---------------------------------------------------------------------------

_INDUSTRY_FALLBACK_BODIES: Dict[str, List[str]] = {
    "plumbing": [
        "I work with a lot of plumbing shops and the thing that comes up almost every time is that the phone is the whole business — when it's covered, things run fine, but when it's not, jobs and callbacks just disappear.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
        "I've been working with service businesses on the gap between getting a call and actually closing the job. For most plumbing shops it's not a volume problem — it's a follow-through problem.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWould it be worth a quick conversation?",
    ],
    "hvac": [
        "I work with a lot of HVAC owners and the pattern I see most is that the busy season creates a backlog that never fully clears — and by the time things slow down, the leads from the peak are already gone somewhere else.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
        "I've been working with HVAC shops on the operational side — specifically the part where new calls come in while the crew is already stretched and things start slipping between the cracks.\n\nI work one on one with owners to look at the full picture and build something around how they actually operate.\n\nWould it be worth a quick conversation?",
    ],
    "electrical": [
        "I work with electrical contractors pretty regularly and the thing that comes up most is scheduling — jobs run long, new calls stack up, and by the time someone gets back to an estimate request it's usually too late.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
        "I've been working with electrical shops on the gap between incoming work and actual capacity. Most of the time it's not a sales problem — it's a coordination problem.\n\nI work one on one with owners to look at the full picture and build something around how they actually operate.\n\nWould it be worth a quick conversation?",
    ],
    "roofing": [
        "I work with roofing contractors and the pattern I see most is that storm season creates a volume problem that the follow-up process wasn't built for — estimates go out and nobody knows which ones are still live.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
        "I've been working with roofing shops on the estimate follow-up side — most are leaving jobs on the table not because the price is wrong but because the follow-up timing is.\n\nI work one on one with owners to look at the full picture and build something around how they actually operate.\n\nWould it be worth a quick conversation?",
    ],
    "towing": [
        "I work with towing companies and the thing I see most is that dispatch is the whole bottleneck — when it's tight, calls get missed or returned too late and the job goes to whoever picked up.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "auto": [
        "I work with auto shops and the thing that comes up almost every time is that the front desk is doing five things at once — and the calls that don't get answered during a busy afternoon usually don't come back.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "landscaping": [
        "I work with landscaping companies and the pattern I see most is that spring creates more demand than the process was built to handle — estimates pile up, follow-ups slip, and a lot of good jobs just don't close.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "painting": [
        "I work with painting contractors and the thing I see most is that the estimate side is solid but the follow-up isn't — most jobs that don't close are ones where no one circled back within a few days.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "cleaning": [
        "I work with cleaning businesses and the pattern I see most is that recurring clients are easy to keep but new ones are hard to convert because the inquiry process is slow.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "concrete": [
        "I work with concrete contractors and the thing I see most is that the estimate-to-job gap is long and most of that time is just waiting — and the jobs that go cold are usually the ones where nobody followed up in the first week.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "tree_service": [
        "I work with tree service companies and the pattern I see most is that storm work creates a volume spike the process wasn't built for — and a lot of good leads just disappear between the estimate and the call back.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "flooring": [
        "I work with flooring contractors and the thing I see most is that showroom visits don't always turn into jobs — usually because the follow-up after the estimate is inconsistent.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "appliance_repair": [
        "I work with appliance repair shops and the thing that comes up most is same-day calls — when the schedule is full and the phone still rings, those jobs usually just go to whoever can get there first.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "moving": [
        "I work with moving companies and the pattern I see most is that quote requests come in and the response time is what decides the job — not the price.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "pressure_washing": [
        "I work with pressure washing businesses and the thing I see most is that spring and summer create more demand than the scheduling process was built for — and a lot of jobs just go to whoever responds first.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "construction": [
        "I work with general contractors and the pattern I see most is that the estimate pipeline gets backed up when the crew is full — and by the time there's bandwidth to follow up, the homeowner has already moved on.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
    "pest_control": [
        "I work with pest control companies and the thing I see most is that the scheduling side works fine for recurring accounts but new calls get treated like walk-ins — and a lot of those just go cold.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    ],
}

# Generic fallback for any industry not specifically mapped
_GENERIC_FALLBACK_BODIES: List[str] = [
    "I work with service business owners pretty regularly and the thing that comes up most is that the operational side — keeping up with new work, following up on estimates, staying on top of incoming calls — is harder to manage than the work itself.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
    "I've been working with small business owners on the gap between the work they're doing and the work they could be closing. Most of the time it's not a marketing problem — it's a process problem.\n\nI work one on one with owners to look at the full picture and build something around how they actually operate.\n\nWould it be worth a quick conversation?",
    "I work with owners who are doing the work, running the business, and handling everything in between — and usually the thing that's hardest to stay on top of is the follow-up side.\n\nI work one on one with owners to look at the full operation and build something specific to how they run things.\n\nWorth a quick call to look at it together?",
]

_FALLBACK_SUBJECTS: List[str] = [
    "quick question",
    "had a question for you",
    "wanted to ask you something",
    "a question about your business",
    "quick question for you",
]


def _build_no_obs_draft(
    prospect: Dict[str, str],
    channel: str = "email",
) -> str:
    """
    Build a draft when no observation is available.
    Industry-specific, in Drew's voice, no generic filler.
    Feels like Drew knows the trade — just not this specific business yet.
    """
    industry = detect_industry(
        prospect.get("business_name", ""),
        prospect.get("industry", ""),
    )
    bodies = _INDUSTRY_FALLBACK_BODIES.get(industry, _GENERIC_FALLBACK_BODIES)
    # Deterministic variant pick
    name_hash = int(hashlib.md5(
        (prospect.get("business_name", "") + industry).encode()
    ).hexdigest(), 16)
    body = bodies[name_hash % len(bodies)]
    name = (prospect.get("business_name") or "").strip()
    city = (prospect.get("city") or "").strip()

    if channel == "dm":
        p1 = f"Hey{chr(10)}{chr(10)}My name is Drew."
    else:
        p1 = "My name is Drew."

    return f"{p1}\n\n{body}"



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
    Convert the stored observation into a clean grammatically correct sentence.
    Always produces: "I noticed [something specific about you/your business]."
    """
    import re as _re
    o = obs.strip().rstrip(".")

    # Run replacements BEFORE stripping opener prefixes, so "your site pushes"
    # gets converted to "you're pushing" while it's still intact
    replacements = [
        ("your site is very focused on ", "your site is very focused on "),
        ("your site is pretty explicit about ", "your site is very focused on "),
        ("your site is explicit about ", "your site is focused on "),
        ("your site focuses heavily on ", "you're focused heavily on "),
        ("your site lists ", "you're listing "),
        ("your site pushes ", "you're pushing "),
        ("your site advertises ", "you're advertising "),
        ("your site keeps ", "you keep "),
        ("your site splits ", "you split "),
        ("your site leans ", "you lean toward "),
        ("your site has ", "you have "),
        ("your homepage has ", "you have "),
        ("your homepage centers ", "you're centering "),
        ("site is pretty explicit about ", "your site is very focused on "),
        ("site is explicit about ", "your site is focused on "),
        ("site pushes ", "you're pushing "),
        ("site lists ", "you're listing "),
        ("site has ", "you have "),
        ("site advertises ", "you're advertising "),
    ]
    o_lower = o.lower()
    for old, new in replacements:
        if o_lower.startswith(old):
            o = new + o[len(old):]
            o_lower = o.lower()
            break

    # Now strip any explicit opener the operator or agent may have typed
    o = _re.sub(
        r"^(saw that\s*|noticed that\s*|i noticed\s*|i saw\s*|saw\s*|noticed\s*"
        r"|looks like\s*|came across\s*[-—]?\s*)",
        "", o, flags=_re.IGNORECASE,
    ).strip()

    # Ensure observations starting with a bare noun phrase get a natural lead-in
    # e.g. "estimate form is..." → "your estimate form is..."
    o_lower = o.lower()
    needs_your = (
        "estimate form", "contact form", "quote form", "request form",
        "booking widget", "chat widget", "scheduling widget", "website ",
        "homepage ", "main page ",
    )
    starts_with_noun_verb = any(o_lower.startswith(n) for n in needs_your)
    if starts_with_noun_verb and not o_lower.startswith("your ") and not o_lower.startswith("you"):
        o = "your " + o[0].lower() + o[1:]
        o_lower = o.lower()

    # Bare noun with no verb — add natural connector
    first_words = o_lower.split()[:4]
    has_early_verb = any(w in first_words for w in (
        "is", "are", "was", "were", "has", "have", "had",
        "does", "do", "did", "shows", "uses", "lists", "pushes",
        "advertises", "offers", "includes", "focuses", "keeps",
    ))
    if not has_early_verb:
        if any(o_lower.startswith(n) for n in ("dispatch number", "voicemail box", "voicemail only")):
            o = "you're relying on " + o[0].lower() + o[1:]
        elif any(o_lower.startswith(n) for n in ("phone number",)):
            o = "you have " + o[0].lower() + o[1:]

    # Ensure first character is lowercase for clean sentence assembly
    if o and o[0].isalpha():
        o = o[0].lower() + o[1:]

    return f"I noticed {o}."


def _build_consequence_sentence(obs: str, angle: str) -> str:
    """
    One direct sentence about what that specific detail probably means for their business.
    Specific, grounded, not vague. Avoids 'a lot of those probably' as a crutch.
    """
    o = obs.lower()

    if any(p in o for p in (
        "no confirmation", "no immediate", "nothing back",
        "no next step", "no acknowledgment", "unclear",
    )) and any(p in o for p in ("form", "submit", "contact", "inquiry")):
        return "When there's no confirmation after a form submission, most people assume it didn't go through and move on."

    if any(p in o for p in ("voicemail", "dispatch number", "dispatch line")):
        return "Most people who hit voicemail on a service call don't leave a message — they call the next number on the list."

    if any(p in o for p in (
        "only contact", "only way", "no other contact",
        "just a phone", "single phone", "phone is the main", "phone number prominently",
    )):
        return "If that number goes unanswered while you're on a job, that lead is usually gone before you can call back."

    if any(p in o for p in ("24/7", "24 7", "emergency service", "same-day response", "same day response")):
        return "That's a real commitment to back up operationally — most businesses that advertise it can't consistently deliver it."

    if any(p in o for p in ("after-hours", "after hours", "weekend", "nights")):
        return "After-hours requests that don't get a same-day response almost never convert — people make a decision and move on quickly."

    if any(p in o for p in (
        "estimate request form", "estimate form", "primary call to action",
        "free estimate", "quote request form", "free quote",
    )):
        return "Quote requests that sit for more than a few hours usually end up going to whoever responds first."

    if any(p in o for p in ("quote button", "quote on every page", "push free quote")):
        return "When there's a quote request and no fast follow-up, most people have already contacted someone else by the time you get back to them."

    if any(p in o for p in (
        "proposal request", "proposal form", "free in-home",
    )):
        return "Proposal requests that don't get a quick acknowledgment tend to go cold — people interpret silence as disinterest."

    if any(p in o for p in ("chat widget", "text-back", "text back", "few different places", "couple different")):
        return "When inquiries are coming in through multiple channels, it's easy for things to fall through between the cracks."

    if any(p in o for p in ("online booking", "booking widget", "scheduling widget")):
        return "Online bookings that don't get a quick confirmation call tend to generate no-shows — people aren't sure if it actually went through."

    if any(p in o for p in ("water heater", "financing", "explicit about")):
        return "Businesses that are very focused on one service sometimes have a harder time converting customers who want the full picture upfront."

    # Angle fallbacks — direct, not passive
    fallbacks = {
        "after_hours_response":
            "After-hours requests that don't get a fast response almost never convert.",
        "estimate_follow_up":
            "Slow estimate follow-up is usually the difference between winning and losing the job.",
        "service_requests":
            "New service requests that sit unacknowledged for more than a few hours rarely turn into customers.",
        "inquiry_routing":
            "Inquiries that fall through without a quick response are usually already talking to someone else.",
        "callback_recovery":
            "Missed calls that don't get a callback within the hour rarely convert.",
        "owner_workflow":
            "When the owner is also running operations, things that need attention tend to stack up faster than they get resolved.",
    }
    return fallbacks.get(angle, fallbacks["owner_workflow"])


def _build_offer_sentence(obs: str, angle: str, variant: int) -> str:
    """
    Drew's positioning: one on one, looks at the full picture,
    builds something specific to how they run things.
    Confident. No hedging. No product pitch.
    """
    variants = [
        "I work one on one with owners to look at the full operation and build something specific to how they run their business.",
        "I work one on one with owners to find where the gaps are and put something in place that actually fits how they work.",
        "I work one on one with owners to look at the whole picture and build a system around how they actually operate.",
    ]
    return variants[variant % len(variants)]


def _build_close_sentence(obs: str, angle: str, variant: int, channel: str) -> str:
    """
    Direct soft question. Not permission-seeking. Not vague.
    Drew closes with a real question that assumes the conversation is worth having.
    """
    o = obs.lower()

    if any(p in o for p in ("24/7", "emergency", "same-day", "same day")):
        closes = [
            "Would it be worth a quick call to talk through it?",
            "Worth getting on a call to look at it together?",
            "Want to get on a quick call and walk through how that's working?",
        ]
    elif channel == "dm":
        closes = [
            "Worth a quick conversation?",
            "Want to jump on a quick call about it?",
            "Would it be worth a short conversation?",
        ]
    else:
        closes = [
            "Worth a quick call to look at it together?",
            "Would it be worth getting on a call to walk through it?",
            "Want to get on a quick call and see if there's something worth addressing?",
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
    obs_clean = raw_obs.strip()

    # No observation — use industry-keyed fallback draft
    if not obs_clean or _is_generic_observation(obs_clean):
        industry = detect_industry(
            prospect.get("business_name", ""),
            prospect.get("industry", ""),
        )
        name_hash = int(hashlib.md5(
            (prospect.get("business_name", "") + industry).encode()
        ).hexdigest(), 16)
        subject = _FALLBACK_SUBJECTS[name_hash % len(_FALLBACK_SUBJECTS)]
        body    = _build_no_obs_draft(prospect, channel="email")
        body    = enforce_human_style(body) + _SIGN_OFF
        validate_subject(subject)
        return subject, body

    obs = _require_observation(obs_clean)
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
    obs_clean = raw_obs.strip()

    # No observation — use industry-keyed fallback
    if not obs_clean or _is_generic_observation(obs_clean):
        dm_body = _build_no_obs_draft(prospect, channel="dm")
        dm_body = enforce_human_style(dm_body)
        return dm_body, dm_body, dm_body

    obs = _require_observation(obs_clean)
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
