from __future__ import annotations

import argparse
import csv
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List


MAX_DAILY_SEND = 20
DEFAULT_CONTACT_HISTORY_CSV = "lead_engine/data/contact_history.csv"

PENDING_EMAIL_COLUMNS = [
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

CONTACT_HISTORY_COLUMNS = [
    "business_name",
    "website",
    "contacted_date",
    "contact_method",
    "status",
    "notes",
]


def _read_pending_rows(pending_csv_path: str | Path) -> List[Dict[str, str]]:
    path = Path(pending_csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Pending email queue not found: {path}")

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Pending email queue is missing a header row.")
        return [{column: row.get(column, "") for column in PENDING_EMAIL_COLUMNS} for row in reader]


def _write_pending_rows(pending_csv_path: str | Path, rows: List[Dict[str, str]]) -> None:
    path = Path(pending_csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PENDING_EMAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _read_contact_history(path: str | Path) -> List[Dict[str, str]]:
    history_path = Path(path)
    if not history_path.exists():
        return []
    with history_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        return [{column: row.get(column, "") for column in CONTACT_HISTORY_COLUMNS} for row in reader]


def _append_contact_history(path: str | Path, entries: List[Dict[str, str]]) -> None:
    if not entries:
        return

    history_path = Path(path)
    existing = _read_contact_history(history_path)
    existing.extend(entries)

    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONTACT_HISTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(existing)


def _send_email_via_gmail(to_email: str, subject: str, body: str) -> None:
    sender = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not sender or not app_password:
        raise RuntimeError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set for live sends.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)


def _is_send_eligible(row: Dict[str, str]) -> bool:
    approved = (row.get("approved", "").strip().lower() == "true")
    unsent = not (row.get("sent_at") or "").strip()
    has_recipient = bool((row.get("to_email") or "").strip())
    return approved and unsent and has_recipient


def count_sent_today(contact_history_csv: str | Path = DEFAULT_CONTACT_HISTORY_CSV) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    rows = _read_contact_history(contact_history_csv)
    return sum(
        1
        for row in rows
        if (row.get("contacted_date") or "").startswith(today)
        and (row.get("contact_method") or "").strip().lower() == "email"
        and (row.get("status") or "").strip().lower() == "sent"
    )


def process_pending_emails(
    pending_csv_path: str | Path,
    dry_run: bool = True,
    contact_history_csv: str | Path = DEFAULT_CONTACT_HISTORY_CSV,
) -> Dict[str, int]:
    """Process pending queue safely. Dry run by default."""
    rows = _read_pending_rows(pending_csv_path)

    drafted = len(rows)
    eligible_rows = [row for row in rows if _is_send_eligible(row)]
    approved_ready = len(eligible_rows)

    sent_today = count_sent_today(contact_history_csv)
    remaining_cap = max(0, MAX_DAILY_SEND - sent_today)

    sent = 0
    failed = 0
    capped = 0
    history_entries: List[Dict[str, str]] = []

    for idx, row in enumerate(eligible_rows):
        if idx >= remaining_cap:
            capped += 1
            continue

        to_email = (row.get("to_email") or "").strip()
        subject = row.get("subject", "")
        body = row.get("body", "")

        if dry_run:
            print(f"[DRY RUN] Would send to {to_email} | {subject.strip()}")
            continue

        try:
            _send_email_via_gmail(to_email, subject, body)
            sent_at = datetime.now(timezone.utc).isoformat()
            row["sent_at"] = sent_at
            sent += 1
            history_entries.append(
                {
                    "business_name": row.get("business_name", "").strip(),
                    "website": row.get("website", "").strip(),
                    "contacted_date": sent_at,
                    "contact_method": "email",
                    "status": "sent",
                    "notes": "",
                }
            )
        except Exception as exc:
            failed += 1
            print(f"[SEND FAILED] {to_email} | {exc}")

    if not dry_run:
        _write_pending_rows(pending_csv_path, rows)
        _append_contact_history(contact_history_csv, history_entries)

    skipped = drafted - approved_ready
    stats = {
        "drafted": drafted,
        "skipped": skipped,
        "approved_ready": approved_ready,
        "capped": capped,
        "sent": sent,
        "failed": failed,
        "remaining_cap": remaining_cap,
    }
    return stats


def send_approved_emails(
    pending_csv_path: str | Path,
    send_live: bool = False,
    dry_run: bool = True,
    contact_history_csv: str | Path = DEFAULT_CONTACT_HISTORY_CSV,
) -> int:
    """Compatibility wrapper. Never sends live unless send_live=True and dry_run=False."""
    if send_live:
        dry_run = False

    stats = process_pending_emails(pending_csv_path, dry_run=dry_run, contact_history_csv=contact_history_csv)
    if dry_run:
        return 0
    return stats["sent"]


def count_send_eligible_rows(pending_csv_path: str | Path) -> int:
    """Count rows that are approved, unsent, and include recipient email."""
    rows = _read_pending_rows(pending_csv_path)
    return sum(1 for row in rows if _is_send_eligible(row))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending lead_engine email queue.")
    parser.add_argument(
        "--queue",
        default="lead_engine/queue/pending_emails.csv",
        help="Path to pending_emails.csv",
    )
    parser.add_argument(
        "--contact-history",
        default=DEFAULT_CONTACT_HISTORY_CSV,
        help="Path to contact_history.csv",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview sends only (default behavior).",
    )
    parser.add_argument(
        "--send-live",
        action="store_true",
        help="Send live emails for approved+unsent+to_email rows.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    dry_run = True
    if args.send_live:
        dry_run = False
    if args.dry_run:
        dry_run = True

    mode = "DRY RUN" if dry_run else "LIVE SEND"
    print(f"Email sender mode: {mode}")

    stats = process_pending_emails(args.queue, dry_run=dry_run, contact_history_csv=args.contact_history)
    print("Send summary")
    print(f"- drafted: {stats['drafted']}")
    print(f"- skipped: {stats['skipped']}")
    print(f"- approved-ready: {stats['approved_ready']}")
    print(f"- daily-cap-remaining: {stats['remaining_cap']}")
    print(f"- capped: {stats['capped']}")
    print(f"- sent: {stats['sent']}")
    print(f"- failed: {stats['failed']}")

    if not dry_run and stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
