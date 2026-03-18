"""
seed_contacted_memory.py
Pass 46 — Seed lead_memory with existing real-sent queue rows.

Reads pending_emails.csv, finds rows where is_real_send() is True,
and records each as 'contacted' in lead_memory.json.

Rows with sent_at but no message_id (logged-only, unconfirmed sends)
are intentionally skipped — only confirmed SMTP sends are seeded.

Usage:
    python lead_engine/scripts/seed_contacted_memory.py           # dry run
    python lead_engine/scripts/seed_contacted_memory.py --write   # commit to memory

Safe to re-run: existing 'contacted' records are not overwritten if
the lead already has a memory entry with any state.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Resolve lead_engine on sys.path regardless of where the script is run from
BASE_DIR = Path(__file__).resolve().parent.parent   # lead_engine/
sys.path.insert(0, str(BASE_DIR))

from send.email_sender_agent import is_real_send
import lead_memory as lm

QUEUE_CSV = BASE_DIR / "queue" / "pending_emails.csv"


def main(dry_run: bool = True) -> None:
    if not QUEUE_CSV.exists():
        print(f"ERROR: queue CSV not found at {QUEUE_CSV}")
        sys.exit(1)

    rows = list(csv.DictReader(QUEUE_CSV.open(encoding="utf-8")))
    real_sent = [r for r in rows if is_real_send(r)]

    print(f"Queue rows      : {len(rows)}")
    print(f"is_real_send    : {len(real_sent)}")
    print(f"Mode            : {'DRY RUN (pass --write to commit)' if dry_run else 'WRITE'}")
    print()

    seeded     = 0
    skipped_existing = 0
    skipped_no_identity = 0

    for r in real_sent:
        key = lm.lead_key(r)

        # Skip rows with no meaningful identity beyond name+city (low-confidence key)
        # All 34 real-sent rows have websites, so this should never trigger in practice.
        if key.startswith("nc:") and not (r.get("website") or r.get("phone")):
            skipped_no_identity += 1
            print(f"  SKIP (weak identity): {r.get('business_name','?')!r} -> key={key}")
            continue

        # If the lead already has any memory entry, don't overwrite.
        # Preserves do_not_contact, hold, or manually set states.
        existing = lm.get_record(r)
        if existing:
            skipped_existing += 1
            print(f"  SKIP (already in memory, state={existing['current_state']!r}): "
                  f"{r.get('business_name','?')!r}")
            continue

        sent_ts = (r.get("sent_at") or "").strip()
        note = f"seeded from queue: sent_at={sent_ts} message_id={(r.get('message_id') or '').strip()[:20]}"
        biz  = r.get("business_name", "?")

        if dry_run:
            print(f"  WOULD SEED: {biz!r:40s}  key={key}  sent={sent_ts[:19]}")
        else:
            lm.record_suppression(r, "contacted", note=note, operator="seed_script")
            print(f"  SEEDED:     {biz!r:40s}  key={key}  sent={sent_ts[:19]}")
        seeded += 1

    print()
    print(f"{'Would seed' if dry_run else 'Seeded'}   : {seeded}")
    print(f"Skipped (already in memory) : {skipped_existing}")
    print(f"Skipped (weak identity)     : {skipped_no_identity}")
    if dry_run:
        print()
        print("Run with --write to commit changes to lead_memory.json.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed contacted memory from sent queue rows.")
    parser.add_argument("--write", action="store_true", help="Commit to lead_memory.json (default: dry run)")
    args = parser.parse_args()
    main(dry_run=not args.write)
