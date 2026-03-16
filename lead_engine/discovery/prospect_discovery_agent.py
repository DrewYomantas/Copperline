"""
prospect_discovery_agent.py
Utility functions for deduplication and CSV loading of prospects.
Used by run_lead_engine.py.

Key design rules:
  - All dedupe keys are computed from NORMALIZED data (lowercase, stripped, UTM-free)
  - dedupe_key_for_prospect: primary = (normalized_name, clean_domain)
                             fallback = (normalized_name, normalized_city)
  - normalize_business_name: strips noise words, punctuation, LLC/Inc suffixes
  - clean_website_for_key: strips UTM params and trailing slashes, returns bare domain
"""
from __future__ import annotations

import csv
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

REQUIRED_INPUT_COLUMNS = ["business_name", "city", "state"]
ALL_COLUMNS = [
    "business_name", "city", "state", "website", "phone",
    "contact_method", "industry", "likely_opportunity", "priority_score",
    "to_email", "status", "email_sent", "sent_at", "followup_due",
    "scan_notes", "contactability",
    "facebook_url", "instagram_url", "contact_form_url",
    "social_channels", "social_dm_text",
    "automation_opportunity",
]

BLANK_LIKE_VALUES = {"", "unknown", "n/a", "na", "none", "null", "-", "--"}

# Noise words stripped from business names during normalization.
# These are common enough that two businesses can have the same name
# minus one of these tokens and still be the same business.
_NAME_NOISE_WORDS = {
    "llc", "inc", "corp", "co", "ltd", "company", "companies",
    "plumbing", "plumber", "sewer", "drain", "heating", "cooling",
    "hvac", "electric", "electrical", "locksmith", "roofing",
    "services", "service", "solutions", "group", "the", "and", "&",
}

_PUNCT_RE = re.compile(r"[^\w\s]")


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_value(value: str | None) -> str:
    text = (value or "").strip()
    return "" if text.lower() in BLANK_LIKE_VALUES else text


def normalize_identity_token(value: str | None) -> str:
    return " ".join(normalize_value(value).lower().split())




def clean_website_for_key(website: str | None) -> str:
    """Normalize website/domain for dedupe keys."""
    raw = normalize_value(website)
    if not raw:
        return ""

    candidate = raw
    if "://" not in candidate:
        candidate = "https://" + candidate

    try:
        parsed = urlparse(candidate)
        host = (parsed.netloc or parsed.path or "").strip().lower()
    except Exception:
        return ""

    if host.startswith("www."):
        host = host[4:]
    return host.strip("/")
def dedupe_key_for_prospect(row: Dict[str, str]) -> Tuple[str, str]:
    """
    Compute a stable, normalized dedupe key for a prospect or queue row.

    Primary key:  (normalized_name, clean_domain)
    Fallback key: (normalized_name, normalized_city)   [when no website]

    Both sides are normalized so UTM variants, capitalization differences,
    and noise word presence do not produce false mismatches.
    """
    name_key = normalize_business_name(row.get("business_name", ""))
    domain = clean_website_for_key(row.get("website", ""))
    city = normalize_identity_token(row.get("city", ""))

    if domain:
        return name_key, domain
    return name_key, city


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _normalize_header(name: str) -> str:
    return (name or "").strip().lower()


def load_prospects_from_csv(csv_path: str | Path) -> List[Dict[str, str]]:
    """Load and normalize prospects from CSV, skipping invalid rows."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Prospect file not found: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Prospect CSV must include a header row.")

        normalized_header = [_normalize_header(n) for n in reader.fieldnames]
        missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in normalized_header]
        if missing:
            raise ValueError("Prospect CSV missing required columns: " + ", ".join(missing))

        header_map = {}
        for raw_name in reader.fieldnames:
            if raw_name is None:
                continue
            normalised = _normalize_header(raw_name)
            if not normalised:
                continue
            # Legacy rename: scan_note → scan_notes
            if normalised == "scan_note":
                normalised = "scan_notes"
            header_map[raw_name] = normalised

        prospects: List[Dict[str, str]] = []
        skipped_invalid = 0

        for row in reader:
            normalized_row = {col: "" for col in ALL_COLUMNS}
            for raw_key, raw_value in row.items():
                key = header_map.get(raw_key, "")
                if key in normalized_row:
                    normalized_row[key] = normalize_value(raw_value)

            if not (normalized_row["business_name"] and
                    normalized_row["city"] and
                    normalized_row["state"]):
                skipped_invalid += 1
                continue

            prospects.append(normalized_row)

    if skipped_invalid:
        print(f"Skipped {skipped_invalid} prospect rows missing required values.")

    return prospects
