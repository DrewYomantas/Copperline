"""
queue/exception_router.py

Exception routing layer for the Copperline outreach queue.
Detects rows that need human attention instead of silent skipping.

detect_row_exceptions(row) -> List[str]
  Returns a list of exception flag strings for a single queue row.
  Empty list = row is clean.

Exception flags:
  INVALID_EMAIL       — to_email present but fails format check
  MISSING_EMAIL       — no to_email at all
  ASSET_EMAIL         — to_email looks like an image/asset filename
  POSSIBLE_DUPLICATE  — dedupe key matches another known key in queue
  PRIOR_CONTACT       — sent_at set but message_id missing (logged only)
  DRAFT_ERROR         — subject or body blank / placeholder text found
  APPROVED_NO_EMAIL   — approved=true but no valid email
  FOLLOWUP_CONFLICT   — next_followup_at set but prior send not confirmed
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from discovery.prospect_discovery_agent import dedupe_key_for_prospect

BASE_DIR    = Path(__file__).resolve().parent.parent
PENDING_CSV = BASE_DIR / "queue" / "pending_emails.csv"

# ── Constants ────────────────────────────────────────────────────────────────

INVALID_EMAIL      = "INVALID_EMAIL"
MISSING_EMAIL      = "MISSING_EMAIL"
ASSET_EMAIL        = "ASSET_EMAIL"
POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
PRIOR_CONTACT      = "PRIOR_CONTACT"
DRAFT_ERROR        = "DRAFT_ERROR"
APPROVED_NO_EMAIL  = "APPROVED_NO_EMAIL"
FOLLOWUP_CONFLICT  = "FOLLOWUP_CONFLICT"

ALL_FLAGS = [
    INVALID_EMAIL, MISSING_EMAIL, ASSET_EMAIL, POSSIBLE_DUPLICATE,
    PRIOR_CONTACT, DRAFT_ERROR, APPROVED_NO_EMAIL, FOLLOWUP_CONFLICT,
]

_EMAIL_RE     = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_ASSET_FRAGS  = (".webp", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".css", ".js")
_PLACEHOLDER  = re.compile(r"\{[a-z_]+\}|PLACEHOLDER|TODO|FIXME|<INSERT|lorem ipsum", re.IGNORECASE)


# ── Email helpers ─────────────────────────────────────────────────────────────

def _is_asset_email(email: str) -> bool:
    e = email.strip().lower()
    for frag in _ASSET_FRAGS:
        bare = frag.lstrip(".")
        if e.endswith(frag) or bare in e.split("@")[-1] if "@" in e else bare in e:
            return True
    return False


def _is_valid_email(email: str) -> bool:
    if not email:
        return False
    if _is_asset_email(email):
        return False
    return bool(_EMAIL_RE.match(email.strip()))


# ── Core exception detector ───────────────────────────────────────────────────

def detect_row_exceptions(
    row: Dict[str, str],
    existing_keys: Set[tuple] | None = None,
) -> List[str]:
    """
    Inspect a single queue row and return all applicable exception flags.

    Parameters:
      row           — dict of pending_emails.csv columns
      existing_keys — optional set of dedupe keys already seen in this pass;
                      if provided, POSSIBLE_DUPLICATE is checked against it.

    Returns:
      List of exception flag strings (empty = row is clean).
    """
    flags: List[str] = []
    email = (row.get("to_email") or "").strip()

    # ── Email exceptions ──────────────────────────────────────────────────
    if not email:
        flags.append(MISSING_EMAIL)
    elif _is_asset_email(email):
        flags.append(ASSET_EMAIL)
    elif not _is_valid_email(email):
        flags.append(INVALID_EMAIL)

    # ── Duplicate check ───────────────────────────────────────────────────
    if existing_keys is not None:
        key = dedupe_key_for_prospect(row)
        if key in existing_keys:
            flags.append(POSSIBLE_DUPLICATE)

    # ── Prior contact without confirmed send ──────────────────────────────
    has_sent_at    = bool((row.get("sent_at") or "").strip())
    has_message_id = bool((row.get("message_id") or "").strip())
    if has_sent_at and not has_message_id:
        flags.append(PRIOR_CONTACT)

    # ── Draft errors ──────────────────────────────────────────────────────
    subject = (row.get("subject") or "").strip()
    body    = (row.get("body") or "").strip()
    if not subject or not body:
        flags.append(DRAFT_ERROR)
    elif _PLACEHOLDER.search(subject) or _PLACEHOLDER.search(body):
        flags.append(DRAFT_ERROR)

    # ── Approved but no valid email ───────────────────────────────────────
    is_approved = (row.get("approved") or "").strip().lower() == "true"
    if is_approved and not _is_valid_email(email):
        if APPROVED_NO_EMAIL not in flags:
            flags.append(APPROVED_NO_EMAIL)

    # ── Follow-up conflict ────────────────────────────────────────────────
    # next_followup_at is set but there's no confirmed real send backing it
    has_followup = bool((row.get("next_followup_at") or "").strip())
    if has_followup and not (has_sent_at and has_message_id):
        flags.append(FOLLOWUP_CONFLICT)

    return flags


# ── Batch scanner ─────────────────────────────────────────────────────────────

def scan_exceptions(csv_path: Path = PENDING_CSV) -> Dict:
    """
    Scan all rows in the pending queue and return:
      total_rows       int
      exception_rows   int  — rows with at least one flag
      counts           dict — {FLAG: count, ...}
      rows             list — [{row fields + "exception_flags": [...]}]

    Rows without any flags are excluded from the "rows" list but counted in total_rows.
    """
    if not csv_path.exists():
        return {"total_rows": 0, "exception_rows": 0, "counts": {f: 0 for f in ALL_FLAGS}, "rows": []}

    raw_rows: List[Dict[str, str]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            raw_rows = [dict(r) for r in reader]

    # Build key set for duplicate detection in a single pass
    key_seen:  Set[tuple] = set()
    key_counts: Dict[tuple, int] = {}
    for row in raw_rows:
        k = dedupe_key_for_prospect(row)
        key_counts[k] = key_counts.get(k, 0) + 1
    duplicate_keys = {k for k, v in key_counts.items() if v > 1}

    counts = {f: 0 for f in ALL_FLAGS}
    exception_rows: List[Dict] = []

    for row in raw_rows:
        flags = detect_row_exceptions(row, existing_keys=duplicate_keys)
        if flags:
            for f in flags:
                counts[f] = counts.get(f, 0) + 1
            exception_rows.append({**row, "exception_flags": flags})

    return {
        "total_rows":     len(raw_rows),
        "exception_rows": len(exception_rows),
        "counts":         counts,
        "rows":           exception_rows,
    }


if __name__ == "__main__":
    report = scan_exceptions()
    print(f"Total rows:      {report['total_rows']}")
    print(f"Exception rows:  {report['exception_rows']}")
    print("\nCounts by flag:")
    for flag, n in report["counts"].items():
        if n:
            print(f"  {flag:<22} {n}")
    if report["rows"]:
        print("\nFirst 5 exception rows:")
        for r in report["rows"][:5]:
            print(f"  {r.get('business_name','')} → {r['exception_flags']}")
