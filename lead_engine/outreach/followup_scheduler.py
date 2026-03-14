"""
Follow-Up Scheduler
Reads prospects.csv, finds rows where sent_at has passed Day 5 or Day 10,
and queues follow-up drafts into pending_emails.csv.

Sequence:
  Day 0  — initial outreach (sent by main pipeline)
  Day 5  — follow-up 1 (this script)
  Day 10 — follow-up 2 / final (this script)

Usage:
  python lead_engine/outreach/followup_scheduler.py
  python lead_engine/outreach/followup_scheduler.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
PROSPECTS_CSV = BASE_DIR / "data" / "prospects.csv"
PENDING_CSV   = BASE_DIR / "queue" / "pending_emails.csv"

FOLLOWUP_DAYS = [5, 10]

PENDING_COLUMNS = [
    "business_name", "city", "state", "website", "phone", "contact_method",
    "industry", "to_email", "subject", "body", "approved", "sent_at",
    "scoring_reason", "final_priority_score",
]

# ── Follow-up copy ────────────────────────────────────────────────────────────

FOLLOWUP_1_SUBJECTS = {
    "plumbing":     "Re: automation idea for {name}",
    "hvac":         "Re: service reminder automation for {name}",
    "electrical":   "Re: lead capture idea for {name}",
    "dental":       "Re: appointment follow-up idea for {name}",
    "salon":        "Re: no-show reduction for {name}",
    "general":      "Re: quick automation idea for {name}",
}

FOLLOWUP_2_SUBJECTS = {
    "plumbing":     "Last note — {name}",
    "hvac":         "Last note — {name}",
    "electrical":   "Last note — {name}",
    "dental":       "Last note — {name}",
    "salon":        "Last note — {name}",
    "general":      "Last note — {name}",
}


def _followup_subject(step: int, industry: str, business_name: str) -> str:
    templates = FOLLOWUP_1_SUBJECTS if step == 1 else FOLLOWUP_2_SUBJECTS
    template = templates.get(industry, templates["general"])
    return template.format(name=business_name)


def _followup_body(step: int, business_name: str, city: str, industry: str) -> str:
    ind = industry.replace("_", " ")
    if step == 1:
        return (
            f"Hi {business_name} team,\n\n"
            f"Just following up on my note from last week about lead follow-up for {ind} businesses in {city}.\n\n"
            f"I help local service businesses stop losing leads after hours and respond faster "
            f"to new enquiries. Happy to send a quick example if that's easier than a call.\n\n"
            "Best,\nDrew\nCopperline"
        )
    else:
        return (
            f"Hi {business_name} team,\n\n"
            f"Last note — I reached out a couple of times about Copperline Lead Follow-Up, "
            f"which helps {ind} businesses in {city} respond to new leads faster and stop losing jobs after hours.\n\n"
            f"If timing isn't right, no worries. Feel free to reach out anytime.\n\n"
            "Best,\nDrew\nCopperline"
        )


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _read_prospects() -> Tuple[List[str], List[Dict]]:
    if not PROSPECTS_CSV.exists():
        return [], []
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def _write_prospects(fieldnames: List[str], rows: List[Dict]) -> None:
    with PROSPECTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_pending() -> List[Dict]:
    if not PENDING_CSV.exists():
        return []
    with PENDING_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        return [{col: row.get(col, "") for col in PENDING_COLUMNS} for row in reader]


def _write_pending(rows: List[Dict]) -> None:
    PENDING_CSV.parent.mkdir(parents=True, exist_ok=True)
    with PENDING_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PENDING_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ── Core logic ────────────────────────────────────────────────────────────────

def _parse_sent_at(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _followup_step_needed(row: Dict, now: datetime) -> Optional[int]:
    """
    Return 1 (Day-5 followup) or 2 (Day-10 followup) if due, else None.
    Checks followup_due field to avoid re-queuing.
    """
    sent_at = _parse_sent_at(row.get("sent_at", ""))
    if not sent_at:
        return None
    if row.get("status", "") not in ("sent", "followup_1_sent"):
        return None

    followup_due = row.get("followup_due", "").strip()
    days_elapsed = (now - sent_at).days

    if row.get("status") == "sent" and days_elapsed >= FOLLOWUP_DAYS[0]:
        return 1
    if row.get("status") == "followup_1_sent" and days_elapsed >= FOLLOWUP_DAYS[1]:
        return 2
    return None


def _already_queued(pending_rows: List[Dict], business_name: str, step: int) -> bool:
    """Check if a follow-up for this business is already in the pending queue."""
    fu_subjects = set(FOLLOWUP_1_SUBJECTS.values()) | set(FOLLOWUP_2_SUBJECTS.values())
    name_lower = business_name.strip().lower()
    for row in pending_rows:
        if row.get("business_name", "").strip().lower() != name_lower:
            continue
        row_subject = row.get("subject", "")
        if any(tmpl.replace("{name}", business_name) == row_subject for tmpl in fu_subjects):
            return True
        scoring = row.get("scoring_reason", "")
        if f"follow-up #{step}" in scoring:
            return True
    return False


def run_followup_scheduler(dry_run: bool = False) -> Dict[str, int]:
    now = datetime.now(timezone.utc)
    fieldnames, prospect_rows = _read_prospects()
    pending_rows = _read_pending()

    # Ensure followup_due + status columns exist
    for col in ("followup_due", "status", "email_sent", "sent_at"):
        if col not in fieldnames:
            fieldnames.append(col)

    queued = 0
    skipped = 0
    updated_prospects = []

    for row in prospect_rows:
        step = _followup_step_needed(row, now)
        if step is None:
            updated_prospects.append(row)
            skipped += 1
            continue

        name     = row.get("business_name", "").strip()
        city     = row.get("city", "").strip()
        industry = row.get("industry", "general").strip() or "general"
        to_email = row.get("to_email", "").strip()

        if _already_queued(pending_rows, name, step):
            updated_prospects.append(row)
            skipped += 1
            continue

        subject = _followup_subject(step, industry, name)
        body    = _followup_body(step, name, city, industry)

        new_pending = {
            "business_name":       name,
            "city":                city,
            "state":               row.get("state", ""),
            "website":             row.get("website", ""),
            "phone":               row.get("phone", ""),
            "contact_method":      row.get("contact_method", ""),
            "industry":            industry,
            "to_email":            to_email,
            "subject":             subject,
            "body":                body,
            "approved":            "false",
            "sent_at":             "",
            "scoring_reason":      f"follow-up #{step}",
            "final_priority_score": row.get("priority_score", ""),
        }

        followup_due_date = (now + timedelta(days=FOLLOWUP_DAYS[step - 1])).date().isoformat()

        if dry_run:
            print(f"[DRY RUN] Step {step} follow-up queued: {name} → {to_email or 'no email'}")
            print(f"          Subject: {subject}")
        else:
            pending_rows.append(new_pending)
            row["followup_due"] = followup_due_date
            queued += 1

        updated_prospects.append(row)

    if not dry_run:
        _write_pending(pending_rows)
        _write_prospects(fieldnames, updated_prospects)

    stats = {"queued": queued, "skipped": skipped}
    return stats


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Queue follow-up emails for sent prospects.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be queued without writing anything.")
    args = parser.parse_args()

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\nFollow-Up Scheduler [{mode}]")
    print(f"  Checking: {PROSPECTS_CSV}\n")

    stats = run_followup_scheduler(dry_run=args.dry_run)

    print(f"\nDone.")
    print(f"  Follow-ups queued : {stats['queued']}")
    print(f"  Rows skipped      : {stats['skipped']}")
    if not args.dry_run and stats["queued"] > 0:
        print(f"\n  → Open dashboard to review and approve follow-ups before sending.")


if __name__ == "__main__":
    main()
