"""
Pass 38 — Safe bulk unschedule of pre-Pass-36 scheduled rows.
Step 1: inspect only. No writes.
"""
import csv, os, sys

QUEUE = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\queue\pending_emails.csv"

with open(QUEUE, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

total       = len(rows)
sent        = [r for r in rows if r.get("sent_at","").strip()]
scheduled   = [r for r in rows if r.get("send_after","").strip() and not r.get("sent_at","").strip()]
pending     = [r for r in rows if not r.get("sent_at","").strip() and not r.get("send_after","").strip()]

print(f"total rows         : {total}")
print(f"sent rows          : {len(sent)}")
print(f"scheduled+unsent   : {len(scheduled)}")
print(f"unscheduled+unsent : {len(pending)}")
print()
print("Scheduled rows to unschedule:")
for r in scheduled:
    print(f"  [{r.get('draft_version','?'):>3}]  sa={r.get('send_after','')!r:36s}  appr={r.get('approved','')!r:6}  {r.get('business_name','')!r}")
