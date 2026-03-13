from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse

from discovery.prospect_discovery_agent import (
    dedupe_key_for_prospect,
    discover_prospects_by_industry,
    load_prospects_from_csv,
)
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

CONTACT_FORM_COLUMNS = [
    "business_name",
    "city",
    "state",
    "website",
    "phone",
    "contact_method",
    "contact_page_url",
    "approved",
    "submitted_at",
    "notes",
    "scoring_reason",
    "final_priority_score",
]

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PROSPECTS_CSV = BASE_DIR / "data" / "prospects.csv"
DEFAULT_PENDING_CSV = BASE_DIR / "queue" / "pending_emails.csv"
DEFAULT_CONTACT_FORM_QUEUE_CSV = BASE_DIR / "queue" / "pending_contact_forms.csv"
DEFAULT_CONTACT_HISTORY_CSV = BASE_DIR / "data" / "contact_history.csv"


def _read_rows(path: Path, columns: List[str]) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        return [{column: row.get(column, "") for column in columns} for row in reader]


def _write_rows(path: Path, rows: List[Dict[str, str]], columns: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _is_scannable_website(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lead_engine CSV-to-draft pipeline.")
    parser.add_argument("--input", default=str(DEFAULT_PROSPECTS_CSV), help="Path to prospects CSV")
    parser.add_argument("--discover", default="", help="Industry to discover (e.g., HVAC)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of prospect rows processed")
    parser.add_argument("--city", default="", help='Seed city for discovery, e.g. "Chicago, IL"')
    parser.add_argument("--skip-scan", action="store_true", help="Skip website fetch/scan step")
    return parser.parse_args()


def _empty_scan_result() -> Dict[str, object]:
    return {
        "website_reachable": False,
        "scanned_urls": [],
        "has_contact_form": False,
        "has_email_visible": False,
        "has_phone_visible": False,
        "has_chat_widget": False,
        "has_online_booking_keywords": False,
        "has_request_quote_cta": False,
        "has_schedule_service_cta": False,
        "mobile_friendly_hint": False,
        "weak_website_signals": [],
        "positive_conversion_signals": [],
    }


def run(
    input_csv: str | Path = DEFAULT_PROSPECTS_CSV,
    discover: str = "",
    limit: int = 0,
    city: str = "",
    skip_scan: bool = False,
) -> Dict[str, int | str]:
    input_path = Path(input_csv)

    if discover.strip():
        prospects = discover_prospects_by_industry(
            industry=discover.strip(),
            limit=limit if limit > 0 else 30,
            seed_city=city or None,
            existing_prospects_csv=input_path,
            contact_history_csv=DEFAULT_CONTACT_HISTORY_CSV,
        )
        discovered = len(prospects)
    else:
        prospects = load_prospects_from_csv(input_path)
        if limit > 0:
            prospects = prospects[:limit]
        discovered = 0

    pending_rows = _read_rows(DEFAULT_PENDING_CSV, PENDING_COLUMNS)
    contact_form_rows = _read_rows(DEFAULT_CONTACT_FORM_QUEUE_CSV, CONTACT_FORM_COLUMNS)
    unsent_keys: Set[Tuple[str, str]] = set()
    sent_keys: Set[Tuple[str, str]] = set()
    contact_form_keys: Set[Tuple[str, str]] = set()

    for row in pending_rows:
        key = dedupe_key_for_prospect(row)
        if (row.get("sent_at") or "").strip():
            sent_keys.add(key)
        else:
            unsent_keys.add(key)

    for row in contact_form_rows:
        if not (row.get("submitted_at") or "").strip():
            contact_form_keys.add(dedupe_key_for_prospect(row))

    drafted = 0
    contact_form_queued = 0
    skipped_invalid_or_duplicate = 0
    skipped_existing_unsent = 0
    skipped_existing_sent = 0
    websites_scanned = 0

    for prospect in prospects:
        key = dedupe_key_for_prospect(prospect)
        if not key[0]:
            skipped_invalid_or_duplicate += 1
            print("[skip] missing business identity")
            continue

        if key in unsent_keys:
            skipped_existing_unsent += 1
            print(f"[skip] already queued unsent: {prospect.get('business_name', '').strip()}")
            continue

        if key in sent_keys:
            skipped_existing_sent += 1
            print(f"[skip] already sent previously: {prospect.get('business_name', '').strip()}")
            continue

        website = prospect.get("website", "")
        scan_result = _empty_scan_result()

        if not skip_scan and _is_scannable_website(website):
            websites_scanned += 1
            scan_result = scan_website(website)

        final_priority_score, scoring_reason = score_opportunity(prospect, scan_result)

        try:
            subject, body = draft_email(prospect, final_priority_score)
        except ValueError:
            skipped_invalid_or_duplicate += 1
            print(f"[skip] missing draft fields: {prospect.get('business_name', '').strip()}")
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
        unsent_keys.add(key)
        drafted += 1

        likely_contact_page = ""
        scanned_urls = scan_result.get("scanned_urls", []) if isinstance(scan_result, dict) else []
        if isinstance(scanned_urls, list):
            likely_contact_page = next((u for u in scanned_urls if "/contact" in u.lower()), "")

        if (
            not (scan_result.get("has_email_visible", False) if isinstance(scan_result, dict) else False)
            and (
                (scan_result.get("has_contact_form", False) if isinstance(scan_result, dict) else False)
                or bool(likely_contact_page)
            )
            and key not in contact_form_keys
        ):
            contact_form_rows.append(
                {
                    "business_name": prospect.get("business_name", "").strip(),
                    "city": prospect.get("city", "").strip(),
                    "state": prospect.get("state", "").strip(),
                    "website": website.strip(),
                    "phone": prospect.get("phone", "").strip(),
                    "contact_method": "contact_form",
                    "contact_page_url": likely_contact_page,
                    "approved": "false",
                    "submitted_at": "",
                    "notes": "",
                    "scoring_reason": scoring_reason,
                    "final_priority_score": str(final_priority_score),
                }
            )
            contact_form_keys.add(key)
            contact_form_queued += 1

    _write_rows(DEFAULT_PENDING_CSV, pending_rows, PENDING_COLUMNS)
    _write_rows(DEFAULT_CONTACT_FORM_QUEUE_CSV, contact_form_rows, CONTACT_FORM_COLUMNS)
    approved_ready = count_send_eligible_rows(DEFAULT_PENDING_CSV)
    skipped_total = skipped_invalid_or_duplicate + skipped_existing_unsent + skipped_existing_sent

    stats: Dict[str, int | str] = {
        "input": str(input_path),
        "discover": discover or "none",
        "discovered": discovered,
        "loaded": len(prospects),
        "scanned": websites_scanned,
        "drafted": drafted,
        "contact_form_queued": contact_form_queued,
        "skipped": skipped_total,
        "approved_ready": approved_ready,
        "queued_email": len(pending_rows),
        "queued_contact_forms": len(contact_form_rows),
    }

    print(
        "RUN SUMMARY "
        f"input={stats['input']} discover={stats['discover']} discovered={stats['discovered']} loaded={stats['loaded']} "
        f"scanned={stats['scanned']} drafted={stats['drafted']} contact-form-queued={stats['contact_form_queued']} "
        f"skipped={stats['skipped']} approved-ready={stats['approved_ready']} queue={DEFAULT_PENDING_CSV}"
    )

    return stats


def main() -> None:
    args = _parse_args()
    run(input_csv=args.input, discover=args.discover, limit=args.limit, city=args.city, skip_scan=args.skip_scan)


if __name__ == "__main__":
    main()
