"""
_reset_drafted.py — Resets drafted prospects to new, safely.

Rules:
  - drafted -> new ONLY
  - sent/replied/seeded rows: untouched
  - new rows: already new, skip
  - Prints exact counts before/after
"""
import csv
from pathlib import Path

BASE          = Path(__file__).resolve().parent
PROSPECTS_CSV = BASE / "data" / "prospects.csv"

# Gmail-contacted names — these must NEVER be downgraded even if currently 'drafted'
# (belt-and-suspenders: seed script already set them to sent, but guard here too)
PROTECTED = {
    "all temp heating & cooling", "u.s. allied plumbing & hvac",
    "oliphant lock & safe",
    "m spinello & son locksmiths safe & security experts",
    "i. spinello locksmiths & security integrators",
    "24 hr emergency plumber chicago inc", "power plumbing & sewer contractor inc",
    "lopez plumbing systems inc", "first chicago plumbing",
    "j sewer & drain plumbing", "apex plumbing & sewer inc",
    "vanguard plumbing and sewer inc", "goode plumbing",
    "rescue plumbing", "total sewer & drain",
    "handyman connection of rockford", "lars plumbing",
    "dee's plumbing & construction inc",
}

def normalize(name):
    return name.lower().strip().replace(",","").replace(".","").replace("  "," ")

def reset():
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = [dict(r) for r in reader]

    before = {}
    for r in rows:
        s = r.get("status","")
        before[s] = before.get(s,0) + 1
    print("Before:", before)

    reset_count   = 0
    skipped_prot  = 0
    skipped_other = 0

    for row in rows:
        status = row.get("status","").strip()
        name   = normalize(row.get("business_name",""))

        if status != "drafted":
            skipped_other += 1
            continue

        if name in PROTECTED:
            skipped_prot += 1
            print(f"  PROTECTED (skip reset): {row['business_name']!r}")
            continue

        row["status"] = "new"
        reset_count += 1

    with PROSPECTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    after = {}
    for r in rows:
        s = r.get("status","")
        after[s] = after.get(s,0) + 1
    print("After: ", after)
    print(f"Reset:          {reset_count} (drafted -> new)")
    print(f"Skipped prot:   {skipped_prot}")
    print(f"Skipped other:  {skipped_other} (non-drafted rows untouched)")

if __name__ == "__main__":
    reset()
