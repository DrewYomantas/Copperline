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


PENDING_COLUMNS = [
    "business_name",
    "city",
    "state",
    "website",
    "phone",
    "contact_method",
    "to_email",
    "subject",
    "body",
    "approved",
    "sent_at",
    "scoring_reason",
    "final_priority_score",
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


def run(input_csv: str | Path = DEFAULT_PROSPECTS_CSV, limit: int = 0, skip_scan: bool = False) -> None:
    input_path = Path(input_csv)
    prospects = load_prospects_from_csv(input_path)
    if limit > 0:
        prospects = prospects[:limit]

    pending_rows = _read_pending_rows(DEFAULT_PENDING_CSV)
    existing_keys: Set[Tuple[str, str]] = {dedupe_key_for_prospect(row) for row in pending_rows}

    drafted = 0
    skipped = 0
    websites_scanned = 0

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

        if not skip_scan and _is_scannable_website(website):
            websites_scanned += 1
            scan_result = scan_website(website)

        final_priority_score, scoring_reason = score_opportunity(prospect, scan_result)

        try:
            subject, body = draft_email(prospect, final_priority_score)
        except ValueError:
            skipped += 1
            continue

        pending_rows.append(
            {
                "business_name": prospect.get("business_name", "").strip(),
                "city": prospect.get("city", "").strip(),
                "state": prospect.get("state", "").strip(),
                "website": website.strip(),
                "phone": prospect.get("phone", "").strip(),
                "contact_method": prospect.get("contact_method", "").strip(),
                "to_email": "",
                "subject": subject,
                "body": body,
                "approved": "false",
                "sent_at": "",
                "scoring_reason": scoring_reason,
                "final_priority_score": str(final_priority_score),
            }
        )
        existing_keys.add(key)
        drafted += 1

    _write_pending_rows(DEFAULT_PENDING_CSV, pending_rows)
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
