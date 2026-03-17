from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from discovery.auto_prospect_agent import (
    _build_social_channels,
    _is_ambiguous_name,
    _is_directory_url,
    classify_contactability,
    extract_contact_details_from_website,
)


def _read_rows(path: Path) -> tuple[List[Dict[str, str]], List[str]]:
    if not path.exists():
        return [], []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return rows, fieldnames


def _write_rows(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    safe_fieldnames = [name for name in fieldnames if name]
    extras = [
        "contactability",
        "contact_method",
        "facebook_url",
        "instagram_url",
        "contact_form_url",
        "social_channels",
    ]
    for col in extras:
        if col not in safe_fieldnames:
            safe_fieldnames.append(col)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=safe_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def enrich_prospects_with_emails(csv_path: str | Path, limit: int = 0, overwrite: bool = False) -> Dict[str, int]:
    """
    Fill missing website-derived contact fields in prospects.csv.

    This is intentionally conservative:
    - skips directory and ambiguous-name rows
    - only overwrites an existing email when overwrite=True
    - updates only contactability/contact channel fields tied to extraction
    """
    path = Path(csv_path)
    rows, fieldnames = _read_rows(path)
    if not rows:
        return {
            "processed": 0,
            "updated": 0,
            "skipped": 0,
            "unchanged": 0,
            "limit": int(limit or 0),
            "overwrite": 1 if overwrite else 0,
        }

    processed = 0
    updated = 0
    skipped = 0
    unchanged = 0

    candidates = rows[: int(limit)] if int(limit or 0) > 0 else rows

    for row in candidates:
        website = (row.get("website") or "").strip()
        existing_email = (row.get("to_email") or "").strip()
        is_directory = _is_directory_url(website)
        is_ambiguous = _is_ambiguous_name(row.get("business_name", ""))

        if not website or is_directory or is_ambiguous:
            skipped += 1
            continue
        if existing_email and not overwrite:
            skipped += 1
            continue

        processed += 1
        details = extract_contact_details_from_website(website)
        email = (details.get("email") or "").strip()
        site_reachable = details.get("site_reachable")

        changed = False
        if email and email != existing_email:
            row["to_email"] = email
            row["contact_method"] = "email"
            changed = True

        for key in ("facebook_url", "instagram_url", "contact_form_url"):
            new_value = (details.get(key) or "").strip()
            if new_value and not (row.get(key) or "").strip():
                row[key] = new_value
                changed = True

        if email or website:
            next_contactability = classify_contactability(
                email=(row.get("to_email") or "").strip(),
                website=website,
                website_reachable=site_reachable,
                is_directory=is_directory,
                is_ambiguous=is_ambiguous,
            )
            if (row.get("contactability") or "").strip() != next_contactability:
                row["contactability"] = next_contactability
                changed = True

            next_channels = _build_social_channels(
                email=(row.get("to_email") or "").strip(),
                fb=(row.get("facebook_url") or "").strip(),
                ig=(row.get("instagram_url") or "").strip(),
                contact_form=(row.get("contact_form_url") or "").strip(),
            )
            if (row.get("social_channels") or "").strip() != next_channels:
                row["social_channels"] = next_channels
                changed = True

        if changed:
            updated += 1
        else:
            unchanged += 1

    if updated > 0:
        _write_rows(path, rows, fieldnames)

    return {
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "unchanged": unchanged,
        "limit": int(limit or 0),
        "overwrite": 1 if overwrite else 0,
    }
