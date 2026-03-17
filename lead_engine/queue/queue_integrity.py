"""
queue/queue_integrity.py

Queue health scanner for the Copperline outreach system.
Called by the dashboard /api/queue_health endpoint.

scan_queue_integrity() reads pending_emails.csv and returns a structured
report that the dashboard uses to surface data quality problems immediately.

Checks performed:
  - duplicate_rows         : same dedupe key appears more than once
  - invalid_emails         : to_email present but fails basic format check
  - approved_no_email      : approved=true but to_email is empty
  - sent_no_message_id     : sent_at set but message_id empty (contact-logged, not SMTP-sent)
  - missing_required_fields: business_name, city, or state blank
  - total_rows             : total queue size
  - real_sends             : rows with BOTH sent_at AND message_id (confirmed SMTP sends)
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List

# Import helpers — these must stay consistent with the rest of the pipeline
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from discovery.prospect_discovery_agent import dedupe_key_for_prospect

BASE_DIR    = Path(__file__).resolve().parent.parent
PENDING_CSV = BASE_DIR / "queue" / "pending_emails.csv"

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# Known junk/asset pseudo-emails that slip through naive format checks
_JUNK_EMAIL_FRAGMENTS = (".webp", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".css", ".js")


def _is_valid_email(email: str) -> bool:
    """Basic format check. Returns False for empty, malformed, or asset-filename emails."""
    if not email:
        return False
    if any(frag in email.lower() for frag in _JUNK_EMAIL_FRAGMENTS):
        return False
    return bool(_EMAIL_RE.match(email.strip()))


def _is_real_send(row: Dict[str, str]) -> bool:
    """Confirmed SMTP send = sent_at AND message_id both populated."""
    return bool((row.get("sent_at") or "").strip()) and bool((row.get("message_id") or "").strip())


def _read_queue(csv_path: Path) -> List[Dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        return [dict(row) for row in reader]


def scan_queue_integrity(csv_path: Path = PENDING_CSV) -> Dict:
    """
    Scan the pending queue and return a health report dict.

    Keys returned:
      total_rows            int
      real_sends            int   — sent_at AND message_id set
      contact_logged_only   int   — sent_at set, message_id empty
      duplicate_rows        int   — rows sharing the same dedupe key
      duplicate_details     list  — [{"key": ..., "count": ...}]
      invalid_emails        int
      invalid_email_details list  — [{"business_name": ..., "email": ...}]
      approved_no_email     int
      missing_required      int   — business_name, city, or state blank
      queue_ok              bool  — True when no problems found
    """
    rows = _read_queue(csv_path)

    total              = len(rows)
    real_sends         = 0
    contact_logged     = 0
    invalid_email_rows = []
    approved_no_email  = 0
    missing_required   = 0

    key_counts: Dict[tuple, int] = {}

    for row in rows:
        # Real send vs contact-logged
        has_sent_at    = bool((row.get("sent_at") or "").strip())
        has_message_id = bool((row.get("message_id") or "").strip())
        if has_sent_at and has_message_id:
            real_sends += 1
        elif has_sent_at and not has_message_id:
            contact_logged += 1

        # Email validity
        email = (row.get("to_email") or "").strip()
        if email and not _is_valid_email(email):
            invalid_email_rows.append({
                "business_name": row.get("business_name", ""),
                "email": email,
            })

        # Approved but no email
        if (row.get("approved") or "").strip().lower() == "true" and not email:
            approved_no_email += 1

        # Missing required fields
        if not (row.get("business_name", "").strip() and
                row.get("city", "").strip() and
                row.get("state", "").strip()):
            missing_required += 1

        # Dedupe key tracking
        key = dedupe_key_for_prospect(row)
        key_counts[key] = key_counts.get(key, 0) + 1

    # Duplicate detection
    duplicate_details = [
        {"key": str(k), "count": v}
        for k, v in key_counts.items()
        if v > 1
    ]
    duplicate_count = sum(v - 1 for v in key_counts.values() if v > 1)

    queue_ok = (
        duplicate_count == 0
        and len(invalid_email_rows) == 0
        and approved_no_email == 0
        and missing_required == 0
    )

    return {
        "total_rows":           total,
        "real_sends":           real_sends,
        "contact_logged_only":  contact_logged,
        "duplicate_rows":       duplicate_count,
        "duplicate_details":    duplicate_details[:20],  # cap for API response size
        "invalid_emails":       len(invalid_email_rows),
        "invalid_email_details": invalid_email_rows[:20],
        "approved_no_email":    approved_no_email,
        "missing_required":     missing_required,
        "queue_ok":             queue_ok,
    }


if __name__ == "__main__":
    report = scan_queue_integrity()
    print(f"Queue size:           {report['total_rows']}")
    print(f"Real sends:           {report['real_sends']}")
    print(f"Contact-logged only:  {report['contact_logged_only']}")
    print(f"Duplicate rows:       {report['duplicate_rows']}")
    print(f"Invalid emails:       {report['invalid_emails']}")
    print(f"Approved/no email:    {report['approved_no_email']}")
    print(f"Missing required:     {report['missing_required']}")
    print(f"Queue OK:             {report['queue_ok']}")
    if report["duplicate_details"]:
        print("\nDuplicates:")
        for d in report["duplicate_details"]:
            print(f"  {d['key']}  x{d['count']}")
    if report["invalid_email_details"]:
        print("\nInvalid emails:")
        for e in report["invalid_email_details"]:
            print(f"  {e['business_name']} → {e['email']}")
