"""
_seed_missing.py — Adds the 5 Gmail-contacted businesses that don't exist in
prospects.csv. These were contacted via Gmail but never added to the discovery
pipeline. Adds them with status=sent so they won't be redrafted.

Businesses to add:
  All Temp Heating & Cooling          (HVAC — Rockford area assumed)
  U.S. Allied Plumbing & HVAC         (plumbing/hvac)
  Oliphant Lock & Safe                (locksmith)
  M Spinello & Son Locksmiths Safe & Security Experts  (locksmith)
  I. Spinello Locksmiths & Security Integrators        (locksmith)

Note: city/state/contact details are UNKNOWN — these businesses were contacted
outside the current discovery pipeline. Minimal safe rows are added with
contact_note='seeded from Gmail history - details unknown'.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path

BASE          = Path(__file__).resolve().parent
PROSPECTS_CSV = BASE / "data" / "prospects.csv"

NOW_ISO = datetime.now(timezone.utc).isoformat()

MISSING_BUSINESSES = [
    {"business_name": "All Temp Heating & Cooling",                           "industry": "hvac"},
    {"business_name": "U.S. Allied Plumbing & HVAC",                          "industry": "plumbing"},
    {"business_name": "Oliphant Lock & Safe",                                  "industry": "locksmith"},
    {"business_name": "M Spinello & Son Locksmiths Safe & Security Experts",  "industry": "locksmith"},
    {"business_name": "I. Spinello Locksmiths & Security Integrators",        "industry": "locksmith"},
]

def add_missing():
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        reader    = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows      = [dict(r) for r in reader]

    for col in ("contact_note",):
        if col not in fieldnames:
            fieldnames.append(col)

    # Normalize check — confirm none already exist
    existing_names = {r.get("business_name","").lower().strip() for r in rows}

    added = 0
    for biz in MISSING_BUSINESSES:
        name = biz["business_name"]
        if name.lower().strip() in existing_names:
            print(f"  ALREADY EXISTS (skip): {name}")
            continue

        new_row = {col: "" for col in fieldnames}
        new_row.update({
            "business_name": name,
            "city":          "",
            "state":         "IL",
            "industry":      biz["industry"],
            "status":        "sent",
            "email_sent":    "true",
            "sent_at":       NOW_ISO,
            "contact_note":  "seeded from Gmail history - details unknown",
        })
        rows.append(new_row)
        added += 1
        print(f"  ADDED: {name!r} (industry={biz['industry']}, status=sent)")

    with PROSPECTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nAdded {added} missing businesses to prospects.csv")
    print(f"Total rows now: {len(rows)}")

if __name__ == "__main__":
    add_missing()
