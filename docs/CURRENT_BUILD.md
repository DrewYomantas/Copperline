# Current Build Pass

## Active System
Dashboard UX Safety Cleanup

## Status
Pass 14 complete.

---

## Completed: Pass 9a — Queue Visual Safety — `f712909`
## Completed: Pass 9b — Scheduled Send Intent — `24dc5b2` / `52dd64a` / `a5f09c5`

---

## Completed: Pass 10 — Scheduled Queue UX — `d31d720`

Two files changed: `dashboard_server.py` + `dashboard_static/index.html`.
No schema changes. No send logic changes.

### Backend change (`dashboard_server.py`)
`/api/schedule_email` now accepts `send_after: ""` to clear a schedule.
Previously, empty string was rejected with 400. Now:
- `send_after` absent/null → 400 (missing)
- `send_after: ""` → accepted, clears schedule, writes `""` to row
- `send_after: "2026-03-17T07:30:00"` → accepted, schedules
All identity/bounds/name-match validation unchanged. No other field touched.

### Frontend changes (`index.html`)

**`_formatSendAfter(isoStr)` helper** (new function)
Parses ISO string to local Date. Returns:
- `Today · 7:30am` if same calendar day
- `Tomorrow · 7:30am` if next calendar day
- `Fri Mar 20 · 8:00am` for further dates
- `""` for empty/null input

**Table: readable time under scheduled badge**
For `row.send_after && !row.sent_at`, a muted 10px sub-line appears under
the `🕐 Scheduled` badge showing `_formatSendAfter(row.send_after)`.

**`applyFiltersAndSort` — Active filter fix**
Active was: `!sent_at && !_TERMINAL`
Active now: `!sent_at && !send_after && !_TERMINAL`
Scheduled rows move to the Scheduled tab. Active = true actionable drafts only.

**`applyFiltersAndSort` — Scheduled sort**
Scheduled filter now includes `rows.sort((a,b) => a.send_after.localeCompare(b.send_after))`
Earliest scheduled rows appear first.

**CSS additions**
`.panel-sched-info` — amber-tinted schedule info block
`.panel-sched-info .sched-time` — bold time label
`.panel-sched-info .btn-sched-act` — inline action button style

**Panel HTML addition**
`<div id="panel-schedule-info">` inserted between social section and footer.

**`fillPanel` — schedule info wiring**
When `row.send_after && !row.sent_at`:
- Renders `🕐 Scheduled: [formatted time]` + Clear / +1 day / +2 / +3 buttons
- Block is hidden when `send_after` is empty

**`panelClearSchedule()` (new)**
Calls `/api/schedule_email` with `send_after: ""`.
Updates `row.send_after = ""`, calls `renderTable()` + `fillPanel()`.
Toast: `Schedule cleared`.

**`panelReschedule(days)` (new)**
Calls `/api/schedule_email` with `send_after = today + days + SEND_WINDOWS[industry]`.
Updates `row.send_after`, calls `renderTable()` + `fillPanel()`.
Toast: `Rescheduled for [formatted date]`.

---


## Completed: Pass 11 — Sent Mail Reconciliation Recovery — `aae0cb5`

Three files changed: `outreach/reply_checker.py` + `dashboard_server.py` + `dashboard_static/index.html`.
No schema changes. No send pipeline rewrite.

### Backend changes
- Added `reconcile_sent_mail(max_messages=150, lookback_hours=72)` in `reply_checker.py`
- Added Sent mailbox probing (`[Gmail]/Sent Mail`, `[Gmail]/Sent`, `Sent`, `Sent Mail`)
- Added strict reconciliation key: `(to_email, subject)` over approved rows where `sent_at` + `message_id` are blank
- Added ambiguity guard: skip when queue has duplicate key or Gmail Sent has multiple matches
- Added `/api/reconcile_sent` route in `dashboard_server.py`

### Frontend changes
- Added toolbar action button `↺ Check Sent`
- Added `checkSent()` flow calling `/api/reconcile_sent`
- Shows safe-skip toast for ambiguous matches and refreshes queue after updates


## Completed: Pass 12 — Queue Bulk Action + Unschedule Fix — `c40d16d`

One file changed: `dashboard_static/index.html`.
No schema changes. No send logic changes.

### Root cause
Bulk Approve/Unapprove used `Promise.all` against `/api/approve_row` and `/api/unapprove_row`.
Those endpoints read+write the full queue per call, so concurrent calls can race and overwrite each other.

### Fix
- `bulkApprove()` changed from parallel `Promise.all` to sequential per-row calls
- `bulkUnapprove()` changed from parallel `Promise.all` to sequential per-row calls
- Existing bulk Delete/Clear and single-row approve/unapprove flows were preserved
- Panel schedule action label changed from `Clear` to explicit `Unschedule`
- `panelUnschedule()` uses existing `/api/schedule_email` with `send_after: ""`


## Completed: Pass 13 — Dashboard Startup Import Recovery — `c2234ea`

Files changed:
- `lead_engine/discovery/prospect_discovery_agent.py`
- `lead_engine/run_lead_engine.py`
- `lead_engine/intelligence/website_scan_agent.py`
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/scoring/opportunity_scoring_agent.py`
- `lead_engine/city_planner.py`
- `lead_engine/intelligence/email_extractor_agent.py`

Root cause: startup import chain had drifted symbols/modules (`clean_website_for_key`, `generate_lead_insight`, `draft_social_messages`, `compute_numeric_score`, `score_priority_label`, `city_planner`, `email_extractor_agent`).

Fix: restore missing compatibility exports/modules with minimal additive shims so dashboard import chain resolves.

Verification:
- `python -m py_compile` on touched startup files
- `python lead_engine/dashboard_server.py` starts and serves on `127.0.0.1:5000`


## Completed: Pass 14 — Dashboard UX Safety Cleanup — `014e68c`

File changed:
- `lead_engine/dashboard_static/index.html`

UI cleanup delivered:
- Broken client leads navigation path disabled (`mcViewLeads` informational toast only)
- Disabled client actions now have explicit tooltips (`Leads view not enabled yet`, `Delete client not enabled yet`)
- Conversation quick action labels now clarify copy behavior
- `Approve All` now requires confirmation with explicit write-action copy and target count
- Map disclosure note added for marker partiality expectations
- Tools top-nav now visibly marked `Stub`

Verification:
- Browser script check: no JS page errors on load
- Approve All confirms and still hits `/api/approve_all`
- Conversation quick action still copies text via clipboard handler
- `mcViewLeads()` no longer switches pages
- Map disclosure note visible on Map page
- No backend files modified

## Next: Pass 15 — TBD

Candidates:
- Territory heatmap overlay
- Industry saturation view
- Tiled backend improvements (rate-limit handling)

Define scope before starting.
