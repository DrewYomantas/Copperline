# Current Build Pass

## Active System
Observation-Led Outreach Rewrite

## Status
Pass 36 complete.

---

## Completed: Pass 36 - Observation-Led Outreach Rewrite - TBD

Product changes across three files:
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

No protected systems touched. Queue schema column addition is additive and non-send-path only.

### Core rule change

First-touch outreach generation is now blocked without a `business_specific_observation`.
This is a product rule change, not copy polish. A draft without a specific observation cannot be created or regenerated.

### email_draft_agent.py — full rewrite to v9

- Removed all previous industry-angle templates (`_ANGLE_CLAUSE`, `_OPENERS`, `_SECOND_SENTENCES`).
- Added `ObservationMissingError` and `DraftInvalidError` exception types for clear failure signaling.
- Added `_require_observation()` — blocks if observation absent or under 15 chars.
- Added `_is_generic_observation()` — blocks observations that are category labels rather than business-specific details.
- Added `validate_draft()` — deterministic validation layer that blocks banned buzzwords, hard CTAs, links, pricing, sender-centered filler openers, and drafts that don't materially reflect the observation.
- Added three controlled variation families (A/B/C) only — no open-ended variation:
  - Family A: observation → grounded sentence → soft open
  - Family B: observation → operational implication → soft open
  - Family C: observation → soft grounded note → soft open
- `draft_email()` now requires `observation` arg or `prospect["business_specific_observation"]` field. Fails clearly if absent or invalid.
- `draft_social_messages()` now requires observation. Same failure path.
- Added prefix normalization so observations starting with "saw"/"noticed" don't stack with the variant prefix.
- `DRAFT_VERSION` bumped v8 → v9.

### dashboard_server.py — additive changes only

- Added `business_specific_observation` to `PENDING_COLUMNS` as the final column. Additive, non-send-path, DictReader-safe for existing rows.
- Added `/api/update_observation` — persists observation to queue row. Rejects absent, short, or generic observations.
- Added `/api/regenerate_draft` — requires observation (stored or override). Returns structured `blocked_reason` on failure. On success, writes new subject/body/DM drafts back to queue and returns all fields to frontend.

### index.html — observation field + regenerate controls

- Added observation CSS block (`.obs-section`, `.obs-input`, `.btn-regen`, `.obs-regen-status`, `.obs-blocked-banner`).
- Added observation HTML panel section between insight and social sections: textarea, hint, required tag, regenerate button, status line.
- Added `_panelPopulateObs(row)` — hydrates observation field when panel opens; shows blocked state + hint when observation absent; enables regen button when observation present.
- Added `panelObsChanged(value)` — live input handler; enables/disables regen button; updates hint text in real time.
- Added `panelRegenerateDraft()` — calls `/api/regenerate_draft`; on success updates subject, body, DM draft fields in panel and in-memory row; on `observation_missing` shows blocked banner; on `draft_invalid` shows specific reason.
- Wired `_panelPopulateObs(row)` call into `fillPanel()` after the insight section.

### Verification

- `python -m py_compile` clean on `email_draft_agent.py` and `dashboard_server.py`.
- `node --check` clean on extracted dashboard JS.
- 23/23 targeted verification checks passed:
  - `draft_email` blocks when observation missing
  - `draft_social_messages` blocks when observation missing
  - Generic observation detected and rejected
  - Short observation rejected
  - Valid observation produces clean draft, observation token appears in body
  - No banned words in output
  - DM observation token appears, no links in DM
  - `validate_draft` rejects banned words, links, pricing
  - Controlled variations produce distinct openings across 3 businesses
  - Observation from `prospect` field works (not only from arg)

---

## Completed: Pass 35 - Scheduling Clarity + Queue Timeline UX - `4e18c3c`

Product change stayed in `lead_engine/dashboard_static/index.html`.
No backend changes. No protected systems touched.

### Clearer queue states

- Added a queue-state helper layer so outreach rows now read more clearly as `Pending`, `Approved`, `Scheduled`, or `Ready Now` when a scheduled send window has already arrived.
- Status cells now include compact explanation lines under the badge instead of only terse labels.
- Future scheduled rows explicitly say they are waiting, while reached-window rows now explain that they are eligible in `Send Approved` again.

### Better timeline understanding

- Added a queue timeline explainer bar directly under the outreach filters.
- The note changes by queue view and explains how future scheduled rows behave relative to `Actionable`, `Approved`, `Scheduled`, and `All`.
- Added an exact local-time formatter for scheduled rows so the UI can show both relative timing and the concrete local send time.

### Clearer review feedback

- Reworked the review panel schedule block so it explains whether a row is:
  - waiting for a future morning window
  - ready now because the scheduled time already arrived
  - approved and immediately sendable
  - still pending review
- Updated scheduling feedback copy across queue/review actions so the operator gets immediate confirmation about whether the row is waiting for later or back in a ready-now queue.

### Verification

- Extracted inline dashboard JavaScript and ran `node --check` successfully.
- Ran a focused live headless-browser smoke pass against `http://127.0.0.1:5000` using a synthetic queue subset with stubbed API writes to verify:
  - dashboard load
  - queue timeline note rendering
  - approved vs scheduled vs ready-now distinction
  - review panel timing explanations
  - schedule and unschedule state transitions
  - schedule button wording clarity
  - basic Pass 29 discovery control availability
- Reconfirmed the pass stayed frontend-only and did not touch protected systems.

---

## Completed: Pass 34 - Outreach Review Throughput + Queue Control - `67716ce`

Product change stayed in `lead_engine/dashboard_static/index.html`.
No backend changes. No protected systems touched.

### Faster sequential review flow

- Added a review-session bar directly under the panel header so operators can see which subset they are reviewing without leaving the panel.
- Added compact live counts for the current snapshot set: total rows in set, remaining after the current record, pending, approved, scheduled, and no-email rows.
- Added a new flow-action strip inside the panel body with context-aware actions like `Approve + Next`, `Schedule + Next`, `Unschedule + Next`, `Undo + Next`, and `Skip`.

### Better queue visibility and continuity

- Preserved Pass 30 snapshot-based review stability and layered clearer session context on top of it instead of redesigning the panel.
- Discovery-opened review sessions now carry a `Discovery review subset` label through the Pass 33 bridge, so the operator can tell they are working inside a narrowed discovery handoff set.
- Existing panel position controls remain intact, but the current subset is now clearer while moving record to record.

### Faster review controls

- Added keyboard shortcuts for high-volume review sessions:
  - arrows move
  - `A` approve
  - `Shift+A` approve and continue
  - `S` schedule
  - `Shift+S` schedule and continue
  - `U` unschedule
  - `N` skip to next
- Built these on top of the current review actions instead of altering queue schema, scheduler logic, or sender behavior.

### Verification

- Extracted inline dashboard JavaScript and ran `node --check` successfully.
- Ran a focused live headless-browser smoke pass against `http://127.0.0.1:5000` using a synthetic review subset with stubbed API writes to verify:
  - dashboard load
  - discovery-to-review subset label continuity
  - queue position/session visibility
  - `Approve + Next`
  - `Unschedule + Next`
  - `Shift+S` schedule-and-continue
  - `N` skip progression
  - overlay-close guard stability
  - basic Pass 29 discovery control availability
- Reconfirmed the pass stayed frontend-only and did not touch protected systems.

---

## Completed: Pass 33 - Bulk Discovery-to-Outreach Workflow Acceleration - `c1a56a4`

Product change stayed in `lead_engine/dashboard_static/index.html`.
No backend changes. No protected systems touched.

### Faster discovery-to-outreach handoff

- Added a direct bridge from the discovery results rail into the outreach review workflow, built around the current visible subset after triage/filtering.
- Added `Review Visible` so operators can take the exact current visible discovery subset into the review panel as a navigable outreach set.
- Added `Prep Outreach` so outreach-ready visible leads are bulk-approved first, then opened immediately in review.

### Smarter visible-set bulk behavior

- Tightened discovery bulk actions to use the actual visible queue-row context instead of weaker business-name matching.
- This keeps visible-set `Approve`, `Schedule`, and `Delete` aligned with the filtered/qualified subset the operator is looking at.
- Added compact visible-set summary counts showing reviewable rows, outreach-ready rows, and how many still need approval.

### Workflow continuity

- The discovery panel now supports a cleaner progression: narrow to strong leads, prep them in bulk, then review that same subset without rebuilding context manually.
- The review panel still opens against a snapshot of the intended row set, preserving Pass 30 edit stability.
- Pass 29 grid/visible/exhaust discovery controls and Pass 32 triage controls remain intact.

### Verification

- Extracted inline dashboard JavaScript and ran `node --check` successfully.
- Ran a focused live headless-browser smoke pass against `http://127.0.0.1:5000` using a synthetic discovery dataset with stubbed API writes to verify:
  - dashboard load
  - triage controls still rendering
  - visible-set summary counts
  - `Review Visible` opening the correct subset in outreach review
  - `Prep Outreach` approving outreach-ready visible rows and opening that subset in review
  - overlay-close guard stability
  - basic Pass 29 discovery control availability
- Reconfirmed the pass stayed frontend-only and did not touch protected systems.

---

## Completed: Pass 32 - Discovery Triage + Lead Qualification Controls - `8868847`

Product change stayed in `lead_engine/dashboard_static/index.html`.
No backend changes. No protected systems touched.

### Qualification layer

- Added a lightweight qualification helper in the discovery results panel that uses fields already present on the result/queue rows instead of inventing a new backend scoring engine.
- Leads are now classified into practical operator buckets: `Ready now`, `Maybe later`, `Needs contact info`, `Weak / skip`, and `Sent / closed`.
- Qualification looks at existing signals such as email presence, website/phone availability, queue state, score, and other contactability-strength hints when available.

### Faster triage controls

- Added quick triage chips with live counts directly in the map results rail for `All`, `Ready`, `Maybe`, `Needs Contact`, `Weak`, and `No Email`.
- Added `Group: Qualification` so large discovery runs can be sectioned by readiness instead of only workflow/city/email.
- Existing score-first sorting, workflow grouping, email-only filtering, and map result bulk actions remain available.

### At-a-glance clarity

- Each discovery result now shows a primary qualification badge plus compact "why" chips such as email readiness, score strength, missing website, phone-only, or no direct contact.
- This makes stronger vs weaker leads clearer without forcing the operator to open each row one by one.
- The visible review/edit context still follows the currently narrowed result set, so triage and review work together instead of fighting each other.

### Verification

- Extracted inline dashboard JavaScript and ran `node --check` successfully.
- Ran a focused live headless-browser smoke pass against `http://127.0.0.1:5000` using a synthetic discovery dataset injected into the real dashboard page to verify:
  - dashboard load
  - triage chip rendering and counts
  - qualification grouping
  - triage narrowing
  - marker click behavior from panel items
  - review/edit opening and overlay-close guard stability
  - basic Pass 29 discovery control availability
- Reconfirmed the pass stayed frontend-only and did not touch protected systems.

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
