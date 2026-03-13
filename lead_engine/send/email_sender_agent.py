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


def process_pending_emails(pending_csv_path: str | Path, dry_run: bool = True) -> Dict[str, int]:
    """Process pending queue safely. Dry run by default."""
    rows = _read_pending_rows(pending_csv_path)

    drafted = len(rows)
    approved_ready = sum(1 for row in rows if _is_send_eligible(row))
    sent = 0
    failed = 0

    for row in rows:
        if not _is_send_eligible(row):
            continue

        to_email = (row.get("to_email") or "").strip()
        subject = row.get("subject", "")
        body = row.get("body", "")

        if dry_run:
            print(f"[DRY RUN] Would send to {to_email} | {subject.strip()}")
            continue

        try:
            _send_email_via_gmail(to_email, subject, body)
            row["sent_at"] = datetime.now(timezone.utc).isoformat()
            sent += 1
        except Exception as exc:
            failed += 1
            print(f"[SEND FAILED] {to_email} | {exc}")

    if not dry_run:
        _write_pending_rows(pending_csv_path, rows)

    skipped = drafted - approved_ready
    stats = {
        "drafted": drafted,
        "skipped": skipped,
        "approved_ready": approved_ready,
        "sent": sent,
        "failed": failed,
    }
    return stats


def send_approved_emails(pending_csv_path: str | Path, send_live: bool = False, dry_run: bool = True) -> int:
    """Compatibility wrapper. Never sends live unless send_live=True and dry_run=False."""
    if send_live:
        dry_run = False

    stats = process_pending_emails(pending_csv_path, dry_run=dry_run)
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

    stats = process_pending_emails(args.queue, dry_run=dry_run)
    print("Send summary")
    print(f"- drafted: {stats['drafted']}")
    print(f"- skipped: {stats['skipped']}")
    print(f"- approved-ready: {stats['approved_ready']}")
    print(f"- sent: {stats['sent']}")
    print(f"- failed: {stats['failed']}")

    if not dry_run and stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
