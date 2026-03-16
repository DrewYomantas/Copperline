from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional, Tuple

DRAFT_VERSION = "v2_signal_templates"

# ---------------------------------------------------------------------------
# Industry detection (unchanged — used by pipeline)
# ---------------------------------------------------------------------------

INDUSTRY_SIGNALS: List[Tuple[str, List[str]]] = [
    ("plumbing",     ["plumb", "sewer", "drain", "pipe", "rooter", "septic"]),
    ("hvac",         ["hvac", "heating", "cooling", "air condition", "furnace", "refrigerat"]),
    ("electrical",   ["electric", "wiring", "electrician", "panel", "generator"]),
    ("roofing",      ["roof", "gutter", "siding", "shingle"]),
    ("landscaping",  ["landscap", "lawn", "garden", "tree", "mow", "sod"]),
    ("pest_control", ["pest", "exterminator", "termite", "rodent", "bug"]),
    ("dental",       ["dental", "dentist", "orthodont", "oral"]),
    ("medical",      ["medical", "clinic", "doctor", "physician", "urgent care", "chiro"]),
    ("legal",        ["law", "attorney", "lawyer", "legal", "firm"]),
    ("real_estate",  ["real estate", "realty", "realtor", "property management"]),
    ("restaurant",   ["restaurant", "diner", "cafe", "catering", "bistro", "eatery", "pizza", "grill"]),
    ("auto",         ["auto", "mechanic", "car repair", "tire", "collision", "body shop"]),
    ("cleaning",     ["cleaning", "janitorial", "maid", "housekeeping", "pressure wash"]),
    ("construction", ["construction", "contractor", "remodel", "renovation", "carpent", "mason"]),
    ("insurance",    ["insurance", "insur", "agency", "broker"]),
    ("accounting",   ["account", "bookkeep", "tax", "cpa", "payroll"]),
    ("salon",        ["salon", "barber", "hair", "nail", "spa", "beauty"]),
    ("gym",          ["gym", "fitness", "personal train", "yoga", "pilates"]),
    ("moving",       ["moving", "mover", "storage", "relocation"]),
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
# Signal-aware email templates (automation_opportunity driven)
# ---------------------------------------------------------------------------
# Each opportunity maps to 3 variants (selected deterministically by name hash).
# Keys: subject, body  — body is under 70 words, one paragraph, casual tone.
# Banned words: optimize, revolutionize, leverage, synergy, streamline,
#               game-changer, cutting-edge, robust, scalable, seamlessly.
# ---------------------------------------------------------------------------

# (subject, body) tuples — 3 variants per opportunity
# Tone: one person talking to one person. No brand voice. No product language.
# Model: "I noticed you're manually doing X, I can automate that."
_TEMPLATES: Dict[str, List[Tuple[str, str]]] = {

    "missed_after_hours": [
        (
            "after-hours calls?",
            "Hey {name} - quick question. "
            "When someone calls after hours and you're not there, what happens to that lead? "
            "Most {industry} businesses in {city} lose those jobs without ever knowing. "
            "I built a simple fix that texts callers back instantly so you capture them before they call someone else. "
            "Worth a quick look?",
        ),
        (
            "missed calls?",
            "Hi {name} - noticed your number is on the site. "
            "Quick one - what happens when someone calls at 9pm and gets voicemail? "
            "For most {industry} shops that's a lost job. "
            "I set up an auto-response that captures those leads automatically. "
            "15 minutes to show you if you're curious.",
        ),
        (
            "quick question",
            "Hey {name} - do calls after hours ever go unanswered? "
            "It's the number one way {industry} businesses in {city} lose work they never knew they had. "
            "I built a text-back system that captures those leads automatically - takes about a week to set up. "
            "Want me to show you how it works?",
        ),
    ],

    "no_chat": [
        (
            "website question",
            "Hey {name} - I was on your site and noticed you have a contact form but no chat. "
            "Most people won't fill out a form on a first visit - they just leave. "
            "A simple chat catches them before they go. "
            "I set these up for {industry} businesses in {city} in about a week. "
            "Worth a 15-minute call?",
        ),
        (
            "quick thought",
            "Hi {name} - looked at your site. "
            "You're probably losing visitors who have a question but won't fill out a form. "
            "A lightweight chat fixes that without anyone having to sit at a screen all day. "
            "I've set this up for a few {industry} businesses in {city} - happy to show you what it looks like.",
        ),
        (
            "losing website leads?",
            "Hey {name} - noticed your site has a form but no way for visitors to ask a quick question. "
            "That's a lot of people bouncing who were ready to reach out. "
            "I help {industry} shops in {city} add a simple chat that catches those leads automatically. "
            "Interested?",
        ),
    ],

    "no_booking": [
        (
            "still taking bookings by phone?",
            "Hey {name} - do customers still have to call to schedule with you? "
            "A lot of {industry} businesses in {city} lose the people who want to book at 10pm and won't wait until morning. "
            "I set up simple online booking - works around the clock, takes about a week. "
            "Want to see how other local shops are using it?",
        ),
        (
            "quick question",
            "Hi {name} - if someone visits your site at midnight ready to schedule, can they? "
            "Most {industry} shops in {city} still rely on phone calls for booking, which means they miss the late decisions. "
            "I set up lightweight online booking in about a week, flat fee. "
            "Curious if that's something on your radar?",
        ),
        (
            "losing late bookings?",
            "Hey {name} - one pattern I see a lot with {industry} businesses: "
            "customers want to book after hours but won't call. They just move on. "
            "Online booking running 24/7 catches those jobs. "
            "Takes less than a week to set up - is that worth a quick call?",
        ),
    ],

    "unknown": [
        (
            "quick question",
            "Hey {name} - I help {industry} businesses in {city} automate the repetitive stuff - "
            "missed calls, follow-ups, scheduling. "
            "The kind of admin work that takes up time but doesn't need a human. "
            "Not a big pitch - just wondering if any of that sounds familiar. "
            "Worth a 15-minute call?",
        ),
        (
            "automation idea",
            "Hi {name} - I noticed {industry} businesses in {city} often handle "
            "scheduling and follow-ups manually. "
            "I can automate that - flat fee, set up in about a week. "
            "Happy to send a quick example if it's useful.",
        ),
        (
            "saving time on admin?",
            "Hey {name} - quick one. "
            "I work with {industry} shops in {city} on one specific thing: "
            "cutting out the manual back-and-forth that eats their day. "
            "Follow-ups, missed calls, booking - all automatable. "
            "Want to see what that looks like for a business like yours?",
        ),
    ],
}


# ---------------------------------------------------------------------------
# Core draft function
# ---------------------------------------------------------------------------

_BANNED = [
    "optimize", "revolutionize", "leverage", "synergy", "streamline",
    "game-changer", "game changer", "cutting-edge", "cutting edge",
    "robust", "scalable", "seamlessly", "seamless",
]

_WORD_LIMIT = 70


def _variant(business_name: str, n: int = 3) -> int:
    digest = hashlib.sha256(business_name.strip().lower().encode()).hexdigest()
    return int(digest[:8], 16) % n


_SIGN_OFF = "\n\nBest,\nDrew"


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
    Generate a signal-aware cold email under 70 words.

    Returns (subject, body) strings — pipeline-compatible.
    Also internally produces the JSON payload logged below.
    """
    business_name = (prospect.get("business_name") or "").strip()
    city          = (prospect.get("city") or "").strip()

    if not business_name:
        raise ValueError("Cannot draft email without business_name.")
    if not city:
        raise ValueError(f"Cannot draft email for {business_name} without city.")

    industry     = detect_industry(business_name, prospect.get("industry", ""))
    opportunity  = (prospect.get("automation_opportunity") or "unknown").strip().lower()

    # Fallback to "unknown" if key not in templates
    if opportunity not in _TEMPLATES:
        opportunity = "unknown"

    variants     = _TEMPLATES[opportunity]
    idx          = _variant(business_name, len(variants))
    subject_tmpl, body_tmpl = variants[idx]

    subject = _fill(subject_tmpl, business_name, city, industry)
    body_text = _fill(body_tmpl, business_name, city, industry)

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
