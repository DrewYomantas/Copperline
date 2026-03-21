from pathlib import Path

p = Path(r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CHANGELOG_AI.md')
original = p.read_text(encoding='utf-8')

new_entry = """
### 2026-03-18 - Pass 48: Lifecycle Coverage Expansion

**Goal:** Fill in the remaining high-value lifecycle events so the timeline
is meaningfully complete for normal operator work without touching protected systems.

**Files changed:**
- `lead_engine/lead_memory.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`
- docs (4 files)

**What changed:**

`lead_memory.py`:
- Added `EVT_APPROVED`, `EVT_UNAPPROVED`, `EVT_SCHEDULED`, `EVT_UNSCHEDULED`
  to constants, `_ALL_EVENT_TYPES`, and `_EVENT_LABELS`.

`dashboard_server.py`:
- `api_approve_row`: records `EVT_APPROVED` after queue write.
- `api_unapprove_row`: records `EVT_UNAPPROVED` after queue write.
- `api_schedule_email`: records `EVT_SCHEDULED` (detail=send_after) when
  setting a schedule, `EVT_UNSCHEDULED` when clearing. All try/except wrapped.

`index.html`:
- `_TL_ICON` and `_TL_COLOR` extended for approved (✓ green), unapproved
  (✗ muted), scheduled (🕐 blue), unscheduled (○ muted).

**Intentional non-hooks:**
- `discovered`: post-pipeline row attribution is too risky without protected code.
- `EVT_DRAFTED`: run_pipeline is protected.
- `EVT_FOLLOWUP_SENT`: deferred to Pass 50.
- `suppressed`, `revived`, `deleted_intentionally`: already recorded as
  state-transition entries via `record_suppression()` — no new hooks needed.

**Commit:** `e8d8312`

---

"""

anchor = '### 2026-03-18 - Pass 47:'
idx = original.find(anchor)
if idx == -1:
    new_content = new_entry.lstrip('\n') + original
else:
    new_content = original[:idx] + new_entry.lstrip('\n') + original[idx:]

p.write_text(new_content, encoding='utf-8')
print(f'Written {len(new_content):,} chars')
