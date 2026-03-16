from __future__ import annotations

import csv
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, List, Tuple

REQUIRED_INPUT_COLUMNS = ["business_name", "city", "state"]
ALL_COLUMNS = [
    "business_name",
    "city",
    "state",
    "website",
    "phone",
    "contact_method",
    "likely_opportunity",
    "priority_score",
]

BLANK_LIKE_VALUES = {"", "unknown", "n/a", "na", "none", "null", "-", "--"}


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
    """Primary key: business_name + website; fallback: business_name + city."""
    business_name = normalize_identity_token(row.get("business_name", ""))
    website = normalize_identity_token(row.get("website", ""))
    city = normalize_identity_token(row.get("city", ""))

    if website:
        return business_name, website
    return business_name, city


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

        normalized_header = [_normalize_header(name) for name in reader.fieldnames]
        missing_required_columns = [
            column for column in REQUIRED_INPUT_COLUMNS if column not in normalized_header
        ]
        if missing_required_columns:
            raise ValueError(
                "Prospect CSV missing required columns: " + ", ".join(missing_required_columns)
            )

        header_map = {
            raw_name: _normalize_header(raw_name)
            for raw_name in reader.fieldnames
            if _normalize_header(raw_name)
        }

        prospects: List[Dict[str, str]] = []
        skipped_invalid = 0

        for row in reader:
            normalized_row = {column: "" for column in ALL_COLUMNS}

            for raw_key, raw_value in row.items():
                key = header_map.get(raw_key, "")
                if key in normalized_row:
                    normalized_row[key] = normalize_value(raw_value)

            if not normalized_row["business_name"] or not normalized_row["city"] or not normalized_row["state"]:
                skipped_invalid += 1
                continue

            prospects.append(normalized_row)

    if skipped_invalid:
        print(f"Skipped {skipped_invalid} prospect rows missing required values (business_name/city/state).")

    return prospects
