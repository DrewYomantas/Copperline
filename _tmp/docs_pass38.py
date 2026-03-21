import re, os

BASE  = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs"
STATE = os.path.join(BASE, "PROJECT_STATE.md")
CHLOG = os.path.join(BASE, "CHANGELOG_AI.md")

# ── PROJECT_STATE: insert Pass 38 note after the Pass 37 last-pass block ──────
with open(STATE, "r", encoding="utf-8") as f:
    src = f.read()

P38_NOTE = """
## Queue State Management Note — Pass 38
**Date:** 2026-03-17
**Operation:** Bulk unschedule of 56 pre-Pass-36 (v7 draft) scheduled rows.

All 56 rows were scheduled for 2026-03-18 morning windows but carry old-style
pre-observation drafts that should not auto-send. `send_after` was cleared on
each. No rows deleted. No other fields altered. 50 sent rows untouched.
Total row count unchanged at 180.

Backup: `_backups/pending_emails_pre_p38_20260317_182909.csv`

**Queue state after:**
- total rows: 180
- sent rows: 50
- scheduled+unsent: 0
- unscheduled+unsent: 130

"""

# Insert before ## Previous Completed Pass
target = "## Previous Completed Pass"
if target in src and "Pass 38" not in src:
    src = src.replace(target, P38_NOTE + target, 1)
    print("STATE: Pass 38 note inserted")
else:
    print("STATE: already present or target missing")

with open(STATE, "w", encoding="utf-8") as f:
    f.write(src)

# ── CHANGELOG: prepend entry ───────────────────────────────────────────────────
P38_LOG = """### 2026-03-17 - Pass 38: Pre-Pass-36 Queue State Cleanup (Bulk Unschedule)

**Type:** Operational state management. No product code changed.

**Goal:** Stop 56 old-style (v7 draft) scheduled rows from auto-sending tomorrow morning without losing any lead identity or contact history.

**What happened:**
- Inspected `pending_emails.csv`: 56 rows scheduled+unsent, all `draft_version=v7`, all targeting 2026-03-18 windows.
- Backed up queue to `_backups/pending_emails_pre_p38_20260317_182909.csv`.
- Cleared `send_after` on all 56 rows. No other fields touched.
- Verified: total rows 180→180, sent rows 50→50, scheduled+unsent 56→0.
- All assertions passed.

**Files changed (docs only — queue is gitignored):**
- `docs/PROJECT_STATE.md`
- `docs/CHANGELOG_AI.md`

**Commit:** TBD

---

"""

with open(CHLOG, "r", encoding="utf-8") as f:
    cl = f.read()

first = "### 2026-03-17 - Pass 37:"
if first in cl and "Pass 38" not in cl:
    cl = cl.replace(first, P38_LOG + first, 1)
    print("CHANGELOG: Pass 38 prepended")
else:
    print("CHANGELOG: already present or anchor missing")

with open(CHLOG, "w", encoding="utf-8") as f:
    f.write(cl)

print("Done.")
