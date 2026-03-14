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
]

TIMEOUT = 8
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}")

# File extensions that disqualify a regex match (image / frontend assets)
_ASSET_EXTENSIONS = (
    ".webp", ".png", ".jpg", ".jpeg", ".svg",
    ".css", ".js", ".gif", ".ico", ".bmp", ".tiff",
)

# Blocked placeholder / dummy domains
_BLOCKED_DOMAINS = {
    "example.com", "test.com", "domain.com",
    "yourdomain.com", "sample.com",
}

JUNK_EMAIL_DOMAINS = {
    "sentry.io","wixpress.com","squarespace.com","shopify.com","wordpress.org",
    "google.com","facebook.com","twitter.com","example.com","yourdomain.com",
    "w3.org","schema.org","bootstrapcdn.com","cloudfront.net","amazonaws.com",
} | _BLOCKED_DOMAINS

# Maps friendly industry name → Google Places search query
INDUSTRY_QUERIES = {
    "plumbing":     "plumber",
    "hvac":         "HVAC heating cooling",
    "electrical":   "electrician",
    "roofing":      "roofing contractor",
    "landscaping":  "landscaping lawn care",
    "pest_control": "pest control exterminator",
    "dental":       "dentist dental office",
    "medical":      "medical clinic doctor",
    "legal":        "attorney law firm",
    "real_estate":  "real estate agent realtor",
    "restaurant":   "restaurant",
    "auto":         "auto repair mechanic",
    "cleaning":     "cleaning service",
    "construction": "general contractor construction",
    "salon":        "hair salon barber",
    "gym":          "gym fitness center",
    "moving":       "moving company",
    "accounting":   "accountant CPA bookkeeping",
    "insurance":    "insurance agency",
}


def _fetch(url: str, headers: dict = None) -> dict | str | None:
    try:
        req = Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0)"})
        with urlopen(req, timeout=TIMEOUT) as r:
            data = r.read()
            ct = r.headers.get("Content-Type", "")
            if "json" in ct:
                return json.loads(data.decode("utf-8"))
            return data.decode("utf-8", errors="ignore")
    except Exception as exc:
        return None


def _is_asset_email(candidate: str) -> bool:
    """Return True if the candidate looks like an asset filename, not a real email."""
    local_part = candidate.split("@")[0]
    for part in (local_part, candidate):
        if any(part.endswith(ext) for ext in _ASSET_EXTENSIONS):
            return True
        if any(ext in part for ext in _ASSET_EXTENSIONS):
            return True
    return False


def _clean_email(email: str) -> Optional[str]:
    e = email.strip().lower()
    domain = e.split("@")[-1] if "@" in e else ""
    # Reject asset filenames masquerading as emails
    if _is_asset_email(e):
        return None
    if domain in JUNK_EMAIL_DOMAINS or domain in _BLOCKED_DOMAINS:
        return None
    if any(e.startswith(p) for p in ["noreply","no-reply","donotreply","postmaster","bounce","admin@","test@","info@example"]):
        return None
    if len(e) > 80 or "." not in domain:
        return None
    if any(c in e for c in ["=","{","}","//","\\","(",")","<",">"]):
        return None
    return e


def _scrape_email_from_website(website: str) -> Optional[str]:
    """Try homepage then /contact for email addresses."""
    if not website or not website.startswith(("http://", "https://")):
        return None

    emails: List[str] = []
    scan_notes: List[str] = []
    seen: set[str] = set()
    pages_to_try = [website]

    # Add common contact page paths
    base = f"{urlparse(website).scheme}://{urlparse(website).netloc}"
    for path in ["/contact", "/contact-us", "/about", "/reach-us"]:
        pages_to_try.append(base + path)

    site_domain = urlparse(website).netloc.replace("www.", "")

    for url in pages_to_try[:4]:
        try:
            html = _fetch(url)
        except Exception:
            html = None
        if not html or not isinstance(html, str):
            continue

        # mailto: links first (most reliable)
        for m in re.findall(r'mailto:([^"\'>\s?&]+)', html, re.IGNORECASE):
            raw = re.split(r'[?&]', m)[0]
            cleaned = _clean_email(raw)
            if cleaned is None:
                scan_notes.append(f"invalid asset email filtered: {raw.lower()}")
            elif cleaned in seen:
                scan_notes.append(f"duplicate email skipped: {cleaned}")
            else:
                seen.add(cleaned)
                emails.append(cleaned)
                scan_notes.append(f"valid email extracted: {cleaned}")

        # visible email addresses
        for raw in EMAIL_RE.findall(html):
            cleaned = _clean_email(raw)
            if cleaned is None:
                scan_notes.append(f"invalid asset email filtered: {raw.lower()}")
            elif cleaned in seen:
                scan_notes.append(f"duplicate email skipped: {cleaned}")
            else:
                seen.add(cleaned)
                emails.append(cleaned)
                scan_notes.append(f"valid email extracted: {cleaned}")

        if emails:
            break
        time.sleep(0.2)

    if not emails:
        return None

    # Prefer emails matching the site domain
    def score(e: str) -> int:
        return 0 if site_domain and site_domain in e else 1

    emails.sort(key=score)
    return emails[0]


def search_places(query: str, city: str, state: str, api_key: str,
                  limit: int = 20) -> List[Dict]:
    """
    Use Places API (New) Text Search to find businesses.
    Endpoint: https://places.googleapis.com/v1/places:searchText
    """
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri",
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
    """
    Places API (New) — place_id is the full resource name e.g. 'places/ChIJ...'
    We already get phone + website from searchText FieldMask, so this is a
    lightweight fallback only used if those fields are missing.
    """
    # Normalise: strip leading 'places/' if present for the URL
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
        return {r.get("business_name","").strip().lower() for r in reader}


def _append_to_prospects(csv_path: Path, rows: List[Dict]) -> None:
    is_new = not csv_path.exists() or csv_path.stat().st_size == 0
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PROSPECTS_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)


def discover_prospects(industry: str, city: str, state: str,
                       api_key: str, limit: int = 20,
                       scrape_emails: bool = True) -> List[Dict]:
    """
    Full autonomous discovery pipeline:
    1. Google Places search → business list
    2. Places Details → phone + website per business
    3. Website scrape → email address
    4. Dedupe against existing prospects.csv
    5. Append new rows
    """
    query = INDUSTRY_QUERIES.get(industry.lower(), industry)
    print(f"\n  Searching Google Places: '{query} in {city} {state}'")
    places = search_places(query, city, state, api_key, limit=limit)
    print(f"  Found {len(places)} places from Google\n")

    existing = _read_existing_names(PROSPECTS_CSV)
    new_rows: List[Dict] = []

    for place in places:
        # Places API (New): displayName is {"text": "...", "languageCode": "..."}
        display = place.get("displayName", {})
        name = (display.get("text", "") if isinstance(display, dict) else str(display)).strip()
        if not name or name.lower() in existing:
            print(f"  skip (duplicate): {name}")
            continue

        print(f"  Processing: {name} ...", end=" ", flush=True)

        # Places API (New) returns these fields directly from searchText
        phone = (place.get("nationalPhoneNumber") or "").replace(" ", "").replace("-", "").replace("(","").replace(")","").replace("+1","")
        website = (place.get("websiteUri") or "").strip()
        address = place.get("formattedAddress", "")

        # Only call details if phone or website missing
        if not phone or not website:
            place_id = place.get("id", "")
            if place_id:
                details = get_place_details(place_id, api_key)
                phone = phone or (details.get("nationalPhoneNumber") or "").replace(" ", "").replace("-", "").replace("(","").replace(")","").replace("+1","")
                website = website or (details.get("websiteUri") or "").strip()

        # Try to get email from website
        email = ""
        if scrape_emails and website:
            email = _scrape_email_from_website(website) or ""

        status = f"website={bool(website)} email={email or 'none'}"
        print(status)

        row = {
            "business_name": name,
            "city": city,
            "state": state,
            "website": website,
            "phone": phone,
            "contact_method": "email" if email else ("website" if website else "phone"),
            "industry": industry,
            "likely_opportunity": "",
            "priority_score": "",
            "to_email": email,
            "status": "new",
            "email_sent": "",
            "sent_at": "",
            "followup_due": "",
        }
        new_rows.append(row)
        existing.add(name.lower())
        time.sleep(0.3)

    _append_to_prospects(PROSPECTS_CSV, new_rows)

    return new_rows


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

    found_email = sum(1 for r in rows if r.get("to_email"))
    print(f"\n  ✓ Added {len(rows)} new prospects to prospects.csv")
    print(f"  ✓ Found emails for {found_email} of them")
    print(f"\n  Next: run 'python lead_engine/run_lead_engine.py' to draft outreach emails\n")


if __name__ == "__main__":
    main()
