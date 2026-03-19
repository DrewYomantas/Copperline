from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Optional

import lead_memory as _lm


_MAX_OBSERVATION_CHARS = 170
_MAX_OBSERVATION_WORDS = 30

_BANNED_OBSERVATION_PHRASES = [
    "more leads",
    "more customers",
    "grow faster",
    "grow your business",
    "better marketing",
    "marketing",
    "automation",
    "automate",
    "ai",
    "agency",
    "lead gen",
    "lead generation",
    "book more",
    "book appointments",
    "capture more leads",
    "lead capture",
    "optimize",
    "streamline",
    "scale",
]

_WEAK_SOURCE_PHRASES = [
    "website signal scan was limited",
    "position outreach around",
    "lead capture reliability",
    "missed-call response speed",
]

_WORD_RE = re.compile(r"\b[a-z][a-z0-9_+-]*\b")


class ObservationValidationError(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


class ObservationCandidateBlockedError(ValueError):
    def __init__(
        self,
        reason: str,
        message: str,
        *,
        evidence: Optional[List[str]] = None,
        source_labels: Optional[List[str]] = None,
        confidence: str = "",
        family: str = "",
    ):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.evidence = evidence or []
        self.source_labels = source_labels or []
        self.confidence = confidence
        self.family = family


@dataclass
class _RouteContext:
    website: str
    phone: str
    email: str
    contact_form_url: str
    facebook_url: str
    instagram_url: str
    contactability: str
    insight_sentence: str
    insight_signals: List[str]

    @property
    def route_labels(self) -> List[str]:
        labels: List[str] = []
        if self.email:
            labels.append("email")
        if self.contact_form_url:
            labels.append("contact form")
        if self.facebook_url:
            labels.append("facebook")
        if self.instagram_url:
            labels.append("instagram")
        return labels

    @property
    def route_count(self) -> int:
        return len(self.route_labels)

    @property
    def has_phone_only_listing(self) -> bool:
        return bool(self.phone and not self.website and self.route_count == 0)


def validate_observation_text(text: str) -> dict:
    obs = (text or "").strip()
    grade = _lm.grade_observation(obs)
    if grade["grade"] == "empty":
        raise ObservationValidationError("observation_missing", "Observation required.")
    if grade["grade"] == "too_short":
        raise ObservationValidationError("observation_too_short", grade["message"])
    if grade["grade"] == "generic":
        raise ObservationValidationError("observation_generic", grade["message"])
    if len(obs) > _MAX_OBSERVATION_CHARS or len(obs.split()) > _MAX_OBSERVATION_WORDS:
        raise ObservationValidationError(
            "observation_too_long",
            "Observation is too long. Keep it short and grounded.",
        )
    lower = obs.lower()
    tokens = set(_WORD_RE.findall(lower))
    for phrase in _BANNED_OBSERVATION_PHRASES:
        phrase_lower = phrase.lower()
        if (" " in phrase_lower and phrase_lower in lower) or (" " not in phrase_lower and phrase_lower in tokens):
            raise ObservationValidationError(
                "observation_banned_language",
                f"Observation uses banned growth/agency language: '{phrase}'.",
            )
    return grade


def build_observation_candidate(
    row: Dict[str, str],
    *,
    memory_record: Optional[dict] = None,
    prospect_row: Optional[Dict[str, str]] = None,
) -> dict:
    mem_obs = ((memory_record or {}).get("current_observation") or "").strip()
    if mem_obs:
        grade = validate_observation_text(mem_obs)
        return {
            "candidate_text": mem_obs,
            "family": "prior_observation_restore",
            "confidence": "high",
            "grade": grade,
            "rationale": "Restored from saved lead memory for this same business.",
            "evidence": ["Lead memory already has a saved observation on file."],
            "source_labels": ["lead_memory"],
        }

    ctx = _build_route_context(row, prospect_row)
    evidence = _build_base_evidence(ctx, prospect_row)

    text = ""
    family = ""
    confidence = ""
    rationale = ""

    if "limited_contact_methods" in ctx.insight_signals and ctx.website and 1 <= ctx.route_count <= 2:
        text = _limited_contact_methods_candidate(ctx)
        family = "limited_contact_methods"
        confidence = "high" if ctx.route_count == 1 else "medium"
        rationale = "Built from the queue's limited-contact signal plus the contact routes already on file."
    elif ctx.website and ctx.route_count == 1 and ctx.contactability in {"website_contact_only", "email_found"}:
        text = _single_route_candidate(ctx)
        family = "single_contact_route"
        confidence = "medium"
        rationale = "Built from the matched contactability classification and the single contact route currently on file."
    elif ctx.has_phone_only_listing and ctx.contactability == "no_website":
        text = "not seeing a website tied in here - the contact path looks pretty phone-only right now."
        family = "phone_only_listing"
        confidence = "medium"
        rationale = "Built from the matched no-website contactability and the listing phone on file."
    else:
        reason = "weak_source_context" if _has_weak_source_only(ctx) else "insufficient_context"
        message = (
            "Only weak positioning guidance is on file for this lead. No safe observation candidate was generated."
            if reason == "weak_source_context"
            else "No safe observation candidate could be generated from the current lead evidence."
        )
        raise ObservationCandidateBlockedError(
            reason,
            message,
            evidence=evidence,
            source_labels=_source_labels(ctx, prospect_row),
        )

    grade = validate_observation_text(text)
    _validate_generated_overlap(text, ctx, family)
    return {
        "candidate_text": text,
        "family": family,
        "confidence": confidence,
        "grade": grade,
        "rationale": rationale,
        "evidence": evidence,
        "source_labels": _source_labels(ctx, prospect_row),
    }


def _build_route_context(row: Dict[str, str], prospect_row: Optional[Dict[str, str]]) -> _RouteContext:
    insight_sentence = (row.get("lead_insight_sentence") or "").strip()
    insight_signals = [
        part.strip().lower()
        for part in (row.get("lead_insight_signals") or "").split("|")
        if part.strip()
    ]
    prospect = prospect_row or {}
    return _RouteContext(
        website=(row.get("website") or prospect.get("website") or "").strip(),
        phone=(row.get("phone") or prospect.get("phone") or "").strip(),
        email=(row.get("to_email") or prospect.get("to_email") or "").strip(),
        contact_form_url=(row.get("contact_form_url") or prospect.get("contact_form_url") or "").strip(),
        facebook_url=(row.get("facebook_url") or prospect.get("facebook_url") or "").strip(),
        instagram_url=(row.get("instagram_url") or prospect.get("instagram_url") or "").strip(),
        contactability=(prospect.get("contactability") or "").strip().lower(),
        insight_sentence=insight_sentence,
        insight_signals=insight_signals,
    )


def _build_base_evidence(ctx: _RouteContext, prospect_row: Optional[Dict[str, str]]) -> List[str]:
    evidence: List[str] = []
    if ctx.insight_signals:
        evidence.append("Queue insight signals: " + ", ".join(ctx.insight_signals))
    if ctx.insight_sentence and not _has_weak_source_only(ctx):
        evidence.append("Queue insight: " + ctx.insight_sentence)
    if ctx.contactability:
        evidence.append("Matched prospect contactability: " + ctx.contactability)
    if ctx.route_labels:
        evidence.append("Contact routes on file: " + ", ".join(ctx.route_labels))
    if prospect_row and (prospect_row.get("website") or "").strip():
        evidence.append("Matched prospect row via stored lead identity.")
    return evidence


def _source_labels(ctx: _RouteContext, prospect_row: Optional[Dict[str, str]]) -> List[str]:
    labels: List[str] = []
    if ctx.insight_signals or (ctx.insight_sentence and not _has_weak_source_only(ctx)):
        labels.append("lead_insight")
    if prospect_row:
        labels.append("prospect_match")
    if ctx.route_labels:
        labels.append("contact_routes")
    return labels


def _has_weak_source_only(ctx: _RouteContext) -> bool:
    if not ctx.insight_sentence:
        return False
    lower = ctx.insight_sentence.lower()
    return any(phrase in lower for phrase in _WEAK_SOURCE_PHRASES)


def _limited_contact_methods_candidate(ctx: _RouteContext) -> str:
    if ctx.route_count == 1:
        return _single_route_candidate(ctx)
    return f"looks like the site mostly falls back to {_route_phrase(ctx.route_labels)} right now, without much else around it."


def _single_route_candidate(ctx: _RouteContext) -> str:
    route = ctx.route_labels[0]
    if route == "email":
        return "looks like the site mainly leans on the email address as the way in right now."
    if route == "contact form":
        return "looks like the site mainly leans on the contact form as the way in right now."
    if route == "facebook":
        return "looks like Facebook is doing most of the visible contact lifting here right now."
    if route == "instagram":
        return "looks like Instagram is doing most of the visible contact lifting here right now."
    return ""


def _route_phrase(route_labels: List[str]) -> str:
    if not route_labels:
        return "the visible contact path"
    if len(route_labels) == 1:
        return route_labels[0]
    return ", ".join(route_labels[:-1]) + " and " + route_labels[-1]


def _validate_generated_overlap(text: str, ctx: _RouteContext, family: str) -> None:
    lower = text.lower()
    required_terms: List[str] = []
    if family in {"limited_contact_methods", "single_contact_route"}:
        required_terms.extend(["site", "contact", "facebook", "instagram", "email", "form"])
        required_terms.extend(ctx.route_labels)
    if family == "phone_only_listing":
        required_terms.extend(["website", "phone"])
    if required_terms and not any(term in lower for term in required_terms):
        raise ObservationCandidateBlockedError(
            "invalid_missing_context_overlap",
            "Generated candidate did not stay close enough to the evidence on file.",
            evidence=_build_base_evidence(ctx, None),
            source_labels=["generated_candidate"],
            family=family,
        )
