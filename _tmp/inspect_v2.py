"""
V2 Stage 2A — repo inspection before any changes.
Prints queue field names, sample row shapes, and key structural info.
"""
import csv, json, os

BASE = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine"

# Queue fields
with open(os.path.join(BASE, "queue", "pending_emails.csv"), newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    queue_fields = reader.fieldnames
    rows = list(reader)

print("=== QUEUE FIELDS ===")
for i, f in enumerate(queue_fields):
    print(f"  {i+1:2d}. {f}")

print(f"\n  Total rows: {len(rows)}")
print(f"  Sent: {sum(1 for r in rows if r.get('sent_at','').strip())}")
print(f"  With observation: {sum(1 for r in rows if r.get('business_specific_observation','').strip())}")
print(f"  With facebook_url: {sum(1 for r in rows if r.get('facebook_url','').strip())}")

# Prospects fields
with open(os.path.join(BASE, "data", "prospects.csv"), newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    prospect_fields = reader.fieldnames
    prospects = list(reader)

print("\n=== PROSPECT FIELDS ===")
for i, f in enumerate(prospect_fields):
    print(f"  {i+1:2d}. {f}")
print(f"\n  Total prospects: {len(prospects)}")

# Sample queue row — a sent one, shows all fields populated
sent = [r for r in rows if r.get("sent_at","").strip()]
if sent:
    print("\n=== SAMPLE SENT ROW (field: value) ===")
    for k, v in sent[0].items():
        if v.strip():
            print(f"  {k}: {v[:80]!r}")
