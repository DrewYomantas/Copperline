from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse

from discovery.prospect_discovery_agent import dedupe_key_for_prospect, load_prospects_from_csv
from intelligence.website_scan_agent import scan_website
from outreach.email_draft_agent import draft_email
from scoring.opportunity_scoring_agent import score_opportunity
from send.email_sender_agent import count_send_eligible_rows
from datetime import date, timedelta


PENDING_COLUMNS = [
    "business_name",
    "city",
    "state",
    "website",
    "phone",
    "contact_method",
    "industry",
    "to_email",
    "subject",
    "body",
    "approved",
    "sent_at",
    "scoring_reason",
    "final_priority_score",
    "automation_opportunity",
    "do_not_contact",
]


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PROSPECTS_CSV = BASE_DIR / "data" / "prospects.csv"
DEFAULT_PENDING_CSV = BASE_DIR / "queue" / "pending_emails.csv"


def _read_pending_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        return [{column: row.get(column, "") for column in PENDING_COLUMNS} for row in reader]


def _write_pending_rows(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PENDING_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _is_scannable_website(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lead_engine CSV-to-draft pipeline.")
    parser.add_argument("--input", default=str(DEFAULT_PROSPECTS_CSV), help="Path to prospects CSV")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of prospect rows processed")
    parser.add_argument("--skip-scan", action="store_true", help="Skip website fetch/scan step")
    return parser.parse_args()


def _update_prospect_status(input_path: Path, drafted_names: Set[str]) -> None:
    """Mark drafted prospects with status=drafted in prospects.csv."""
    if not input_path.exists() or not drafted_names:
        return
    with input_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Ensure status column exists
    if "status" not in fieldnames:
        fieldnames.append("status")

    for row in rows:
        name = row.get("business_name", "").strip().lower()
        if name in drafted_names and row.get("status", "") == "new":
            row["status"] = "drafted"

    with input_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(input_csv: str | Path = DEFAULT_PROSPECTS_CSV, limit: int = 0, skip_scan: bool = False) -> None:
    input_path = Path(input_csv)
    prospects = load_prospects_from_csv(input_path)
    if limit > 0:
        prospects = prospects[:limit]

    # Only process prospects that haven't been drafted or sent yet
    prospects = [
        p for p in prospects
        if p.get("status", "new") in ("", "new")
    ]

    pending_rows = _read_pending_rows(DEFAULT_PENDING_CSV)
    existing_keys: Set[Tuple[str, str]] = {dedupe_key_for_prospect(row) for row in pending_rows}

    drafted = 0
    skipped = 0
    websites_scanned = 0
    drafted_names: Set[str] = set()

    for prospect in prospects:
        key = dedupe_key_for_prospect(prospect)
        if not key[0] or key in existing_keys:
            skipped += 1
            continue

        website = prospect.get("website", "")
        scan_result = {
            "has_contact_form": False,
            "has_chat_widget": False,
            "has_online_booking_keywords": False,
            "has_email_visible": False,
        }

        # Skip re-scanning if this prospect was already scanned (has automation_opportunity set)
        already_scanned = bool((prospect.get("automation_opportunity") or "").strip())
        if not skip_scan and not already_scanned and _is_scannable_website(website):
            websites_scanned += 1
            scan_result = scan_website(website)
        elif already_scanned:
            # Reuse stored signals so scoring stays consistent
            scan_result["automation_opportunity"] = prospect.get("automation_opportunity", "unknown")

        final_priority_score, scoring_reason = score_opportunity(prospect, scan_result)

        try:
            subject, body = draft_email(prospect, final_priority_score)
        except ValueError:
            skipped += 1
            continue

        # Pull email already found during discovery (no re-scrape needed)
        to_email = prospect.get("to_email", "").strip()

        pending_rows.append(
            {
                "business_name": prospect.get("business_name", "").strip(),
                "city": prospect.get("city", "").strip(),
                "state": prospect.get("state", "").strip(),
                "website": website.strip(),
                "phone": prospect.get("phone", "").strip(),
                "contact_method": prospect.get("contact_method", "").strip(),
                "industry": prospect.get("industry", "").strip(),
                "to_email": to_email,
                "subject": subject,
                "body": body,
                "approved": "false",
                "sent_at": "",
                "scoring_reason": scoring_reason,
                "final_priority_score": str(final_priority_score),
                "automation_opportunity": scan_result.get("automation_opportunity", "unknown"),
                "do_not_contact": prospect.get("do_not_contact", ""),
            }
        )
        existing_keys.add(key)
        drafted_names.add(prospect.get("business_name", "").strip().lower())
        drafted += 1

    _write_pending_rows(DEFAULT_PENDING_CSV, pending_rows)

    # Write status=drafted back to prospects.csv so re-runs skip these
    _update_prospect_status(input_path, drafted_names)

    approved_ready = count_send_eligible_rows(DEFAULT_PENDING_CSV)

    print(
        "RUN SUMMARY "
        f"input={input_path} loaded={len(prospects)} scanned={websites_scanned} "
        f"drafted={drafted} skipped={skipped} approved-ready={approved_ready} "
        f"queue={DEFAULT_PENDING_CSV}"
    )


def main() -> None:
    args = _parse_args()
    run(input_csv=args.input, limit=args.limit, skip_scan=args.skip_scan)


if __name__ == "__main__":
    main()
