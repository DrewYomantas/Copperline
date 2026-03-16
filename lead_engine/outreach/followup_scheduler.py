"""
outreach/followup_scheduler.py

Follow-Up Auto-Draft Generator.
Reads pending_emails.csv (source of truth for sent state), finds rows
that are due for a follow-up, and writes new draft rows to the queue.

Rules (all must pass before a follow-up is drafted):
  1. Prior real send confirmed  — sent_at AND message_id both populated
  2. No reply logged            — replied != "true"
  3. Follow-up is due           — next_followup_at <= now  OR
                                   (next_followup_at empty AND sent_at >= N days ago)
  4. Follow-up count under cap  — contact_attempt_count < FOLLOWUP_CAP
  5. Valid email present        — to_email passes format check
  6. No active exception flags  — detect_row_exceptions() returns empty list
  7. Not already queued         — no unsent follow-up draft exists in queue
     for same business (checked via dedupe key)

Drafts are written with approved="false" — operator must approve before send.
Auto-send is NOT enabled.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR    = Path(__file__).resolve().parent.parent
PENDING_CSV = BASE_DIR / "queue" / "pending_emails.csv"

# Import helpers via sys.path (queue/ conflicts with stdlib so we insert path)
sys.path.insert(0, str(BASE_DIR))
from send.email_sender_agent import is_real_send
from discovery.prospect_discovery_agent import dedupe_key_for_prospect

# Load exception_router via importlib to avoid stdlib 'queue' collision
import importlib.util as _ilu
_er_spec = _ilu.spec_from_file_location("exception_router", BASE_DIR / "queue" / "exception_router.py")
_er_mod  = _ilu.module_from_spec(_er_spec)
_er_spec.loader.exec_module(_er_mod)
detect_row_exceptions = _er_mod.detect_row_exceptions

# ── Configuration ─────────────────────────────────────────────────────────────
FOLLOWUP_CAP          = 2       # max follow-ups per prospect before giving up
FOLLOWUP_DAYS_DEFAULT = 7       # days after real send before first follow-up
FOLLOWUP_DAYS_SECOND  = 14      # days after real send before second follow-up
SEND_WINDOW_START     = 8       # local hour window start (inclusive)
SEND_WINDOW_END       = 18      # local hour window end (exclusive)

_EMAIL_RE    = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_ASSET_FRAGS = (".webp",".png",".jpg",".jpeg",".svg",".gif",".css",".js")

PENDING_COLUMNS = [
    "business_name","city","state","website","phone","contact_method",
    "industry","to_email","subject","body","approved","sent_at",
    "approval_reason","scoring_reason","final_priority_score","automation_opportunity",
    "do_not_contact","draft_version",
    "facebook_url","instagram_url","contact_form_url","social_channels","social_dm_text",
    "facebook_dm_draft","instagram_dm_draft","contact_form_message",
    "lead_insight_sentence","lead_insight_signals","opportunity_score",
    "last_contact_channel","last_contacted_at","contact_attempt_count",
    "contact_result","next_followup_at","campaign_key",
    "message_id","replied","replied_at","reply_snippet",
    "conversation_notes","conversation_next_step",
    "send_after",
]

# ── Follow-up copy ─────────────────────────────────────────────────────────────
def _followup_subject(step: int, business_name: str) -> str:
    if step == 1: return "Re: quick question"
    return "last note"

def _followup_body(step: int, business_name: str, city: str, industry: str) -> str:
    ind = industry.replace("_"," ")
    if step == 1:
        return (
            f"Hi {business_name},\n\n"
            f"Just following up on my note from last week about missed calls for {ind} businesses in {city}.\n\n"
            f"I set up a simple text-back line so missed callers get an instant reply — "
            f"happy to show you a quick example if that's easier.\n\n"
            "– Drew"
        )
    return (
        f"Hi {business_name},\n\n"
        f"Last note — I reached out a couple of times about helping {ind} businesses in {city} "
        f"stay on top of after-hours calls.\n\n"
        f"If the timing isn't right, no worries at all. Feel free to reach out any time.\n\n"
        "– Drew"
    )

# ── CSV helpers ────────────────────────────────────────────────────────────────
def _read_pending() -> List[Dict]:
    if not PENDING_CSV.exists(): return []
    with PENDING_CSV.open("r",newline="",encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames: return []
        return [{col: row.get(col,"") for col in PENDING_COLUMNS} for row in reader]

def _write_pending(rows: List[Dict]) -> None:
    PENDING_CSV.parent.mkdir(parents=True,exist_ok=True)
    with PENDING_CSV.open("w",newline="",encoding="utf-8") as f:
        writer = csv.DictWriter(f,fieldnames=PENDING_COLUMNS)
        writer.writeheader()
        writer.writerows([{col: r.get(col,"") for col in PENDING_COLUMNS} for r in rows])

# ── Eligibility helpers ────────────────────────────────────────────────────────
def _valid_email(email: str) -> bool:
    if not email: return False
    e = email.strip().lower()
    if any(f in e for f in _ASSET_FRAGS): return False
    return bool(_EMAIL_RE.match(e))

def _parse_dt(value: str) -> Optional[datetime]:
    if not value: return None
    try: return datetime.fromisoformat(value.replace("Z","+00:00"))
    except: return None

def _followup_step(row: Dict, now: datetime) -> Optional[int]:
    """
    Return which follow-up step (1 or 2) is due for this row, or None.
    Based on contact_attempt_count and time elapsed since real send.
    """
    sent_dt = _parse_dt(row.get("sent_at",""))
    if not sent_dt: return None
    days_elapsed = (now - sent_dt).days
    try: attempts = int(row.get("contact_attempt_count") or 0)
    except: attempts = 0
    if attempts == 0 and days_elapsed >= FOLLOWUP_DAYS_DEFAULT: return 1
    if attempts == 1 and days_elapsed >= FOLLOWUP_DAYS_SECOND:  return 2
    return None

def followup_eligible(row: Dict, now: datetime, existing_keys: set) -> Tuple[bool, str]:
    """
    Check whether a queue row is eligible for a follow-up draft.

    Returns (eligible: bool, reason: str).
    'reason' is empty string when eligible, or a short skip reason.

    Checks:
      1. Real send confirmed (sent_at + message_id)
      2. No reply logged
      3. Follow-up step is due
      4. contact_attempt_count < FOLLOWUP_CAP
      5. Valid email present
      6. No active exception flags
      7. Not already queued (dedupe key not in existing_keys for unsent rows)
    """
    # 1. Real send
    if not is_real_send(row):
        return False, "no_real_send"

    # 2. No reply
    if row.get("replied","").strip().lower() == "true":
        return False, "already_replied"

    # 3. Step due
    step = _followup_step(row, now)
    if step is None:
        return False, "not_due_yet"

    # 4. Under cap
    try: attempts = int(row.get("contact_attempt_count") or 0)
    except: attempts = 0
    if attempts >= FOLLOWUP_CAP:
        return False, "cap_reached"

    # 5. Valid email
    if not _valid_email(row.get("to_email","")):
        return False, "no_valid_email"

    # 6. No exception flags
    flags = detect_row_exceptions(row)
    active = [f for f in flags if f not in ("PRIOR_CONTACT","FOLLOWUP_CONFLICT")]
    if active:
        return False, f"exceptions:{','.join(active)}"

    # 7. Not already queued as unsent follow-up
    key = dedupe_key_for_prospect(row)
    if key in existing_keys:
        return False, "already_queued"

    return True, ""

# ── Core runner ────────────────────────────────────────────────────────────────
def run_followup_scheduler(dry_run: bool = False) -> Dict:
    """
    Scan pending_emails.csv for rows eligible for follow-up drafts.
    Write new draft rows (approved=false) for each eligible row.

    Returns stats dict:
      queued     int — new follow-up drafts written
      skipped    int — rows checked but ineligible
      skip_reasons dict — {reason: count}
    """
    if not dry_run:
        from datetime import datetime as _dt
        local_hour = _dt.now().hour
        if not (SEND_WINDOW_START <= local_hour < SEND_WINDOW_END):
            print(f"  [scheduler] Outside send window ({SEND_WINDOW_START}:00–{SEND_WINDOW_END}:00). Skipping.")
            return {"queued": 0, "skipped": 0, "skip_reasons": {}}

    now  = datetime.now(timezone.utc)
    rows = _read_pending()

    # Build set of dedupe keys for UNSENT rows only
    # (rows without sent_at are still in draft state — don't create more drafts for same business)
    unsent_keys = {
        dedupe_key_for_prospect(r)
        for r in rows
        if not (r.get("sent_at") or "").strip()
    }

    queued       = 0
    skipped      = 0
    skip_reasons: Dict[str, int] = {}
    new_rows: List[Dict] = []

    for row in rows:
        # Only consider rows with a confirmed real send as candidates
        if not is_real_send(row):
            continue

        eligible, reason = followup_eligible(row, now, unsent_keys)
        if not eligible:
            skipped += 1
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue

        step     = _followup_step(row, now)  # guaranteed non-None here
        name     = row.get("business_name","").strip()
        city     = row.get("city","").strip()
        industry = (row.get("industry","") or "general").strip()
        to_email = row.get("to_email","").strip()

        subject  = _followup_subject(step, name)
        body     = _followup_body(step, name, city, industry)

        try: attempts = int(row.get("contact_attempt_count") or 0)
        except: attempts = 0

        new_draft = {col: "" for col in PENDING_COLUMNS}
        new_draft.update({
            "business_name":         name,
            "city":                  city,
            "state":                 row.get("state",""),
            "website":               row.get("website",""),
            "phone":                 row.get("phone",""),
            "contact_method":        row.get("contact_method",""),
            "industry":              industry,
            "to_email":              to_email,
            "subject":               subject,
            "body":                  body,
            "approved":              "false",
            "sent_at":               "",
            "approval_reason":       "",
            "scoring_reason":        f"follow-up #{step}",
            "final_priority_score":  row.get("final_priority_score",""),
            "automation_opportunity": row.get("automation_opportunity",""),
            "do_not_contact":        row.get("do_not_contact",""),
            "draft_version":         row.get("draft_version",""),
            "contact_attempt_count": str(attempts),  # carry forward count
            "campaign_key":          row.get("campaign_key",""),
            "opportunity_score":     row.get("opportunity_score",""),
        })

        if dry_run:
            print(f"[DRY RUN] step={step} | {name} → {to_email} | {subject}")
        else:
            new_rows.append(new_draft)
            # Add the new draft's key to unsent_keys so same-run duplicates are blocked
            unsent_keys.add(dedupe_key_for_prospect(new_draft))
            queued += 1

    if not dry_run and new_rows:
        all_rows = rows + new_rows
        _write_pending(all_rows)

    stats = {"queued": queued, "skipped": skipped, "skip_reasons": skip_reasons}
    return stats

# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate follow-up drafts for sent prospects.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    args = parser.parse_args()
    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\nFollow-Up Scheduler [{mode}]\n  Queue: {PENDING_CSV}\n")
    stats = run_followup_scheduler(dry_run=args.dry_run)
    print(f"\nDone.")
    print(f"  Queued : {stats['queued']}")
    print(f"  Skipped: {stats['skipped']}")
    if stats["skip_reasons"]:
        print("  Skip reasons:")
        for r,n in stats["skip_reasons"].items():
            print(f"    {r}: {n}")
    if not args.dry_run and stats["queued"] > 0:
        print(f"\n  → Open dashboard to review and approve follow-ups.")

if __name__ == "__main__":
    main()
