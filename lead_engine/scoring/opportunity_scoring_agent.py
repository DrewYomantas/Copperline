from __future__ import annotations

from typing import Dict, Tuple


def score_opportunity(prospect: Dict[str, str], website_scan: Dict[str, object]) -> Tuple[int, str]:
    """Return 1-5 priority score and concise reason from deterministic website signals."""
    website = (prospect.get("website") or "").strip()
    if not website:
        return 5, "No website found; high automation opportunity."

    reachable = bool(website_scan.get("website_reachable", False))
    weak_signals = website_scan.get("weak_website_signals", []) or []
    positive_signals = website_scan.get("positive_conversion_signals", []) or []

    if not reachable:
        return 4, "Website unreachable; limited conversion path visible."

    score = 3
    reasons = []

    if not website_scan.get("has_online_booking_keywords", False):
        score += 1
        reasons.append("no booking flow")
    if not website_scan.get("has_request_quote_cta", False):
        score += 1
        reasons.append("no quote cta")
    if not website_scan.get("has_chat_widget", False):
        score += 1
        reasons.append("no chat")

    if weak_signals:
        score += 1
        reasons.append(f"{len(weak_signals)} weak-site clues")

    if website_scan.get("has_contact_form", False):
        score -= 1
    if len(positive_signals) >= 3:
        score -= 1
        reasons.append("some conversion basics in place")

    final_score = max(1, min(5, score))
    if not reasons:
        reasons.append("balanced baseline signals")

    return final_score, "; ".join(reasons[:3])
