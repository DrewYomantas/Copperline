from __future__ import annotations

from typing import Dict, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Target industries for After-Hours Lead Capture
# High-fit: phone-first, emergency-capable trades
# ---------------------------------------------------------------------------
_HIGH_FIT_INDUSTRIES = {
    "plumbing", "hvac", "electrical", "locksmith",
    "garage_door", "garage door", "towing",
}

# Signals in business name or industry tag that indicate strong fit
_EMERGENCY_SIGNALS = [
    "24/7", "24 hour", "emergency", "same day", "same-day",
    "urgent", "after hours", "after-hours", "anytime",
    "night", "weekend", "on-call", "on call",
]

# Industries to deprioritize — not a fit for missed call text-back
_LOW_FIT_INDUSTRIES = {
    "restaurant", "salon", "gym", "dental", "medical",
    "real_estate", "legal", "accounting", "insurance",
    "retail", "moving", "landscaping",
}

# ---------------------------------------------------------------------------
# Known large chains — scored down as low-opportunity targets
# ---------------------------------------------------------------------------
_KNOWN_CHAINS = {
    "mcdonald's", "mcdonalds", "subway", "starbucks", "dunkin", "dunkin donuts",
    "burger king", "wendy's", "wendys", "taco bell", "chick-fil-a", "chickfila",
    "domino's", "dominoes", "pizza hut", "little caesars",
    "jiffy lube", "midas", "meineke", "firestone", "pep boys",
    "anytime fitness", "planet fitness", "la fitness",
    "h&r block", "hr block", "jackson hewitt",
    "great clips", "sport clips", "supercuts",
    "servpro", "servicemaster", "molly maid",
}


# ---------------------------------------------------------------------------
# Score → human label
# ---------------------------------------------------------------------------
_LABELS: Dict[int, str] = {
    5: "High Opportunity",
    4: "Good Fit",
    3: "Possible",
    2: "Weak",
    1: "Skip",
}


def _website_reachable(url: str, timeout: int = 5) -> bool:
    """HEAD request; falls back to GET. Never raises."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": "LeadBot/1.0"})
        with urlopen(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        pass
    try:
        req = Request(url, headers={"User-Agent": "LeadBot/1.0"})
        with urlopen(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False


def _has_emergency_signal(prospect: Dict[str, str]) -> bool:
    """Return True if the business name or scan notes mention emergency/urgency signals."""
    haystack = " ".join([
        (prospect.get("business_name") or ""),
        (prospect.get("scan_notes") or ""),
        (prospect.get("likely_opportunity") or ""),
    ]).lower()
    return any(sig in haystack for sig in _EMERGENCY_SIGNALS)


def _industry_fit(industry: str) -> str:
    """Return 'high', 'low', or 'neutral' for the given industry tag."""
    ind = (industry or "").strip().lower().replace(" ", "_")
    if ind in _HIGH_FIT_INDUSTRIES:
        return "high"
    if ind in _LOW_FIT_INDUSTRIES:
        return "low"
    return "neutral"


def score_opportunity(
    prospect: Dict[str, str],
    website_scan: Dict[str, object],
) -> Tuple[int, str]:
    """
    Deterministic 1-5 lead score for After-Hours Lead Capture targeting.

    Scoring model
    -------------
    Start at 0, then apply positive signals:
      +3  automation_opportunity == "missed_after_hours"  ← strongest signal
      +2  high-fit industry (plumbing, HVAC, electrical, locksmith, garage door, towing)
      +1  emergency/urgency language in name or notes (24/7, same-day, emergency, etc.)
      +1  website present
      +1  email present

    Contactability signals:
      +1  contactability == "email_found"           (confirms direct outreach path)
       0  contactability == "website_contact_only"  (neutral — contact page likely exists)
      -1  contactability == "no_website"            (phone-only, harder to reach)
      -1  contactability == "website_unreachable"   (URL present but dead)
      -2  contactability == "directory_or_ambiguous" (not a real independent business site)

    Other negative signals:
      -2  low-fit industry (restaurant, salon, dental, gym, retail, etc.)
      -1  known chain or franchise

    Max raw score: 9  →  clamped to [1, 5].
    """
    reasons: list[str] = []
    score = 0

    website         = (prospect.get("website") or "").strip()
    email           = (prospect.get("to_email") or "").strip()
    industry        = (prospect.get("industry") or "").strip()
    opportunity     = (prospect.get("automation_opportunity") or "").strip().lower()
    name_lc         = (prospect.get("business_name") or "").strip().lower()
    contactability  = (prospect.get("contactability") or "").strip().lower()

    # --- missed_after_hours: strongest single signal (+3) ---
    if opportunity == "missed_after_hours":
        score += 3
        reasons.append("missed_after_hours signal (+3)")

    # --- industry fit ---
    fit = _industry_fit(industry)
    if fit == "high":
        score += 2
        reasons.append(f"high-fit industry ({industry}) (+2)")
    elif fit == "low":
        score -= 2
        reasons.append(f"low-fit industry ({industry}) (-2)")

    # --- emergency / urgency language ---
    if _has_emergency_signal(prospect):
        score += 1
        reasons.append("emergency/urgency language (+1)")

    # --- contact reachability ---
    if website:
        score += 1
        reasons.append("has website (+1)")
    if email:
        score += 1
        reasons.append("has email (+1)")

    # --- contactability classification ---
    if contactability == "email_found":
        score += 1
        reasons.append("email_found contactability (+1)")
    elif contactability == "directory_or_ambiguous":
        score -= 2
        reasons.append("directory_or_ambiguous contactability (-2)")
    elif contactability in ("no_website", "website_unreachable"):
        score -= 1
        reasons.append(f"{contactability} contactability (-1)")
    # website_contact_only → no adjustment (neutral)

    # --- chain penalty ---
    is_chain = any(chain in name_lc for chain in _KNOWN_CHAINS)
    if is_chain:
        score -= 1
        reasons.append("known chain (-1)")

    final_score = max(1, min(5, score))
    label = _LABELS[final_score]
    reason_str = "; ".join(reasons) if reasons else "no signals"

    return final_score, f"{label} — {reason_str}"


def score_label(score: int) -> str:
    """Return the human-readable label for a numeric score."""
    return _LABELS.get(max(1, min(5, score)), "Unknown")



def compute_numeric_score(prospect: Dict[str, str]) -> int:
    """Compatibility helper: return deterministic 0-100 opportunity score."""
    score5, _ = score_opportunity(prospect, {})
    # map 1..5 to 20..100
    return int(score5 * 20)


def score_priority_label(numeric_score: int) -> str:
    """Compatibility helper for UI chips based on 0-100 score."""
    try:
        s = int(numeric_score)
    except (TypeError, ValueError):
        s = 0
    if s >= 80:
        return "High"
    if s >= 50:
        return "Medium"
    return "Low"
