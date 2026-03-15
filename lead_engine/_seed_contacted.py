"""
_seed_contacted.py — Seeds known Gmail-contacted businesses into prospects.csv.

Gmail contact list (from operator-provided history):
  All Temp Heating & Cooling
  U.S. Allied Plumbing & HVAC
  Oliphant Lock & Safe
  M Spinello & Son Locksmiths Safe & Security Experts
  I. Spinello Locksmiths & Security Integrators
  24 HR Emergency Plumber Chicago INC
  Power Plumbing & Sewer Contractor, Inc.
  Lopez Plumbing Systems, Inc.
  First Chicago Plumbing
  J Sewer & Drain Plumbing
  Apex Plumbing & Sewer Inc.
  Vanguard Plumbing and Sewer, Inc.
  Goode Plumbing
  Rescue Plumbing
  Total Sewer & Drain
  Handyman Connection of Rockford
  Lars Plumbing

Rules:
  - Never downgrade a higher status (replied > sent > drafted)
  - Set status=sent, email_sent=true if currently blank/new/drafted
  - If business not in prospects.csv, report as NOT_FOUND — do not invent
  - Backup is assumed to have been run already by _backup.py

Status hierarchy: replied(4) > sent(3) > drafted(2) > new(1) > ''(0)
"""
import csv, io, shutil
from datetime import datetime, timezone
from pathlib import Path

BASE          = Path(__file__).resolve().parent
PROSPECTS_CSV = BASE / "data" / "prospects.csv"
SEED_LOG      = BASE / "_backups" / "seed_contact_log.txt"

GMAIL_CONTACTED = [
    "All Temp Heating & Cooling",
    "U.S. Allied Plumbing & HVAC",
    "Oliphant Lock & Safe",
    "M Spinello & Son Locksmiths Safe & Security Experts",
    "I. Spinello Locksmiths & Security Integrators",
    "24 HR Emergency Plumber Chicago INC",
    "Power Plumbing & Sewer Contractor, Inc.",
    "Lopez Plumbing Systems, Inc.",
    "First Chicago Plumbing",
    "J Sewer & Drain Plumbing",
    "Apex Plumbing & Sewer Inc.",
    "Vanguard Plumbing and Sewer, Inc.",
    "Goode Plumbing",
    "Rescue Plumbing",
    "Total Sewer & Drain",
    "Handyman Connection of Rockford",
    "Lars Plumbing",
]

STATUS_RANK = {"replied": 4, "sent": 3, "drafted": 2, "new": 1, "": 0}

def normalize(name: str) -> str:
    return name.lower().strip().replace(",", "").replace(".", "").replace("  ", " ")

def seed():
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = [dict(r) for r in reader]

    # Ensure required columns exist
    for col in ("status", "email_sent", "sent_at", "contact_note"):
        if col not in fieldnames:
            fieldnames.append(col)
            for r in rows: r.setdefault(col, "")

    # Build lookup: normalized_name -> row index list
    lookup: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        key = normalize(r.get("business_name", ""))
        lookup.setdefault(key, []).append(i)

    log_lines = [f"Seed run: {datetime.now(timezone.utc).isoformat()}"]
    log_lines.append(f"{'BUSINESS':<55} {'ACTION'}")
    log_lines.append("-" * 80)

    updated = 0
    not_found = []
    already_higher = []

    now_iso = datetime.now(timezone.utc).isoformat()

    for name in GMAIL_CONTACTED:
        key = normalize(name)
        indices = lookup.get(key, [])

        if not indices:
            not_found.append(name)
            log_lines.append(f"{name:<55} NOT_FOUND in prospects.csv")
            continue

        for idx in indices:
            row = rows[idx]
            current_status = row.get("status", "").strip()
            current_rank   = STATUS_RANK.get(current_status, 0)
            target_rank    = STATUS_RANK["sent"]

            if current_rank >= target_rank:
                already_higher.append(name)
                log_lines.append(f"{name:<55} SKIP (already {current_status!r} >= sent)")
                continue

            # Update
            old_status = current_status
            row["status"]       = "sent"
            row["email_sent"]   = "true"
            if not row.get("sent_at", "").strip():
                row["sent_at"]  = now_iso
            row["contact_note"] = "seeded from Gmail history 2026-03-15"
            updated += 1
            log_lines.append(f"{name:<55} UPDATED ({old_status!r} -> 'sent')")

    # Write back
    with PROSPECTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Write log
    SEED_LOG.parent.mkdir(exist_ok=True)
    log_text = "\n".join(log_lines)
    SEED_LOG.write_text(log_text, encoding="utf-8")

    print(log_text)
    print()
    print(f"Updated:        {updated}")
    print(f"Already higher: {len(already_higher)}")
    print(f"Not found:      {len(not_found)}")
    if not_found:
        print("NOT FOUND list:")
        for n in not_found:
            print(f"  - {n!r}")

if __name__ == "__main__":
    seed()
