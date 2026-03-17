"""
Autonomous Prospect Discovery Agent
Uses Google Places API to find real local businesses with contact info.
No manual URL entry required.

Setup (one time):
  Set environment variable GOOGLE_PLACES_API_KEY=your_key
  Get a free key at: https://console.cloud.google.com
  Enable: Places API (New)  — free tier covers ~500 searches/month

Usage:
  python lead_engine/discovery/auto_prospect_agent.py --industry "plumbing" --city "Rockford" --state "IL"
  python lead_engine/discovery/auto_prospect_agent.py --industry "hvac" --city "Rockford" --state "IL" --limit 30
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, quote, unquote
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent.parent
PROSPECTS_CSV = BASE_DIR / "data" / "prospects.csv"

PROSPECTS_COLUMNS = [
    "business_name", "city", "state", "website",
    "phone", "contact_method", "industry", "likely_opportunity", "priority_score",
    "to_email", "status", "email_sent", "sent_at", "followup_due",
    "scan_notes", "contactability",
    "facebook_url",
    "instagram_url",
    "contact_form_url",
    "social_channels",
    "social_dm_text",
    "lat",   # decimal degrees — populated by area search, empty for city search
    "lng",   # decimal degrees — populated by area search, empty for city search
]

TIMEOUT = 8
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}")
EMAIL_FULL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,24}$")
OBFUSCATED_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]{1,64}\s*"
    r"(?:@|\(at\)|\[at\]|\{at\}|\sat\s)\s*"
    r"(?:[a-zA-Z0-9\-]+\s*(?:\.|\(dot\)|\[dot\]|\{dot\}|\sdot\s)\s*)+[a-zA-Z]{2,24}",
    re.IGNORECASE,
)
LIKELY_EMAIL_ATTR_RE = re.compile(
    r'(?:href|onclick|data-[\w-]*(?:email|mail|contact)|aria-label|title|content|value)=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
USER_DOMAIN_ATTR_RE = re.compile(
    r"<[^>]*data-user=['\"]([^'\"]+)['\"][^>]*data-domain=['\"]([^'\"]+)['\"][^>]*>",
    re.IGNORECASE,
)
CF_EMAIL_RE = re.compile(
    r"(?:data-cfemail=['\"]|email-protection#)([0-9a-fA-F]{6,})",
    re.IGNORECASE,
)

# File extensions that disqualify a regex match (image / frontend assets)
_ASSET_EXTENSIONS = (
    ".webp", ".png", ".jpg", ".jpeg", ".svg",
    ".css", ".js", ".gif", ".ico", ".bmp", ".tiff",
)

_BLOCKED_DOMAINS = {
    "example.com", "test.com", "domain.com",
    "yourdomain.com", "sample.com",
}

JUNK_EMAIL_DOMAINS = {
    "sentry.io","wixpress.com","squarespace.com","shopify.com","wordpress.org",
    "google.com","facebook.com","twitter.com","example.com","yourdomain.com",
    "w3.org","schema.org","bootstrapcdn.com","cloudfront.net","amazonaws.com",
} | _BLOCKED_DOMAINS

_PLACEHOLDER_EMAIL_LOCALS = {
    "email", "name", "example", "yourname", "firstname", "lastname",
    "first.last", "test", "mail", "your-email",
}
_PREFERRED_ROLE_LOCALS = (
    "info", "contact", "office", "service", "support",
    "hello", "dispatch", "sales", "team",
)
_TOP_ROLE_LOCALS = ("info", "contact", "office", "service", "support", "hello")
_ROLE_LOCAL_ORDER = {
    "info": 0,
    "contact": 1,
    "service": 2,
    "support": 3,
    "hello": 4,
    "office": 5,
    "dispatch": 6,
    "sales": 7,
    "team": 8,
}

_DIRECTORY_DOMAINS = {
    "yelp.com", "yellowpages.com", "whitepages.com",
    "bbb.org", "angieslist.com", "angi.com",
    "thumbtack.com", "houzz.com", "homeadvisor.com", "homeadvisor.co",
    "porch.com", "networx.com", "bark.com",
    "tripadvisor.com", "foursquare.com", "mapquest.com",
    "facebook.com", "fb.com", "instagram.com",
    "linkedin.com", "twitter.com", "x.com", "tiktok.com",
    "google.com", "bing.com", "yahoo.com",
    "nextdoor.com", "craigslist.org",
    "chamberofcommerce.com", "manta.com", "superpages.com",
    "buildZoom.com", "buildzoom.com",
}

_AMBIGUOUS_NAME_TOKENS = {
    "handyman", "handymen", "home services", "home service",
    "property services", "property maintenance",
    "general services", "general contractor services",
    "local services", "local service",
    "mr handyman", "ace handyman",
    "services llc", "services inc",
}

# ── Pass 26: Chain/franchise detection + lead quality scoring ────────────────

# Name fragments that reliably indicate a chain or franchise.
# Checked case-insensitively against the full business name.
_CHAIN_NAME_FRAGMENTS = {
    # Fast food / national brands
    "mcdonalds", "mcdonald's", "subway", "starbucks", "dunkin", "dominos",
    "domino's", "taco bell", "wendys", "wendy's", "burger king", "chick-fil-a",
    "chick fil a", "kfc", "pizza hut", "little caesars", "jimmy john",
    "jersey mike", "panera",
    # National service chains that appear in our target industries
    "roto-rooter", "roto rooter", "one hour heating", "one hour air",
    "mr. rooter", "mr rooter", "mr. sparky", "mr sparky", "mr. handyman",
    "ace hardware", "home depot", "lowes", "lowe's",
    "midas", "jiffy lube", "firestone", "pep boys", "mavis",
    "service experts", "aire serv", "coolray", "griffith energy",
    "hiller", "american residential services", "ars/rescue rooter",
    "andy's sprinkler",
    # Franchise structure signals in name
    "franchise", "franchisee",
}

# Corporate entity suffixes that, combined with review-count signals,
# suggest a chain. Used as secondary evidence, not sole criterion.
_CORPORATE_SUFFIXES = (
    " llc", " inc", " corp", " corporation", " holdings",
    " group", " enterprises", " partners", " national",
)


def is_chain_name(name: str) -> bool:
    """
    Return True if the business name matches a known chain pattern.

    Uses two tiers:
    1. Direct fragment match against known chain names (high confidence).
    2. Corporate suffix pattern (weaker signal — used for flagging only,
       not automatic exclusion).

    Only tier-1 matches trigger exclusion; tier-2 is surfaced in scan_notes.
    """
    name_lc = name.strip().lower()
    # Tier 1: direct known-chain match
    for fragment in _CHAIN_NAME_FRAGMENTS:
        if fragment in name_lc:
            return True
    return False


def score_lead_quality(
    email: str,
    website: str,
    is_chain: bool,
    rating: Optional[float],
    review_count: Optional[int],
) -> int:
    """
    Lightweight lead quality score from 0–100.

    Components:
      +35  email address found
      +20  has own website (non-directory)
      +20  not a chain/franchise
      +15  rating 3.5–4.7 (sweet spot: real business, not inflated)
      +10  review count >= 10 (established, not brand new or fake)

    Returns integer 0–100. Higher = higher priority.
    """
    score = 0
    if email:
        score += 35
    if website:
        score += 20
    if not is_chain:
        score += 20
    if rating is not None:
        try:
            r = float(rating)
            if 3.5 <= r <= 4.7:
                score += 15
        except (TypeError, ValueError):
            pass
    if review_count is not None:
        try:
            if int(review_count) >= 10:
                score += 10
        except (TypeError, ValueError):
            pass
    return min(score, 100)


def filter_and_score_rows(
    rows: List[Dict],
    strict_chain_filter: bool = True,
) -> List[Dict]:
    """
    Apply chain filtering and attach lead_quality_score to each row.

    Safe fallback rule (Part 6 of spec):
      If strict filtering would remove >= 70% of rows, disable chain
      exclusion and include all rows with flags.

    Returns the filtered (or unfiltered) row list with scores attached.
    """
    if not rows:
        return rows

    # Attach scores and chain flags first
    for row in rows:
        chain_flag = is_chain_name(row.get("business_name", ""))
        row["_is_chain"] = chain_flag
        row["lead_quality_score"] = score_lead_quality(
            email=row.get("to_email", ""),
            website=row.get("website", ""),
            is_chain=chain_flag,
            rating=row.get("_rating"),
            review_count=row.get("_review_count"),
        )
        # Append chain note to scan_notes
        if chain_flag:
            notes = row.get("scan_notes", "")
            chain_note = "likely chain/franchise"
            row["scan_notes"] = (notes + "; " + chain_note).lstrip("; ")

    if not strict_chain_filter:
        return rows

    # Count how many would survive strict filtering
    surviving = [r for r in rows if not r.get("_is_chain")]
    survival_rate = len(surviving) / len(rows)

    if survival_rate < 0.30:
        # Fallback: area is full of chains — include everything with flags
        print(f"  [filter] Strict chain filter would remove {len(rows)-len(surviving)}/{len(rows)} "
              f"rows (< 30% survival) — relaxing filter to avoid empty results")
        return rows

    if surviving:
        print(f"  [filter] Chain filter: kept {len(surviving)}/{len(rows)} rows "
              f"({len(rows)-len(surviving)} chain(s) excluded)")
    return surviving


INDUSTRY_QUERIES = {
    "plumbing":      "plumber",
    "hvac":          "HVAC heating cooling",
    "electrical":    "electrician",
    "locksmith":     "locksmith",
    "garage_door":   "garage door repair",
    "towing":        "towing roadside assistance",
    "roofing":       "roofing contractor",
    "pest_control":  "pest control exterminator",
    "auto":          "auto repair mechanic",
    "construction":  "general contractor construction",
}

CONTACTABILITY_EMAIL_FOUND  = "email_found"
CONTACTABILITY_WEBSITE_ONLY = "website_contact_only"
CONTACTABILITY_NO_WEBSITE   = "no_website"
CONTACTABILITY_UNREACHABLE  = "website_unreachable"
CONTACTABILITY_DIRECTORY    = "directory_or_ambiguous"

CHANNEL_EMAIL_FOUND   = "email_found"
CHANNEL_CONTACT_FORM  = "contact_form_only"
CHANNEL_FACEBOOK      = "facebook_found"
CHANNEL_INSTAGRAM     = "instagram_found"
CHANNEL_NO_CONTACT    = "no_contact_channel"

_FB_RE  = re.compile(r'https?://(?:www\.)?facebook\.com/(?!sharer|share|dialog)([A-Za-z0-9.\-_/]+)', re.IGNORECASE)
_IG_RE  = re.compile(r'https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)/?', re.IGNORECASE)
_CONTACT_FORM_PATH_RE = re.compile(
    r'href=["\']([^"\']*(?:contact|quote|estimate|request|get-a-quote|schedule)[^"\']*)["\']',
    re.IGNORECASE
)

_FB_JUNK_PATHS = {"sharer", "share", "dialog", "login", "l.php", "tr", "plugins"}


def _normalise_fb_url(raw: str) -> Optional[str]:
    try:
        p = urlparse(raw)
        path_parts = [x for x in p.path.strip("/").split("/") if x]
        if not path_parts:
            return None
        slug = path_parts[0].lower()
        if slug in _FB_JUNK_PATHS or len(slug) < 3:
            return None
        return f"https://www.facebook.com/{path_parts[0]}"
    except Exception:
        return None


def _scrape_social_links(website: str, html: str) -> dict:
    result = {"facebook_url": "", "instagram_url": "", "contact_form_url": ""}
    if not html:
        return result
    base = f"{urlparse(website).scheme}://{urlparse(website).netloc}" if website else ""
    for raw_match in _FB_RE.finditer(html):
        clean = _normalise_fb_url(raw_match.group(0))
        if clean:
            result["facebook_url"] = clean
            break
    for m in _IG_RE.finditer(html):
        slug = m.group(1)
        if len(slug) >= 3 and slug.lower() not in ("p", "explore", "reel", "stories"):
            result["instagram_url"] = f"https://www.instagram.com/{slug}/"
            break
    for m in _CONTACT_FORM_PATH_RE.finditer(html):
        href = m.group(1).strip()
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue
        absolute = urljoin(base, href) if base else href
        if base and not absolute.startswith(base):
            continue
        result["contact_form_url"] = absolute
        break
    return result


def _build_social_channels(email: str, fb: str, ig: str, contact_form: str) -> str:
    channels = []
    if email:
        channels.append(CHANNEL_EMAIL_FOUND)
    if fb:
        channels.append(CHANNEL_FACEBOOK)
    if ig:
        channels.append(CHANNEL_INSTAGRAM)
    if not email and contact_form:
        channels.append(CHANNEL_CONTACT_FORM)
    if not channels:
        channels.append(CHANNEL_NO_CONTACT)
    return ",".join(channels)


def _generate_social_dm_text(business_name: str, city: str) -> str:
    return (
        f"Hey {business_name} — quick question. Do you ever miss calls "
        f"when your team is out on jobs? I set up a simple text-back line "
        f"for service companies in {city} that replies to missed callers "
        f"automatically. Happy to send a quick example — just let me know!"
    )


def _domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _is_directory_url(url: str) -> bool:
    domain = _domain_of(url)
    if not domain:
        return False
    return any(domain == d or domain.endswith("." + d) for d in _DIRECTORY_DOMAINS)


def _is_ambiguous_name(name: str) -> bool:
    name_lc = name.strip().lower()
    return any(token in name_lc for token in _AMBIGUOUS_NAME_TOKENS)


def classify_contactability(
    email: str,
    website: str,
    website_reachable: Optional[bool],
    is_directory: bool,
    is_ambiguous: bool,
) -> str:
    if is_directory or is_ambiguous:
        return CONTACTABILITY_DIRECTORY
    if email:
        return CONTACTABILITY_EMAIL_FOUND
    if not website:
        return CONTACTABILITY_NO_WEBSITE
    if website_reachable is False:
        return CONTACTABILITY_UNREACHABLE
    return CONTACTABILITY_WEBSITE_ONLY


def _fetch(url: str, headers: dict = None) -> dict | str | None:
    try:
        req = Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"})
        with urlopen(req, timeout=TIMEOUT) as r:
            data = r.read()
            ct = r.headers.get("Content-Type", "")
            if "json" in ct:
                return json.loads(data.decode("utf-8"))
            return data.decode("utf-8", errors="ignore")
    except Exception:
        return None


def _probe_reachable(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": "LeadBot/1.0"})
        with urlopen(req, timeout=6) as r:
            return r.status < 400
    except Exception:
        pass
    try:
        req = Request(url, headers={"User-Agent": "LeadBot/1.0"})
        with urlopen(req, timeout=6) as r:
            return r.status < 400
    except Exception:
        return False


_FALLBACK_BLOCKED_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com",
    "yelp.com", "yellowpages.com", "whitepages.com", "bbb.org",
    "angieslist.com", "angi.com", "thumbtack.com", "houzz.com",
    "tripadvisor.com", "foursquare.com", "mapquest.com",
    "google.com", "bing.com", "yahoo.com",
    "linkedin.com", "twitter.com", "tiktok.com",
}


def find_business_website_fallback(business_name: str, city: str) -> tuple[str, str]:
    try:
        query = quote(f"{business_name} {city} official website")
        url = f"https://www.google.com/search?q={query}&num=5"
        html = _fetch(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })
        if not html or not isinstance(html, str):
            return "", ""
        hrefs = re.findall(r'href="(https?://[^"]+)"', html)
        for href in hrefs:
            parsed = urlparse(href)
            domain = parsed.netloc.lower().replace("www.", "")
            if not domain or "google." in domain:
                continue
            if any(blocked in domain for blocked in _FALLBACK_BLOCKED_DOMAINS):
                continue
            root = f"{parsed.scheme}://{parsed.netloc}"
            return root, "website discovered via search fallback"
    except Exception:
        pass
    return "", ""


def _is_asset_email(candidate: str) -> bool:
    """Return True if the candidate looks like an asset filename, not a real email.
    Catches cases like m-home-banner@2x.webp where the extension is the TLD."""
    c = candidate.strip().lower()
    local = c.split("@")[0]
    domain = c.split("@")[-1] if "@" in c else ""
    for ext in _ASSET_EXTENSIONS:
        bare = ext.lstrip(".")
        # Full address or local part ends with the extension
        if c.endswith(ext) or local.endswith(ext):
            return True
        # Domain part is or ends with the extension (e.g. "2x.webp" as pseudo-TLD)
        if domain.endswith(ext):
            return True
        # Extension token appears anywhere in the local or domain part
        if bare in local or bare in domain:
            return True
    return False


def _clean_email(email: str) -> Optional[str]:
    e = (email or "").strip().lower()
    e = e.strip(".,;:'\"<>[]{}()")
    e = re.sub(r"\s+", "", e)
    domain = e.split("@")[-1] if "@" in e else ""
    local = e.split("@")[0] if "@" in e else ""
    if e.count("@") != 1 or not EMAIL_FULL_RE.match(e):
        return None
    if _is_asset_email(e):
        return None
    if domain in JUNK_EMAIL_DOMAINS or domain in _BLOCKED_DOMAINS:
        return None
    if local in _PLACEHOLDER_EMAIL_LOCALS:
        return None
    if any(e.startswith(p) for p in [
        "noreply", "no-reply", "donotreply", "postmaster",
        "bounce", "admin@", "test@",
    ]):
        return None
    if e in {"info@example.com", "contact@example.com", "name@example.com"}:
        return None
    if len(e) > 80 or "." not in domain or ".." in e:
        return None
    if any(c in e for c in ["=", "{", "}", "//", "\\", "(", ")", "<", ">"]):
        return None
    return e


def _decode_cfemail(encoded: str) -> Optional[str]:
    try:
        raw = bytes.fromhex((encoded or "").strip())
    except ValueError:
        return None
    if len(raw) < 2:
        return None
    key = raw[0]
    decoded = "".join(chr(b ^ key) for b in raw[1:])
    return _clean_email(decoded)


def _normalise_email_candidate(raw: str) -> Optional[str]:
    if not raw:
        return None
    candidate = unescape(unquote(str(raw)))
    candidate = candidate.replace("\u200b", "").replace("\u2060", "").replace("\xa0", " ")
    candidate = re.sub(r"(?i)^mailto:\s*", "", candidate)
    candidate = re.sub(r"(?i)\s*(?:\(|\[|\{)?at(?:\)|\]|\})\s*", "@", candidate)
    candidate = re.sub(r"(?i)\s+at\s+", "@", candidate)
    candidate = re.sub(r"(?i)\s*(?:\(|\[|\{)?dot(?:\)|\]|\})\s*", ".", candidate)
    candidate = re.sub(r"(?i)\s+dot\s+", ".", candidate)
    candidate = re.split(r"[?&#]", candidate, maxsplit=1)[0]
    candidate = candidate.strip(" \t\r\n'\"<>[]{}(),;:")
    candidate = re.sub(r"\s+", "", candidate)
    return _clean_email(candidate)


def _score_email_candidate(email: str, site_domain: str) -> tuple[int, int, str]:
    local, domain = email.split("@", 1)
    score = 0
    if site_domain:
        if domain == site_domain or domain.endswith("." + site_domain):
            score -= 50
        elif site_domain.split(".")[0] and site_domain.split(".")[0] in domain:
            score -= 15
        else:
            score += 20
    if local in _TOP_ROLE_LOCALS:
        score -= 12
    elif local in _PREFERRED_ROLE_LOCALS:
        score -= 8
    elif any(local.startswith(prefix) for prefix in _PREFERRED_ROLE_LOCALS):
        score -= 5
    if domain in {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com"}:
        score += 8
    score += max(len(local) - 24, 0)
    return (score, _ROLE_LOCAL_ORDER.get(local, 99), len(email), email)


def _contact_like_urls(base_url: str, html: str) -> List[str]:
    urls: List[str] = []
    if not base_url or not html:
        return urls
    base = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    seen: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        absolute = urljoin(base, href.strip())
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if f"{parsed.scheme}://{parsed.netloc}" != base:
            continue
        path = (parsed.path or "").lower()
        if not any(token in path for token in ("contact", "about", "quote", "estimate", "request", "book", "schedule", "appointment")):
            continue
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        if clean and clean not in seen:
            seen.add(clean)
            urls.append(clean)
    return urls


def _extract_email_candidates_from_html(html: str) -> List[str]:
    if not html:
        return []
    seen: set[str] = set()
    emails: List[str] = []

    def add(candidate: Optional[str]) -> None:
        if candidate and candidate not in seen:
            seen.add(candidate)
            emails.append(candidate)

    variants = []
    for variant in (html, unescape(html), unquote(html)):
        if variant and variant not in variants:
            variants.append(variant)

    for encoded in CF_EMAIL_RE.findall(html):
        add(_decode_cfemail(encoded))

    for user, domain in USER_DOMAIN_ATTR_RE.findall(html):
        add(_normalise_email_candidate(f"{user}@{domain}"))

    for variant in variants:
        for raw in re.findall(r"mailto:([^\"'>\s]+)", variant, re.IGNORECASE):
            add(_normalise_email_candidate(raw))
        for raw in LIKELY_EMAIL_ATTR_RE.findall(variant):
            if any(token in raw.lower() for token in ("@", "mailto", " at ", "(at)", "[at]", "{at}", "%40")):
                add(_normalise_email_candidate(raw))
        for raw in EMAIL_RE.findall(variant):
            add(_clean_email(raw))
        for raw in OBFUSCATED_EMAIL_RE.findall(variant):
            add(_normalise_email_candidate(raw))

    return emails


def extract_contact_details_from_website(website: str) -> Dict[str, object]:
    result: Dict[str, object] = {
        "email": "",
        "site_reachable": False,
        "facebook_url": "",
        "instagram_url": "",
        "contact_form_url": "",
    }
    if not website or not website.startswith(("http://", "https://")):
        return result

    parsed = urlparse(website)
    base = f"{parsed.scheme}://{parsed.netloc}"
    site_domain = parsed.netloc.lower().replace("www.", "")
    static_paths = ["/contact", "/contact-us", "/about", "/about-us", "/reach-us", "/request-quote"]
    pages_to_try = [website]
    emails: List[str] = []
    seen_urls: set[str] = set()

    homepage_html = _fetch(website)
    if isinstance(homepage_html, str) and homepage_html:
        result["site_reachable"] = True
        result.update(_scrape_social_links(website, homepage_html))
        emails.extend(_extract_email_candidates_from_html(homepage_html))
        for discovered in _contact_like_urls(website, homepage_html):
            if discovered not in pages_to_try:
                pages_to_try.append(discovered)

    for path in static_paths:
        url = base + path
        if url not in pages_to_try:
            pages_to_try.append(url)

    for url in pages_to_try[:6]:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        html = homepage_html if url == website and isinstance(homepage_html, str) else _fetch(url)
        if not html or not isinstance(html, str):
            continue
        result["site_reachable"] = True
        if not result["contact_form_url"] or not result["facebook_url"] or not result["instagram_url"]:
            scraped = _scrape_social_links(website, html)
            for key, value in scraped.items():
                if value and not result.get(key):
                    result[key] = value
        emails.extend(_extract_email_candidates_from_html(html))
        time.sleep(0.15)

    cleaned = sorted(set(filter(None, emails)), key=lambda e: _score_email_candidate(e, site_domain))
    if cleaned:
        result["email"] = cleaned[0]
    return result


def _scrape_email_from_website(website: str) -> tuple[Optional[str], bool]:
    """Try homepage then /contact pages for email addresses.
    Returns (email_or_None, site_was_reachable)."""
    details = extract_contact_details_from_website(website)
    email = (details.get("email") or "").strip()
    return email or None, bool(details.get("site_reachable"))


def search_places(query: str, city: str, state: str, api_key: str,
                  limit: int = 20) -> List[Dict]:
    """Use Places API (New) Text Search to find businesses."""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.websiteUri,"
            "places.rating,places.userRatingCount"
        ),
    }
    payload = json.dumps({
        "textQuery": f"{query} in {city} {state}",
        "maxResultCount": min(limit, 20),
    }).encode("utf-8")

    results = []
    try:
        import urllib.request as _ur
        req = _ur.Request(url, data=payload, headers=headers, method="POST")
        with _ur.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        for place in data.get("places", []):
            results.append(place)
    except Exception as exc:
        print(f"  [Places API (New)] Error: {exc}")
    return results


def get_place_details(place_id: str, api_key: str) -> Dict:
    resource = place_id if place_id.startswith("places/") else f"places/{place_id}"
    url = f"https://places.googleapis.com/v1/{resource}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "displayName,nationalPhoneNumber,websiteUri,formattedAddress",
    }
    try:
        import urllib.request as _ur
        req = _ur.Request(url, headers=headers)
        with _ur.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def _read_existing_names(csv_path: Path) -> set:
    if not csv_path.exists():
        return set()
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return {r.get("business_name", "").strip().lower() for r in reader}


def _sanitise_row(row: Dict, fieldnames: List[str]) -> Dict:
    allowed = set(fieldnames)
    clean = {}
    extras = []
    for k, v in row.items():
        if k is None or (isinstance(k, str) and k.startswith("_")):
            continue
        if k not in allowed:
            extras.append(k)
            continue
        clean[k] = v if v is not None else ""
    if extras:
        print(f"  [schema] dropped unexpected keys from row: {extras}")
    for col in fieldnames:
        clean.setdefault(col, "")
    return clean


def _append_to_prospects(csv_path: Path, rows: List[Dict]) -> None:
    """
    Append new prospect rows to the CSV.

    If the new rows require additional columns (unified > existing_header),
    the file is rewritten in full so the header always matches the data width.
    Appending wider rows under a narrow header causes DictReader to push the
    overflow into restkey=None, which crashes _update_prospect_status.

    If the schema is unchanged, rows are appended without a full rewrite.
    """
    if not rows:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not csv_path.exists() or csv_path.stat().st_size == 0

    if is_new:
        fieldnames = PROSPECTS_COLUMNS
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(_sanitise_row(row, fieldnames))
        return

    # Read existing header and all rows
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        raw_header = next(csv.reader(f), [])
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        existing_rows = list(csv.DictReader(f))

    # Normalise legacy column names before building unified schema.
    # 'scan_note' (old) → 'scan_notes' (current) so they never both appear.
    existing_header = ["scan_notes" if c == "scan_note" else c for c in raw_header]

    # Rename key in existing rows to match
    if "scan_note" in raw_header:
        for row in existing_rows:
            if "scan_note" in row:
                row["scan_notes"] = row.pop("scan_note")

    # Build unified fieldnames: existing cols first, then any new ones
    unified = list(existing_header)
    for col in PROSPECTS_COLUMNS:
        if col not in unified:
            unified.append(col)

    schema_expanded = (len(unified) > len(existing_header))

    if schema_expanded:
        # Full rewrite so header matches all row widths
        all_rows = existing_rows + rows
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=unified, extrasaction="ignore")
            writer.writeheader()
            for row in all_rows:
                writer.writerow(_sanitise_row(row, unified))
    else:
        # Schema unchanged — safe to append
        with csv_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=unified, extrasaction="ignore")
            for row in rows:
                writer.writerow(_sanitise_row(row, unified))


def discover_prospects(industry: str, city: str, state: str,
                       api_key: str, limit: int = 20,
                       scrape_emails: bool = True) -> List[Dict]:
    """Full autonomous discovery pipeline."""
    query = INDUSTRY_QUERIES.get(industry.lower(), industry)
    print(f"\n  Searching Google Places: '{query} in {city} {state}'")
    places = search_places(query, city, state, api_key, limit=limit)
    print(f"  Found {len(places)} places from Google\n")

    if not places:
        return []

    existing = _read_existing_names(PROSPECTS_CSV)
    new_rows: List[Dict] = []

    for place in places:
        display = place.get("displayName", {})
        name = (display.get("text", "") if isinstance(display, dict) else str(display)).strip()
        if not name or name.lower() in existing:
            print(f"  skip (duplicate): {name}")
            continue

        # Pass 26: extract rating/review signals while still in the Places response
        _rating = place.get("rating")
        _review_count = place.get("userRatingCount")

        print(f"  Processing: {name} ...", end=" ", flush=True)

        phone = (place.get("nationalPhoneNumber") or "").replace(" ","").replace("-","").replace("(","").replace(")","").replace("+1","")
        website = (place.get("websiteUri") or "").strip()

        # Strip UTM params and other query strings from website URL to improve deduplication
        if website:
            parsed_site = urlparse(website)
            website = f"{parsed_site.scheme}://{parsed_site.netloc}{parsed_site.path}".rstrip("/")

        is_directory = _is_directory_url(website)
        if is_directory:
            website = ""

        is_ambiguous = _is_ambiguous_name(name)

        if not phone or (not website and not is_directory):
            place_id = place.get("id", "")
            if place_id:
                details = get_place_details(place_id, api_key)
                phone = phone or (details.get("nationalPhoneNumber") or "").replace(" ","").replace("-","").replace("(","").replace(")","").replace("+1","")
                detail_site = (details.get("websiteUri") or "").strip()
                if detail_site:
                    parsed_detail = urlparse(detail_site)
                    detail_site = f"{parsed_detail.scheme}://{parsed_detail.netloc}{parsed_detail.path}".rstrip("/")
                if not website and detail_site and not _is_directory_url(detail_site):
                    website = detail_site

        fallback_note = ""
        if not website and not is_directory and not is_ambiguous:
            website, fallback_note = find_business_website_fallback(name, city)
            if website and _is_directory_url(website):
                website = ""
                fallback_note = "fallback returned directory URL — cleared"

        email = ""
        site_reachable: Optional[bool] = None
        social = {"facebook_url": "", "instagram_url": "", "contact_form_url": ""}

        if is_directory or is_ambiguous:
            site_reachable = None
        elif scrape_emails and website:
            contact_details = extract_contact_details_from_website(website)
            email = (contact_details.get("email") or "").strip()
            site_reachable = contact_details.get("site_reachable")
            social = {
                "facebook_url": contact_details.get("facebook_url", ""),
                "instagram_url": contact_details.get("instagram_url", ""),
                "contact_form_url": contact_details.get("contact_form_url", ""),
            }
        elif website:
            site_reachable = _probe_reachable(website)

        contactability = classify_contactability(
            email=email, website=website,
            website_reachable=site_reachable,
            is_directory=is_directory, is_ambiguous=is_ambiguous,
        )

        social_channels = _build_social_channels(
            email=email,
            fb=social.get("facebook_url", ""),
            ig=social.get("instagram_url", ""),
            contact_form=social.get("contact_form_url", ""),
        )
        social_dm_text = _generate_social_dm_text(name, city)

        notes_parts = []
        if fallback_note:
            notes_parts.append(fallback_note)
        if is_directory:
            notes_parts.append("directory URL stripped from Places result")
        if is_ambiguous:
            notes_parts.append("ambiguous business name")
        if site_reachable is False:
            notes_parts.append("website unreachable")
        scan_notes = "; ".join(notes_parts)

        print(f"contactability={contactability}")

        row = {
            "business_name":      name,
            "city":               city,
            "state":              state,
            "website":            website,
            "phone":              phone,
            "contact_method":     "email" if email else ("website" if website else "phone"),
            "industry":           industry,
            "likely_opportunity": "",
            "priority_score":     "",
            "to_email":           email,
            "status":             "new",
            "email_sent":         "",
            "sent_at":            "",
            "followup_due":       "",
            "scan_notes":         scan_notes,
            "contactability":     contactability,
            "facebook_url":       social.get("facebook_url", ""),
            "instagram_url":      social.get("instagram_url", ""),
            "contact_form_url":   social.get("contact_form_url", ""),
            "social_channels":    social_channels,
            "social_dm_text":     social_dm_text,
            # Temporary scoring fields (stripped before CSV write via extrasaction=ignore)
            "_rating":            _rating,
            "_review_count":      _review_count,
        }
        new_rows.append(row)
        existing.add(name.lower())
        time.sleep(0.3)

    # Pass 26: filter chains and attach quality scores before writing to CSV
    new_rows = filter_and_score_rows(new_rows, strict_chain_filter=True)
    _append_to_prospects(PROSPECTS_CSV, new_rows)
    return new_rows


def search_places_area(
    query: str,
    lat: float,
    lng: float,
    radius_m: float,
    api_key: str,
    limit: int = 20,
) -> List[Dict]:
    """
    Places API (New) Text Search with locationBias circle.
    Used for map-area discovery instead of city-string discovery.
    Same field mask as search_places(); results are identical in shape.
    """
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.websiteUri,places.location,"
            "places.rating,places.userRatingCount"
        ),
    }
    payload = json.dumps({
        "textQuery": query,
        "maxResultCount": min(limit, 20),
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
    }).encode("utf-8")

    results = []
    try:
        import urllib.request as _ur
        req = _ur.Request(url, data=payload, headers=headers, method="POST")
        with _ur.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        for place in data.get("places", []):
            results.append(place)
    except Exception as exc:
        print(f"  [Places API area] Error: {exc}")
    return results


def discover_prospects_area(
    industry: str,
    lat: float,
    lng: float,
    radius_m: float,
    api_key: str,
    limit: int = 20,
    scrape_emails: bool = True,
) -> List[Dict]:
    """
    Area-based discovery: same pipeline as discover_prospects() but
    uses lat/lng/radius instead of city string for the Places query.

    City and state are reverse-geocoded from the result's formattedAddress
    so each row carries accurate location data.

    Returns the list of newly added prospect dicts (same schema as
    discover_prospects).
    """
    query = INDUSTRY_QUERIES.get(industry.lower(), industry)
    print(f"\n  Area search: '{query}' lat={lat:.4f} lng={lng:.4f} r={radius_m:.0f}m")
    places = search_places_area(query, lat, lng, radius_m, api_key, limit=limit)
    print(f"  Found {len(places)} places\n")

    if not places:
        return []

    existing = _read_existing_names(PROSPECTS_CSV)
    new_rows: List[Dict] = []

    for place in places:
        display = place.get("displayName", {})
        name = (display.get("text", "") if isinstance(display, dict) else str(display)).strip()
        if not name or name.lower() in existing:
            print(f"  skip (duplicate): {name}")
            continue

        # Parse city/state from formattedAddress (best effort)
        address = place.get("formattedAddress", "")
        city, state = _parse_city_state(address)

        print(f"  Processing: {name} ({city}, {state}) ...", end=" ", flush=True)

        phone = (place.get("nationalPhoneNumber") or "").replace(" ","").replace("-","").replace("(","").replace(")","").replace("+1","")
        website = (place.get("websiteUri") or "").strip()

        if website:
            parsed_site = urlparse(website)
            website = f"{parsed_site.scheme}://{parsed_site.netloc}{parsed_site.path}".rstrip("/")

        is_directory = _is_directory_url(website)
        if is_directory:
            website = ""
        is_ambiguous = _is_ambiguous_name(name)

        if not phone or (not website and not is_directory):
            place_id = place.get("id", "")
            if place_id:
                details = get_place_details(place_id, api_key)
                phone = phone or (details.get("nationalPhoneNumber") or "").replace(" ","").replace("-","").replace("(","").replace(")","").replace("+1","")
                detail_site = (details.get("websiteUri") or "").strip()
                if detail_site:
                    p2 = urlparse(detail_site)
                    detail_site = f"{p2.scheme}://{p2.netloc}{p2.path}".rstrip("/")
                if not website and detail_site and not _is_directory_url(detail_site):
                    website = detail_site

        fallback_note = ""
        if not website and not is_directory and not is_ambiguous:
            website, fallback_note = find_business_website_fallback(name, city or "")
            if website and _is_directory_url(website):
                website = ""
                fallback_note = "fallback returned directory URL — cleared"

        email = ""
        site_reachable: Optional[bool] = None
        social = {"facebook_url": "", "instagram_url": "", "contact_form_url": ""}

        if is_directory or is_ambiguous:
            site_reachable = None
        elif scrape_emails and website:
            contact_details = extract_contact_details_from_website(website)
            email = (contact_details.get("email") or "").strip()
            site_reachable = contact_details.get("site_reachable")
            social = {
                "facebook_url": contact_details.get("facebook_url", ""),
                "instagram_url": contact_details.get("instagram_url", ""),
                "contact_form_url": contact_details.get("contact_form_url", ""),
            }
        elif website:
            site_reachable = _probe_reachable(website)

        contactability = classify_contactability(
            email=email, website=website,
            website_reachable=site_reachable,
            is_directory=is_directory, is_ambiguous=is_ambiguous,
        )
        social_channels = _build_social_channels(
            email=email, fb=social.get("facebook_url",""),
            ig=social.get("instagram_url",""), contact_form=social.get("contact_form_url",""),
        )
        social_dm_text = _generate_social_dm_text(name, city or "the area")

        notes_parts = []
        if fallback_note: notes_parts.append(fallback_note)
        if is_directory:  notes_parts.append("directory URL stripped from Places result")
        if is_ambiguous:  notes_parts.append("ambiguous business name")
        if site_reachable is False: notes_parts.append("website unreachable")
        notes_parts.append(f"area search lat={lat:.4f} lng={lng:.4f} r={radius_m:.0f}m")
        scan_notes = "; ".join(notes_parts)

        print(f"contactability={contactability}")

        # Pass 26: extract rating/review signals from Places response
        _rating = place.get("rating")
        _review_count = place.get("userRatingCount")

        # Extract exact coordinates from Places location field
        _loc     = place.get("location") or {}
        place_lat = str(_loc.get("latitude",  ""))
        place_lng = str(_loc.get("longitude", ""))

        row = {
            "business_name":      name,
            "city":               city,
            "state":              state,
            "website":            website,
            "phone":              phone,
            "contact_method":     "email" if email else ("website" if website else "phone"),
            "industry":           industry,
            "likely_opportunity": "",
            "priority_score":     "",
            "to_email":           email,
            "status":             "new",
            "email_sent":         "",
            "sent_at":            "",
            "followup_due":       "",
            "scan_notes":         scan_notes,
            "contactability":     contactability,
            "facebook_url":       social.get("facebook_url",""),
            "instagram_url":      social.get("instagram_url",""),
            "contact_form_url":   social.get("contact_form_url",""),
            "social_channels":    social_channels,
            "social_dm_text":     social_dm_text,
            "lat":                place_lat,
            "lng":                place_lng,
            # Temporary scoring fields (stripped before CSV write via extrasaction=ignore)
            "_rating":            _rating,
            "_review_count":      _review_count,
        }
        new_rows.append(row)
        existing.add(name.lower())
        time.sleep(0.3)

    # Pass 26: filter chains and attach quality scores before writing to CSV
    new_rows = filter_and_score_rows(new_rows, strict_chain_filter=True)
    _append_to_prospects(PROSPECTS_CSV, new_rows)
    return new_rows


def _parse_city_state(formatted_address: str) -> tuple[str, str]:
    """
    Best-effort parse of city and state from a Google formattedAddress string.
    Example: '123 Main St, Rockford, IL 61101, USA' -> ('Rockford', 'IL')
    Returns ('', '') if parsing fails.
    """
    if not formatted_address:
        return "", ""
    # Remove country suffix
    addr = re.sub(r",?\s*USA\s*$", "", formatted_address.strip())
    parts = [p.strip() for p in addr.split(",")]
    # Last part is typically 'ST ZIPCODE' e.g. 'IL 61101'
    # Second-to-last is typically the city
    if len(parts) >= 2:
        city = parts[-2].strip()
        state_zip = parts[-1].strip()
        state_match = re.match(r"^([A-Z]{2})", state_zip)
        state = state_match.group(1) if state_match else ""
        return city, state
    return "", ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomously discover local business prospects.")
    parser.add_argument("--industry", required=True,
                        help=f"Industry to search. Options: {', '.join(INDUSTRY_QUERIES.keys())}")
    parser.add_argument("--city", required=True, help="City name (e.g. Rockford)")
    parser.add_argument("--state", required=True, help="State abbreviation (e.g. IL)")
    parser.add_argument("--limit", type=int, default=20, help="Max businesses to find (default 20)")
    parser.add_argument("--no-email-scrape", action="store_true", help="Skip email scraping")
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        print("\nERROR: GOOGLE_PLACES_API_KEY environment variable not set.")
        print("Get a free key at: https://console.cloud.google.com")
        print("Enable: Places API — then set the variable and re-run.\n")
        sys.exit(1)

    rows = discover_prospects(
        industry=args.industry,
        city=args.city,
        state=args.state,
        api_key=api_key,
        limit=args.limit,
        scrape_emails=not args.no_email_scrape,
    )

    by_contactability: Dict[str, int] = {}
    for r in rows:
        c = r.get("contactability", "unknown")
        by_contactability[c] = by_contactability.get(c, 0) + 1

    print(f"\n  ✓ Added {len(rows)} new prospects to prospects.csv")
    for label, count in sorted(by_contactability.items()):
        print(f"    {label}: {count}")
    print(f"\n  Next: run 'python lead_engine/run_lead_engine.py' to draft outreach emails\n")


if __name__ == "__main__":
    main()
