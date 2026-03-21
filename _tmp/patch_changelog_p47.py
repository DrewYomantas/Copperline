from pathlib import Path

p = Path(r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CHANGELOG_AI.md')
original = p.read_text(encoding='utf-8')

new_entry = """
### 2026-03-18 - Pass 47: Lead Timeline / Lifecycle Event Spine

**Goal:** Introduce durable per-lead event history that records key lifecycle
actions in one place, giving narrative continuity to the lead record beyond
just current suppression state.

**Files changed:**
- `lead_engine/lead_memory.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**

`lead_memory.py`:
- Updated docstring documenting the two-entry-type history model.
- `EVT_*` constants: `EVT_DRAFTED`, `EVT_OBSERVATION_ADDED`, `EVT_DRAFT_REGENERATED`,
  `EVT_REPLIED`, `EVT_NOTE_ADDED`, `EVT_FOLLOWUP_SENT`. All registered in `_ALL_EVENT_TYPES`.
- `_EVENT_LABELS` and `_STATE_LABELS` dicts for UI rendering.
- `record_event(row, event_type, *, detail, operator)`: appends `type='event'` entry to
  `history[]` without changing `current_state`. Creates lead record if none exists.
  Event-only records are not suppressed (`is_suppressed()` returns False).
- `get_timeline(row)`: returns full `history[]` sorted oldest-first. Back-fills
  `type='state'` and `label` for pre-Pass-47 entries that lack those fields.
  Returns `[]` if no memory record exists.

`dashboard_server.py` — 4 lifecycle hooks (all try/except wrapped):
- `api_update_observation`: records `EVT_OBSERVATION_ADDED` with `detail=obs[:120]`.
- `api_regenerate_draft`: records `EVT_DRAFT_REGENERATED` on success.
- `api_update_conversation`: records `EVT_NOTE_ADDED` when notes field is non-empty.
- `api_log_contact` result=replied: records `EVT_REPLIED` with `detail=channel`.
- New `POST /api/lead_timeline`: returns full timeline by lead identity
  (accepts business_name, website, phone, place_id, city).

`index.html`:
- `panel-timeline-strip` div inserted below `panel-meta` in panel HTML.
- `_TL_ICON` and `_TL_COLOR` lookup maps for timeline rendering.
- `_loadPanelTimeline(row)`: fetches `/api/lead_timeline`, non-blocking.
  Called at end of `fillPanel` — does not delay panel render.
- `_timelineStripHtml(timeline)`: renders last 6 events as compact icon+label
  dots with hover tooltips for full detail. Shows "+N more" when truncated.
- Lead Memory tab `memFilterRender`: event count replaced with clickable
  "N events ▾" button. Header row now shows Events column (was count-only).
- `memToggleTimeline(key, bizName, website, btn, rowId)`: toggles/lazy-loads
  full timeline in an inline `<tr>` detail row. Fetches once per row
  (`dataset.loaded='1'` guard). Renders icon, label, timestamp, detail per entry.

**No protected systems touched. No queue schema changes.**

**Verification:**
- `python -c "import lead_memory; import dashboard_server"` clean.
- `node --check` on extracted JS clean.
- 6/6 checks passed: record_event without state change, event-only record not
  suppressed, get_timeline sort + back-fill, legacy entry back-fill, EVT_*
  constants registered, real memory file integrity unchanged.

**Commit:** `4a4a04b`

---

"""

anchor = '### 2026-03-18 - Pass 46:'
idx = original.find(anchor)
if idx == -1:
    new_content = new_entry.lstrip('\n') + original
else:
    new_content = original[:idx] + new_entry.lstrip('\n') + original[idx:]

p.write_text(new_content, encoding='utf-8')
print(f'Written {len(new_content):,} chars')
