# Current Build Pass

## Active System
Contact Quality Upgrade

## Status
Pass 31 complete.

---

## Completed: Pass 31 - Contact Quality Upgrade - `3098082`

Product changes stayed in three backend/support files:
- `lead_engine/discovery/auto_prospect_agent.py`
- `lead_engine/intelligence/email_extractor_agent.py`
- `lead_engine/outreach/email_draft_agent.py`

No protected systems touched.

### Hidden email extraction

- Expanded website email scraping beyond visible text to include `mailto:` actions with query strings, likely email-bearing attributes, simple `[at]` / `[dot]` obfuscation, paired `data-user` + `data-domain` attributes, and Cloudflare email-protection tokens.
- Added bounded contact-page discovery so the scraper can follow obvious internal contact/quote/schedule pages instead of only checking a tiny fixed path list.
- Centralized website contact extraction into one helper so discovery and enrichment use the same capture logic.

### Contact normalization and enrichment

- Strengthened cleanup of extracted emails with safer placeholder/junk suppression and better candidate ranking for domain-matching role accounts.
- Restored `email_extractor_agent.py` from a stub to a working enrichment utility for `prospects.csv`.
- Enrichment now fills missing emails conservatively, updates contactability/contact-channel fields, and preserves existing emails unless overwrite is explicitly requested.

### Message quality guardrails

- Reworked the outreach copy pools toward cleaner, shorter, more natural phrasing without changing the high-level product direction.
- Removed the old intentional sloppy phrasing and random run-on merge from the post-processing guardrails.
- Social/contact-form companion drafts now strip the real sign-off format correctly and reuse the cleaner human-style guardrail.

### Verification

- Ran `python -m py_compile` on all touched code files.
- Ran a targeted Python verification script covering hidden email extraction patterns, candidate ranking, enrichment writes on a temporary prospects CSV, and multiple draft/social output samples.
- Reconfirmed the live dashboard still loads at `http://127.0.0.1:5000` after the backend changes.
- Left protected systems untouched: no `run_lead_engine.py`, sender core, scheduler core, follow-up system, or queue schema changes.

---

## Completed: Pass 30 - Discovery Panel Organization + Edit Stability - `5d11595`

Product changes stayed in `lead_engine/dashboard_static/index.html`.
No backend changes. No protected systems touched.

### Discovery panel organization

- Widened the discovery results rail and replaced the flat scroll list with grouped sections.
- Added `Group` controls for workflow, city, email status, or a flat list without redesigning the discovery page.
- Default ordering is now score-first, which pushes higher-priority rows to the top inside each section.
- Added lightweight detail metadata plus a clear active-result state so the operator can keep track of the lead they are working.
- Added an explicit `Edit` action from discovery results into the review panel.

### Edit stability

- Review panel navigation now anchors to a snapshot of the visible lead set instead of depending only on the live `filteredRows` table state.
- Queue-side panel actions now use the anchored row context, so approve, schedule, unschedule, campaign, and contact-log updates keep the same lead open.
- Overlay clicks no longer dismiss the review panel.
- Panel close is blocked while debounced text edits are still saving, which reduces accidental loss of place while reviewing many leads.
- Small fix: panel reschedule toast now uses the actual updated `row.send_after` value.

### Verification

- Extracted inline dashboard JavaScript and ran `node --check` successfully.
- Ran a live headless-browser smoke pass against the local dashboard server using a synthetic client-side discovery dataset to verify grouped sections, group switching, active selection, edit-panel stability, close-guard behavior, and basic Pass 29 control availability without mutating real queue data.
- Confirmed only `lead_engine/dashboard_static/index.html` changed in product code.
- Reconfirmed no protected systems were modified.

---

## Completed: Pass 29 - Discovery Coverage Expansion + Bulk Unschedule - `aaa3276`

Product change was one file: `lead_engine/dashboard_static/index.html`.
No backend changes. No scheduler core changes. No protected systems touched.

### Discovery coverage expansion

- Added `Search Area Grid` controls using the existing circle as the search boundary.
- Added multi-industry grid chips without removing the existing single-industry map controls.
- Added `_mapCircleGridPlan()` with hard caps of 36 cells and 120 total calls.
- Added `mapSearchAreaGrid()` for sequential circle-cell x industry sweeps with compact progress text and cancel support through `mapCancelAreaGrid()`.
- Added current-run dedupe for accumulated grid markers and one summarized history item per sweep.

### Bulk unschedule

- Added bulk `Unschedule` to the outreach bulk bar.
- Scheduled rows are now selectable in the `Scheduled` filter through `isRowScheduled()` and `isRowBulkSelectable()`.
- Added `bulkUnschedule()` using the existing `/api/schedule_email` clear path with `send_after: ""`.
- Per-row schedule and unschedule actions now refresh stats after completion.

### Verification

- Live headless-browser smoke pass covered dashboard load, grid UI visibility, multi-industry selection, oversized-plan blocking, grid status updates, cancel recovery, summarized history rendering, scheduled-row selection, bulk unschedule visibility/state, and existing single/visible/exhaust discovery actions.
- Smoke stabilization fixed one UI bug: bulk `Unschedule` now forces visible `inline-flex` display when scheduled selections are present.

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

## Completed: Pass 15a — Outreach Positioning: Remove Missed-Call-First Framing

Files changed:
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/dashboard_static/index.html`

Outreach system reframed away from missed-call-product pitch. `_OPENING_QUESTIONS`, `_BODY_FIXED`, and `cvSendQuick` templates updated. `_BANNED` list updated to allow `automation`/`workflow`. `DRAFT_VERSION` bumped to `v5`.

Note: Pass 15a introduced automation-agency tone that was corrected in Pass 15b.

## Completed: Pass 15b — Outreach Tone Correction: Operational Problem-First Messaging

Files changed:
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/dashboard_static/index.html`

Corrected automation-agency drift from Pass 15a. Outreach system now uses operational problem → conversation framing:
- Opening questions anchor on concrete loss scenarios: calls that go cold, leads that fall through after hours, follow-ups that don't happen.
- Body leads with what the business is currently losing, not what Copperline offers.
- CTA is soft and conditional.
- Automation is referenced as the implementation layer, not the headline.
- Missed-call texting remains in the system as a downstream solution — it is not the primary pitch in outreach copy.

`DRAFT_VERSION` bumped to `v6`. No logic, routing, or schema changes. No protected systems touched.

## Next: Pass 16 — TBD

Candidates:
- Territory heatmap overlay
- Industry saturation view
- Tiled backend improvements (rate-limit handling)
- Update `Copperline-Outreach-Sequence.md` and `Copperline-Proposal-Template.md` to match new positioning

Define scope before starting.
