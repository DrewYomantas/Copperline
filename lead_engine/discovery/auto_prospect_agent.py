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
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, quote
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
]

TIMEOUT = 8
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}")

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
    e = email.strip().lower()
    domain = e.split("@")[-1] if "@" in e else ""
    if _is_asset_email(e):
        return None
    if domain in JUNK_EMAIL_DOMAINS or domain in _BLOCKED_DOMAINS:
        return None
    if any(e.startswith(p) for p in [
        "noreply", "no-reply", "donotreply", "postmaster",
        "bounce", "admin@", "test@", "info@example",
    ]):
        return None
    if len(e) > 80 or "." not in domain:
        return None
    if any(c in e for c in ["=", "{", "}", "//", "\\", "(", ")", "<", ">"]):
        return None
    return e


def _scrape_email_from_website(website: str) -> tuple[Optional[str], bool]:
    """Try homepage then /contact pages for email addresses.
    Returns (email_or_None, site_was_reachable)."""
    if not website or not website.startswith(("http://", "https://")):
        return None, False

    seen: set[str] = set()
    emails: List[str] = []
    base = f"{urlparse(website).scheme}://{urlparse(website).netloc}"
    pages_to_try = [website]
    for path in ["/contact", "/contact-us", "/about", "/reach-us"]:
        pages_to_try.append(base + path)

    site_domain = urlparse(website).netloc.replace("www.", "")
    site_reachable = False

    for url in pages_to_try[:4]:
        html = _fetch(url)
        if not html or not isinstance(html, str):
            continue
        site_reachable = True
        for m in re.findall(r'mailto:([^"\'>\s?&]+)', html, re.IGNORECASE):
            raw = re.split(r'[?&]', m)[0]
            cleaned = _clean_email(raw)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                emails.append(cleaned)
        for raw in EMAIL_RE.findall(html):
            cleaned = _clean_email(raw)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                emails.append(cleaned)
        if emails:
            break
        time.sleep(0.2)

    if not emails:
        return None, site_reachable

    def score(e: str) -> int:
        return 0 if site_domain and site_domain in e else 1

    emails.sort(key=score)
    return emails[0], site_reachable


def search_places(query: str, city: str, state: str, api_key: str,
                  limit: int = 20) -> List[Dict]:
    """Use Places API (New) Text Search to find businesses."""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.nationalPhoneNumber,places.websiteUri"
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
    if not rows:
        return
    is_new = not csv_path.exists() or csv_path.stat().st_size == 0
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if not is_new:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            existing_header = next(csv.reader(f), [])
        unified = list(existing_header)
        for col in PROSPECTS_COLUMNS:
            if col not in unified:
                unified.append(col)
        fieldnames = unified
    else:
        fieldnames = PROSPECTS_COLUMNS

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        for row in rows:
            writer.writerow(_sanitise_row(row, fieldnames))


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
            from urllib.request import urlopen, Request as _Req
            _homepage_html = ""
            try:
                _req = _Req(website, headers={"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"})
                with urlopen(_req, timeout=TIMEOUT) as _r:
                    _homepage_html = _r.read().decode("utf-8", errors="ignore")
                site_reachable = True
            except Exception:
                site_reachable = False

            if _homepage_html:
                email, _ = _scrape_email_from_website(website)
                email = email or ""
                social = _scrape_social_links(website, _homepage_html)
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
        }
        new_rows.append(row)
        existing.add(name.lower())
        time.sleep(0.3)

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
            "places.nationalPhoneNumber,places.websiteUri"
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
            from urllib.request import urlopen, Request as _Req
            _homepage_html = ""
            try:
                _req = _Req(website, headers={"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"})
                with urlopen(_req, timeout=TIMEOUT) as _r:
                    _homepage_html = _r.read().decode("utf-8", errors="ignore")
                site_reachable = True
            except Exception:
                site_reachable = False
            if _homepage_html:
                email, _ = _scrape_email_from_website(website)
                email = email or ""
                social = _scrape_social_links(website, _homepage_html)
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
        }
        new_rows.append(row)
        existing.add(name.lower())
        time.sleep(0.3)

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
