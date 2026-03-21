from pathlib import Path

p = Path(r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CURRENT_BUILD.md')
original = p.read_text(encoding='utf-8')

new_header = """# Current Build Pass

## Active System
Pass 47 -- Lead Timeline / Lifecycle Event Spine

## Status
Pass 47 complete.

---

## Completed: Pass 47 -- Lead Timeline / Lifecycle Event Spine -- `4a4a04b`

Product changes across three files:
- `lead_engine/lead_memory.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

No protected systems touched. No queue schema changes.

### Problem addressed

The system had identity, status semantics, next-action guidance, and suppression
memory -- but no narrative continuity per lead. A lead could be discovered,
have an observation added, get a draft regenerated, reply, and be contacted --
and the operator had no single place to see that arc. Each event existed in
isolated queue fields or nowhere at all.

### lead_memory.py extensions

**Two-type history model:** `history[]` now holds two entry types:
- `type: "state"` -- state transitions (contacted, hold, revived, etc.). Written
  by `record_suppression()`. Updates `current_state`.
- `type: "event"` -- lifecycle events. Written by `record_event()`. Does NOT
  update `current_state`. `is_suppressed()` unaffected.

Both coexist in the same `history[]` list, sorted by timestamp in `get_timeline()`.

**`EVT_*` constants:** `EVT_DRAFTED`, `EVT_OBSERVATION_ADDED`, `EVT_DRAFT_REGENERATED`,
`EVT_REPLIED`, `EVT_NOTE_ADDED`, `EVT_FOLLOWUP_SENT`.

**`record_event(row, event_type, *, detail, operator)`**
- Appends `{type:'event', event_type, label, ts, detail, ...}` to `history[]`.
- Creates a memory record for the lead if none exists. Event-only records have
  no `current_state` and are not suppressed.
- Wrapped in try/except at all call sites -- failure never blocks the API response.

**`get_timeline(row)`**
- Returns `history[]` sorted oldest-first.
- Back-fills `type='state'` and `label` for pre-Pass-47 entries that lack them.
- Uses `_STATE_LABELS` and `_EVENT_LABELS` for display text.
- Returns `[]` if no record exists.

### dashboard_server.py hooks

Four additive try/except blocks, one per safe hook point:

| Endpoint | Trigger | Event |
|---|---|---|
| `api_update_observation` | Observation saved | `EVT_OBSERVATION_ADDED` |
| `api_regenerate_draft` | Draft regenerated successfully | `EVT_DRAFT_REGENERATED` |
| `api_update_conversation` | Notes field non-empty on save | `EVT_NOTE_ADDED` |
| `api_log_contact` result=replied | Contact logged as replied | `EVT_REPLIED` |

**`POST /api/lead_timeline`** (new route)
- Accepts: `{ business_name, website?, phone?, place_id?, city? }`
- Returns: `{ ok, key, total, timeline: [...] }`
- Uses `lead_key()` priority for identity resolution.
- Returns `total: 0, timeline: []` when no memory record exists.

### index.html -- two UI surfaces

**Panel timeline strip (Business Info section)**
- `<div id="panel-timeline-strip">` inserted below `panel-meta`.
- `_loadPanelTimeline(row)` called at end of `fillPanel` -- async, non-blocking.
- Fetches `/api/lead_timeline`, renders via `_timelineStripHtml()`.
- Shows last 6 events as compact `icon label` dots separated by `·`.
- Each dot has a hover tooltip with `label — timestamp — detail`.
- "+N more" suffix when history exceeds 6 entries.
- Clears and reloads on every panel open.

**Lead Memory tab expanded timeline**
- `memFilterRender` event count cell replaced with "N events ▾" expand button.
- Clicking toggles a `<tr>` detail row immediately below the lead row.
- `memToggleTimeline()` fetches timeline lazily on first expand (`dataset.loaded`).
- Renders full history: icon, label (color-coded), timestamp, detail per entry.

### What is intentionally not hooked

- `api_run_pipeline` / `run_lead_engine.py` -- protected. `EVT_DRAFTED` constant
  exists for future use when a safe hook point is identified.
- `api_send_followup` -- `EVT_FOLLOWUP_SENT` constant exists; hook deferred to
  Pass 50 (Follow-Up System Rebuild) where it fits more naturally.
- `api_send_approved` / `process_pending_emails` -- protected send path.

### Verification

- Both Python modules import clean.
- `node --check` on extracted JS: clean.
- 6/6 checks passed (see commit message for full list).

---

"""

anchor = '## Completed: Pass 46'
idx = original.find(anchor)
if idx == -1:
    print('ERROR: anchor not found'); exit(1)

new_content = new_header + original[idx:]
p.write_text(new_content, encoding='utf-8')
print(f'Written {len(new_content):,} chars, {new_content.count(chr(10))} lines')
