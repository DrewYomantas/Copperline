"""
Pass 38 — Safe bulk unschedule of pre-Pass-36 scheduled rows.
Backs up state files, clears send_after only, verifies counts, reports exactly.
"""
import csv, os, shutil, sys
from datetime import datetime

BASE   = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation"
QUEUE  = os.path.join(BASE, "lead_engine", "queue", "pending_emails.csv")
BACKUP_DIR = os.path.join(BASE, "_backups")

os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# ── 1. Backup ────────────────────────────────────────────────────────────────
backup_queue = os.path.join(BACKUP_DIR, f"pending_emails_pre_p38_{ts}.csv")
shutil.copy2(QUEUE, backup_queue)
print(f"Backup: {backup_queue}")

# ── 2. Read ──────────────────────────────────────────────────────────────────
with open(QUEUE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

total_before      = len(rows)
scheduled_before  = [r for r in rows if r.get("send_after","").strip() and not r.get("sent_at","").strip()]
sent_rows         = [r for r in rows if r.get("sent_at","").strip()]

print(f"\nBefore:")
print(f"  total rows          : {total_before}")
print(f"  sent rows           : {len(sent_rows)}")
print(f"  scheduled+unsent    : {len(scheduled_before)}")
print(f"  unscheduled+unsent  : {total_before - len(sent_rows) - len(scheduled_before)}")

# ── 3. Apply: clear send_after on scheduled+unsent only ─────────────────────
cleared = []
for r in rows:
    is_scheduled = r.get("send_after", "").strip()
    is_sent      = r.get("sent_at", "").strip()
    if is_scheduled and not is_sent:
        cleared.append({
            "business_name": r["business_name"],
            "send_after":    r["send_after"],
            "approved":      r.get("approved",""),
            "draft_version": r.get("draft_version",""),
        })
        r["send_after"] = ""   # only field touched

# ── 4. Write ─────────────────────────────────────────────────────────────────
with open(QUEUE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

# ── 5. Verify ────────────────────────────────────────────────────────────────
with open(QUEUE, newline="", encoding="utf-8") as f:
    rows_after = list(csv.DictReader(f))

total_after      = len(rows_after)
scheduled_after  = [r for r in rows_after if r.get("send_after","").strip() and not r.get("sent_at","").strip()]
sent_after       = [r for r in rows_after if r.get("sent_at","").strip()]

print(f"\nAfter:")
print(f"  total rows          : {total_after}")
print(f"  sent rows           : {len(sent_after)}")
print(f"  scheduled+unsent    : {len(scheduled_after)}")
print(f"  unscheduled+unsent  : {total_after - len(sent_after) - len(scheduled_after)}")

assert total_after == total_before,      "ERROR: row count changed"
assert len(sent_after) == len(sent_rows),"ERROR: sent row count changed"
assert len(scheduled_after) == 0,        "ERROR: scheduled rows still present"

print(f"\nRows unscheduled : {len(cleared)}")
print(f"Field cleared    : send_after -> ''")
print(f"Fields preserved : all others unchanged")
print(f"\nUnscheduled row list:")
for c in cleared:
    print(f"  [{c['draft_version']:>3}]  was={c['send_after']!r:36s}  appr={c['approved']!r}  {c['business_name']!r}")

print(f"\nAssertions passed. Queue safe.")
print(f"Backup at: {backup_queue}")
