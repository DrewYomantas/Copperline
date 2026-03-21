from pathlib import Path

p = Path(r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CURRENT_BUILD.md')
original = p.read_text(encoding='utf-8')

new_header = """# Current Build Pass

## Active System
Pass 48 -- Lifecycle Coverage Expansion

## Status
Pass 48 complete.

---

## Completed: Pass 48 -- Lifecycle Coverage Expansion -- `e8d8312`

Product changes across three files:
- `lead_engine/lead_memory.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

No protected systems touched. No queue schema changes.

### Problem addressed

Pass 47 built the event infrastructure and UI surfaces. The timeline was live but
thin -- only four event types were recorded (observation, regen, note, replied).
The most common daily actions -- approve, schedule, unschedule -- left no trace.

### What was added

**`lead_memory.py`**

Four new constants, all registered in `_ALL_EVENT_TYPES` and `_EVENT_LABELS`:

| Constant | Value | Label |
|---|---|---|
| `EVT_APPROVED` | `"approved"` | Approved |
| `EVT_UNAPPROVED` | `"unapproved"` | Approval removed |
| `EVT_SCHEDULED` | `"scheduled"` | Scheduled |
| `EVT_UNSCHEDULED` | `"unscheduled"` | Unscheduled |

**`dashboard_server.py`** -- four hooks, all `try/except` wrapped:

`api_approve_row`: records `EVT_APPROVED` after `_write_pending`.

`api_unapprove_row`: records `EVT_UNAPPROVED` after `_write_pending`.

`api_schedule_email`: inspects the resolved `send_after` value. If non-empty,
records `EVT_SCHEDULED` with `detail=send_after`. If empty (schedule cleared),
records `EVT_UNSCHEDULED`. Single insertion point handles both modes (explicit
ISO string and industry-window calculation) because both resolve to the same
`send_after` variable before the hook.

**`index.html`**

`_TL_ICON` and `_TL_COLOR` extended:
- `approved`: ✓ / `var(--green)`
- `unapproved`: ✗ / `var(--muted)`
- `scheduled`: 🕐 / `var(--blue)`
- `unscheduled`: ○ / `var(--muted)`

### What was audited but does not need new code

- `suppressed`, `revived`, `deleted_intentionally`, `do_not_contact`, `hold`:
  already recorded as `type:"state"` entries via `record_suppression()` in
  `api_suppress_lead`, `api_revive_lead`, `api_delete_row`, `api_opt_out_row`.
  They already appear in timelines. No new hooks needed.

### What remains intentionally deferred

- `EVT_DRAFTED`: `run_pipeline` / `run_lead_engine.py` is protected.
- `EVT_FOLLOWUP_SENT`: fits naturally in Pass 50 (Follow-Up System Rebuild).
- `discovered` event: post-pipeline row attribution cannot be done reliably
  without touching protected code.

### Complete lifecycle event coverage as of Pass 48

| Event | Hook | Status |
|---|---|---|
| observation_added | api_update_observation | Live (P47) |
| draft_regenerated | api_regenerate_draft | Live (P47) |
| replied | api_log_contact result=replied | Live (P47) |
| note_added | api_update_conversation | Live (P47) |
| approved | api_approve_row | Live (P48) |
| unapproved | api_unapprove_row | Live (P48) |
| scheduled | api_schedule_email (set) | Live (P48) |
| unscheduled | api_schedule_email (clear) | Live (P48) |
| drafted | run_pipeline (protected) | Deferred |
| followup_sent | send_followup (Pass 50) | Deferred |

### Verification

- `python -c "import lead_memory; import dashboard_server"` clean.
- `node --check` on extracted JS clean.
- 6/6 checks: new EVT constants registered, approved/scheduled/unscheduled
  events recorded correctly, current_state unchanged after events,
  full sequence sorted correctly, real memory file intact.

---

"""

anchor = '## Completed: Pass 47'
idx = original.find(anchor)
if idx == -1:
    print('ERROR: anchor not found'); exit(1)

new_content = new_header + original[idx:]
p.write_text(new_content, encoding='utf-8')
print(f'Written {len(new_content):,} chars, {new_content.count(chr(10))} lines')
