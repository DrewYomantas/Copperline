from __future__ import annotations

import argparse
import csv
import os
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List


# Full 41-column schema — MUST stay in sync with run_lead_engine.PENDING_COLUMNS.
# WARNING: Do NOT shrink this list. _write_pending_rows() uses it as fieldnames,
# so any column omitted here will be permanently stripped from the CSV on the next write.
PENDING_EMAIL_COLUMNS = [
    "business_name", "city", "state", "website", "phone", "contact_method",
    "industry", "to_email", "subject", "body", "approved", "sent_at",
    "approval_reason", "scoring_reason", "final_priority_score", "automation_opportunity",
    "do_not_contact", "draft_version",
    "facebook_url", "instagram_url", "contact_form_url",
    "social_channels", "social_dm_text",
    "facebook_dm_draft", "instagram_dm_draft", "contact_form_message",
    "lead_insight_sentence", "lead_insight_signals", "opportunity_score",
    "last_contact_channel", "last_contacted_at", "contact_attempt_count",
    "contact_result", "next_followup_at", "campaign_key",
    "message_id",     # set after real SMTP send — absence means not truly sent
    "replied", "replied_at", "reply_snippet",
    "conversation_notes", "conversation_next_step",
    "send_after",
]


def is_real_send(row: Dict[str, str]) -> bool:
    """
    A row counts as a REAL send only when BOTH sent_at AND message_id are populated.

    sent_at alone can be set by the dashboard's log_contact action without
    an actual email being sent via SMTP. message_id is only written by
    _send_email_via_gmail(), so its presence is the definitive proof of a send.
    """
    return bool((row.get("sent_at") or "").strip()) and bool((row.get("message_id") or "").strip())


def _read_pending_rows(pending_csv_path: str | Path) -> List[Dict[str, str]]:
    path = Path(pending_csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Pending email queue not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Pending email queue is missing a header row.")
        return [{col: row.get(col, "") for col in PENDING_EMAIL_COLUMNS} for row in reader]


def _write_pending_rows(pending_csv_path: str | Path, rows: List[Dict[str, str]]) -> None:
    path = Path(pending_csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PENDING_EMAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


_SIGNATURE = (
    "\n\n"
    "Drew Yomantas\n"
    "Copperline\n"
    "After-Hours Lead Capture for Service Businesses\n"
    "drewyomantas@gmail.com"
)
_SIGNATURE_ANCHOR = "drewyomantas@gmail.com"


def _append_signature(body: str) -> str:
    if _SIGNATURE_ANCHOR in body:
        return body
    return body + _SIGNATURE


def _send_email_via_gmail(to_email: str, subject: str, body: str) -> str:
    """Send via Gmail SMTP. Returns the Message-ID. Raises on failure."""
    import uuid
    sender      = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not sender or not app_password:
        raise RuntimeError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set.")

    sender_name = os.getenv("SENDER_DISPLAY_NAME", "Drew @ Copperline")
    message_id  = f"<{uuid.uuid4().hex}@copperline.mail>"
    body        = _append_signature(body)

    message = EmailMessage()
    message["From"]       = f"{sender_name} <{sender}>"
    message["To"]         = to_email
    message["Subject"]    = subject
    message["Message-ID"] = message_id
    message.set_content(body)

    html_body = (
        "<html><body style='font-family:Arial,Helvetica,sans-serif;"
        "font-size:14px;color:#1e1e1e;line-height:1.7;max-width:600px'>"
        + body.replace("\n\n", "</p><p>").replace("\n", "<br>")
        + "</p></body></html>"
    )
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)

    return message_id


def _is_send_eligible(row: Dict[str, str]) -> bool:
    """
    A row is eligible to send when:
      - approved = "true"
      - sent_at is empty  (not yet sent or contact-logged)
      - message_id is empty  (not already SMTP-sent — extra safety guard)
      - to_email is present
      - do_not_contact is not "true"
    """
    approved     = row.get("approved", "").strip().lower() == "true"
    no_sent_at   = not (row.get("sent_at") or "").strip()
    no_message_id = not (row.get("message_id") or "").strip()
    has_recipient = bool((row.get("to_email") or "").strip())
    opted_out    = row.get("do_not_contact", "").strip().lower() == "true"
    return approved and no_sent_at and no_message_id and has_recipient and not opted_out


def _update_prospects_sent_status(pending_csv_path: Path, sent_names: set) -> None:
    if not sent_names:
        return
    prospects_csv = Path(pending_csv_path).resolve().parent.parent / "data" / "prospects.csv"
    if not prospects_csv.exists():
        return
    with prospects_csv.open("r", newline="", encoding="utf-8-sig") as f:
        reader    = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows      = list(reader)
    for col in ("email_sent", "sent_at", "status"):
        if col not in fieldnames:
            fieldnames.append(col)
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        name = row.get("business_name", "").strip().lower()
        if name in sent_names:
            row["email_sent"] = "true"
            row["sent_at"]    = now
            row["status"]     = "sent"
    with prospects_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def process_pending_emails(pending_csv_path: str | Path, dry_run: bool = True) -> Dict[str, int]:
    """Process pending queue. dry_run=True by default — never sends unless explicitly False."""
    rows = _read_pending_rows(pending_csv_path)

    drafted       = len(rows)
    approved_ready = sum(1 for r in rows if _is_send_eligible(r))
    real_sent_count = sum(1 for r in rows if is_real_send(r))
    sent   = 0
    failed = 0
    sent_names: set = set()

    for row in rows:
        if not _is_send_eligible(row):
            continue

        to_email = (row.get("to_email") or "").strip()
        subject  = row.get("subject", "")
        body     = row.get("body", "")

        if dry_run:
            print(f"[DRY RUN] Would send to {to_email} | {subject.strip()}")
            continue

        try:
            mid = _send_email_via_gmail(to_email, subject, body)
            row["sent_at"]    = datetime.now(timezone.utc).isoformat()
            row["message_id"] = mid
            sent_names.add((row.get("business_name") or "").strip().lower())
            sent += 1
            send_delay = int(os.getenv("SEND_DELAY_SECONDS", "45"))
            if send_delay > 0:
                print(f"  [rate limit] waiting {send_delay}s before next send...")
                time.sleep(send_delay)
        except Exception as exc:
            failed += 1
            print(f"[SEND FAILED] {to_email} | {exc}")

    if not dry_run:
        _write_pending_rows(pending_csv_path, rows)
        _update_prospects_sent_status(Path(pending_csv_path), sent_names)

    skipped = drafted - approved_ready
    return {
        "drafted":        drafted,
        "skipped":        skipped,
        "approved_ready": approved_ready,
        "real_sent":      real_sent_count,
        "sent":           sent,
        "failed":         failed,
    }


def send_approved_emails(pending_csv_path: str | Path, send_live: bool = False, dry_run: bool = True) -> int:
    if send_live:
        dry_run = False
    stats = process_pending_emails(pending_csv_path, dry_run=dry_run)
    if dry_run:
        return 0
    return stats["sent"]


def count_send_eligible_rows(pending_csv_path: str | Path) -> int:
    rows = _read_pending_rows(pending_csv_path)
    return sum(1 for r in rows if _is_send_eligible(r))


def count_real_sends(pending_csv_path: str | Path) -> int:
    """Count rows confirmed as real SMTP sends (sent_at AND message_id both set)."""
    rows = _read_pending_rows(pending_csv_path)
    return sum(1 for r in rows if is_real_send(r))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending lead_engine email queue.")
    parser.add_argument("--queue", default="lead_engine/queue/pending_emails.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--send-live", action="store_true")
    return parser.parse_args()


def main() -> None:
    args     = _parse_args()
    dry_run  = True
    if args.send_live:
        dry_run = False
    if args.dry_run:
        dry_run = True

    print(f"Email sender mode: {'DRY RUN' if dry_run else 'LIVE SEND'}")
    stats = process_pending_emails(args.queue, dry_run=dry_run)
    print(f"- drafted:        {stats['drafted']}")
    print(f"- approved_ready: {stats['approved_ready']}")
    print(f"- real_sent:      {stats['real_sent']}")
    print(f"- sent_this_run:  {stats['sent']}")
    print(f"- failed:         {stats['failed']}")

    if not dry_run and stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
