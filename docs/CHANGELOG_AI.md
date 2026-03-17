### 2026-03-17 — Docs Governance Pass: Bounded Cohesive Pass Model

**Goal:** Update AI repo instructions to replace ultra-small surgical pass model with bounded cohesive pass model.

**Type:** Documentation/governance pass only. No product code changed. No protected systems touched.

**What changed:**

`AI_DEV_STANDARDS.md`
- Replaced "Small incremental passes / No multi-feature commits" principle with "Bounded cohesive passes" principle
- Added Pass Scoping Rules section with explicit correct/incorrect scope examples
- Updated prohibited behavior: changed "make large multi-feature commits" to "bundle unrelated systems in a single pass"
- Typical pass size guidance added: 1–6 files, no hard max, but larger passes require stronger cohesion justification

`AI_START_HERE.md`
- Updated onboarding framing: new sessions now think in bounded implementation blocks, not artificially tiny passes
- Added "How to scope a pass" section with good/bad examples
- Updated file path references to match actual docs location (removed stale `docs/` prefixes)

`AI_CONTROL_PANEL.md`
- Updated Current Focus, Current Build Pass, Last Completed Pass, and Next Pass to reflect Pass 18b (was stale at Pass 14)
- Added Execution Model section documenting bounded cohesive pass rules with examples
- Updated Last Updated date to 2026-03-17

**Files changed:**
- `docs/AI_DEV_STANDARDS.md`
- `docs/AI_START_HERE.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**Commit:** `aaa3276`

---

### 2026-03-16 — Pass 11D: Industry Send Window UX Refinement

**Goal:** Make scheduling feel deliberate and industry-tailored while preserving manual Gmail sending and existing `send_after` queue semantics.

**Changes:**
- Added industry send-window helpers (`_industryWindowTime`, `_industryWindowLabel`, `_buildSendAfterFromWindow`) for coherent, operator-visible scheduling defaults.
- Updated review panel schedule actions and labels: `Tomorrow @ Best Time`, `Schedule for Best Time`, `Next Best Window`
- Enhanced schedule info block with compact guidance: industry default-time explanation, clear Approved vs Scheduled distinction
- Kept `panelUnschedule`, scheduled ordering, and all send behavior unchanged.

**Files touched:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CHANGELOG_AI.md`

**Commit:** `3413dbb`

---

### 2026-03-16 — Pass 11C: Discovery-to-Queue Continuity UX

**Goal:** Reduce context-switch friction between map discovery and queue processing without introducing fake campaign abstractions.

**Changes:**
- Added a persistent discovery handoff bar under top navigation with truthful post-run summary and direct actions: Review New Drafts, Continue Discovering, Return to Last Discovery Area
- Added lightweight session state: `_lastDiscoveryHandoff`, `_lastDiscoveryMapContext`, `_captureMapContext(...)`, `_publishDiscoveryHandoff(...)`
- Wired handoff publishing into successful discovery flows (`discoverLeads`, `mapSearch`, `mapSearchVisible`).
- Added map-context restore behavior so operators can jump to queue and return to the previous discovery area quickly.
- No backend changes; discovery remains explicit/operator-triggered.

**Files touched:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CHANGELOG_AI.md`

**Commit:** `70f1f96`

---

### 2026-03-16 — Pass 11B: Separate Sent Workspace / Completed Outreach View

**Goal:** Keep the live unsent queue clean by moving completed outreach into a separate destination view.

**Changes:**
- Added a dedicated Sent Workspace page (`page-sentview`) with its own header, stats, and table.
- Kept live queue default on unsent work and preserved existing queue-state filter semantics.
- Added Sent Workspace context using existing fields: sent time, business, subject, reply badge, follow-up hint.
- Added quick actions from Sent Workspace to Replied filter, Follow-Up queue, and original business row panel.
- Added top-nav Sent badge and wired Sent stage/primary nav to the separate Sent destination.

**Files touched:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CHANGELOG_AI.md`

**Commit:** `3a597b1`

---
### 2026-03-16 — Pass 11A: Pipeline UX V2 Flow Cleanup

**Goal:** Make the operator workflow read as one continuous flow: Discover → Review → Approve/Schedule → Sent → Follow-Up.

**Changes:**
- Simplified top-level navigation to direct destinations (Discovery, Queue, Scheduled, Sent, Follow-Up, Clients, System).
- Added a workflow stage rail inside Outreach with live counts and quick stage jumps.
- Preserved queue-state separation: Actionable (unsent and not scheduled), Scheduled (send_after and not sent), Sent (sent_at), Replied.
- Improved queue empty-state messaging for mode-switch scenarios.
- Kept send behavior, queue schema, and backend routes unchanged.

**Files touched:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CHANGELOG_AI.md`

**Commit:** `84d4a7b`

---

### 2026-03-16 — Pass 16: Outreach Command-Center Refinement

**Goal:** Improve operator clarity in Outreach by tightening immediate-work semantics and visually separating discovery, queue filtering, and queue actions.

**Changes:**
- Tightened `Actionable` definition to exclude stale-draft and missing-email rows in addition to scheduled/sent/terminal rows.
- Reorganized Outreach layout into clear stacked groups: Discovery controls, Queue workflow filters/view controls, and Queue actions.
- Grouped review/reconciliation tools separately from the primary send action (`▶ Send Approved`).
- Added secondary row treatment and note labels (`stale draft`, `missing email`, `low fit`).

**Files touched:**
- `lead_engine/dashboard_static/index.html`

**Commit:** `7da49b5`

---

### 2026-03-16 — Pass 15: Outreach Queue Regression Fix

**Goal:** Restore queue/stats/industry/table loading after the command-center cleanup regression.

**Root cause:** `loadAll()` used `Promise.all` for `/api/status` + `/api/queue`, so a failure from either endpoint aborted both. `loadIndustries()` silently swallowed API failures.

**Changes:**
- Updated `loadAll()` to `Promise.allSettled` with independent status/queue application and endpoint-specific operator toasts.
- Added diagnostics (`console.error`) for status and queue failures.
- Added resilient `loadIndustries()` fallback options.

**Files touched:**
- `lead_engine/dashboard_static/index.html`

**Commit:** `347a842`

---

# AI Development Log

Chronological record of all AI-assisted implementation passes on the Copperline project.
Update this file at the end of every pass.

---

## 2026-03-16

### Pass 20c — Live Scheduler Verification

**Goal:** Verify the automated scheduled-send system end-to-end against the live codebase.

**Files changed:** None (verification only).

**Results: 17/17 checks passed.**

- `CSV_WRITE_LOCK` confirmed as real mutex
- `_scheduler_started` guard confirmed no-op on second call
- Exactly 1 daemon thread `copperline-scheduler` running
- `_is_send_eligible`: future returns False, past-due returns True, no send_after returns True
- `send_next_due_email` returns False with no due rows; injected past-due row correctly selected
- Future row injected and confirmed NOT selected

**SMTP boundary:** Not tested end-to-end. Verification covers all logic up to `_send_email_via_gmail()` call site.

**Verdict: READY for overnight scheduled sending.**

**Commit:** `76be407` (Pass 20a, last code change — no new code this pass)

---
### Pass 18b — Human Draft Enforcement Layer

**Goal:** Add a post-processing layer to `draft_email()` that enforces human-style copy constraints after generation.

**Files changed:**
- `lead_engine/outreach/email_draft_agent.py`

**What changed:**

Added two new module-level constants:
- `_FORMAL_OPENER_SUBS` — list of `(pattern, replacement)` pairs for stripping/rewriting formal phrases and secondary banned words
- `_WORD_TARGET_MAX = 65` — soft word ceiling for body_text (sign-off excluded)

Added new function `enforce_human_style(body_text: str) -> str`:
- Applies all `_FORMAL_OPENER_SUBS` substitutions
- Lowercases opener on lines starting with `"Hey "` (not `"Hi "` — intentional)
- Trims to `_WORD_TARGET_MAX` by dropping last paragraph block if over limit — never mid-sentence

Wired call into `draft_email()` between body assembly and sign-off append.

**Sample output verified (5 drafts):** 54–65 words, 2–3 sentences per output, no formal phrases.

**No schema changes. No DRAFT_VERSION bump. No protected systems touched.**

**Commit:** `ff7564d`

---

### Pass 18a — Discovery State Reset (Phase 2)

**Goal:** Reset discovery-layer data to a clean post-outreach baseline.

**Files changed:**
- `lead_engine/scripts/reset_discovery_state.py` (new)
- `lead_engine/data/prospects.csv` (reset)
- `lead_engine/data/search_history.json` (cleared)
- `lead_engine/data/city_planner.json` (cleared)

**What changed:**
- `prospects.csv`: 231 rows → 43 rows. Kept only businesses matching gmail_sent preserve set. 188 unmatched rows archived.
- `search_history.json`: 31 entries → `[]`. Full backup archived.
- `city_planner.json`: 4 city entries → `{}`. Full backup archived.
- `reset_discovery_state.py`: reusable script with dry-run support, backup-before-write safety, queue integrity check.

**Queue integrity confirmed:** `pending_emails.csv` verified at 26 rows before and after reset.

**Commit:** `970a55c`

---

### Pass 17b — KPI Stats Audit: Relabel Prospects Card

**Goal:** Correct misleading "Prospects" KPI card that shows discovery pool count on the outreach queue page.

**Root cause:** `api_status` returns `prospects_loaded` from `prospects.csv`. After queue reset, live queue dropped to 26 rows but `prospects.csv` was untouched, causing stale display.

**Files changed:**
- `lead_engine/dashboard_static/index.html`

**What changed:**
- Renamed stat card label from `Prospects` → `Discovered`
- Added `title` attribute explaining independence from outreach queue

**Commit:** `59d3118`

---

### Pass 17a — Queue Reset: Gmail Preservation Mode

**Goal:** Reset the live outreach queue to a clean state, preserving only the 47 businesses actually contacted via Gmail.

**Files changed:**
- `lead_engine/scripts/reset_queue_from_gmail.py` (new)
- `lead_engine/scripts/gmail_sent_preserve_set_for_reset.csv` (new)
- `lead_engine/queue/pending_emails.csv` (reset)

**Live reset executed:**
- Original queue: 132 rows → Kept (Gmail-matched): 26 rows → Archived to `_backups/`: 106 rows

**Commit:** `8b5723b`

---
### Pass 16a — Bug Stabilization: normalize_business_name, discover 400, None guards

**Goal:** Fix three hard backend failures introduced by prior Codex UX passes.

**Files changed:**
- `lead_engine/discovery/prospect_discovery_agent.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/queue/queue_integrity.py`
- `lead_engine/queue/exception_router.py`

**Failures fixed:**
1. `NameError: normalize_business_name` (routes: `/api/queue_health`, `/api/exceptions`) — added missing function using existing `_NAME_NOISE_WORDS` and `_PUNCT_RE`
2. `/api/discover` and `/api/discover_area` returning 400 on all-duplicates — changed to `200` with `ok: false, all_duplicates: true`
3. `None .lower()` crashes — fixed with `(row.get("approved") or "").lower()`

**Commit:** `7e34d57`

---

### Pass 15b — Outreach Tone Correction: Operational Problem-First Messaging

**Goal:** Correct Pass 15a copy that drifted into generic automation-agency framing.

**Files changed:**
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/dashboard_static/index.html`

**What changed:**
- `_OPENING_QUESTIONS` — All three variants rewritten to open on specific operational gap (leads going cold, after-hours drop-off, follow-ups that don't happen).
- `_BODY_FIXED` — Rewritten to lead with what the business is currently losing, not what Copperline offers.
- `cvSendQuick` templates — Reworded to match problem-first framing.
- `DRAFT_VERSION` bumped `v5` → `v6`.

**Commit:** `fix: Pass 15b — correct outreach tone, lead with operational problems not automation framing`

---

### Pass 15a — Outreach Positioning: Remove Missed-Call-First Framing

**Goal:** Replace missed-call-product-first email templates with automation-audit framing.

**Files changed:**
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/dashboard_static/index.html`

**What changed:**
- `_OPENING_QUESTIONS`, `_BODY_FIXED` replaced with automation/workflow-oriented variants.
- `_BANNED` — Removed `"automation"`, `"automate"`, `"workflow"` from banned list.
- `DRAFT_VERSION` bumped `v4` → `v5`.

**Note:** This pass introduced automation-agency tone corrected in Pass 15b.

**Commit:** `feat: Pass 15a — reposition outreach templates to automation audit framing`

---

## 2026-03-16

### Pass 11 — Sent Mail Reconciliation Recovery

**Goal:** Prevent duplicate resends when Gmail sends succeeded but dashboard closed before queue state updated.

**Files changed:**
- `lead_engine/outreach/reply_checker.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

**What changed:**
- Added `reconcile_sent_mail()` to scan recent Gmail Sent messages and reconcile only approved+unsent queue rows.
- Matching key: recipient email + exact subject, limited to recent sent window (default 72h).
- Ambiguity handling is fail-safe: skip rows when multiple queue rows or Sent messages share a key.
- Added `/api/reconcile_sent` endpoint and UI action `↺ Check Sent`.

**Commit:** `aae0cb5`

---

### Pass 12 — Queue Bulk Action + Unschedule Fix

**Goal:** Restore reliable checked-row bulk approvals and provide explicit unschedule action.

**Files changed:**
- `lead_engine/dashboard_static/index.html`

**What changed:**
- Fixed bulk Approve / Unapprove race: replaced parallel `Promise.all` with sequential row updates.
- Changed schedule panel button from `Clear` to `Unschedule`.

**Commit:** `c40d16d`

---
### Pass 13 — Dashboard Startup Import Recovery

**Goal:** Restore dashboard startup by resolving missing symbols/modules in the server import chain.

**Files changed:**
- `lead_engine/discovery/prospect_discovery_agent.py`
- `lead_engine/run_lead_engine.py`
- `lead_engine/intelligence/website_scan_agent.py`
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/scoring/opportunity_scoring_agent.py`
- `lead_engine/city_planner.py`
- `lead_engine/intelligence/email_extractor_agent.py`

**What changed:**
- Added missing `clean_website_for_key()` to discovery agent.
- Removed stale `normalize_business_name` import from `run_lead_engine.py`.
- Added compatibility helpers: `generate_lead_insight`, `draft_social_messages`, `DRAFT_VERSION`, `compute_numeric_score`, `score_priority_label`.
- Added missing modules imported by dashboard server (`city_planner`, `email_extractor_agent`).

**Commit:** `c2234ea`

---

### Pass 14 — Dashboard UX Safety Cleanup

**Goal:** Remove misleading/dead dashboard actions and clarify operator-facing copy.

**Files changed:**
- `lead_engine/dashboard_static/index.html`

**What changed:**
- Disabled broken client leads navigation (`mcViewLeads` informational only).
- Added explicit tooltips to disabled client actions.
- Relabeled conversation quick actions to copy-oriented language.
- Added safety confirmation to `Approve All` with affected row count.
- Added map disclosure note for partial marker expectations.
- Marked Tools tab as `Stub` in top navigation.

**Commit:** `014e68c`

---

## 2026-03-15

### Pass A — Operator Safety Fixes

**Goal:** Prevent broken outreach messages and fix confusing UI without touching protected systems.

**Changes:**
- `COPPERLINE_LINKS` config block added at top of JS. `_clinkOr(url, fallback)` helper warns operator if links are unconfigured.
- `cvSendQuick` templates now reference `COPPERLINE_LINKS` via `_clinkOr`. Error toast fires if any link is still default.
- `mcRenderClients` table headers corrected to match actual backend schema.
- `mcRenderClients` tbody cells corrected: `c.phone`, `c.sms_reply`, `c.active`.
- Leads and Delete buttons in client rows: `disabled` + `opacity:.4`.
- Service badge initial text: `● Missed-Call: Not Configured`.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `4a169dd`

---

### Clients Route Fix

**Root cause:** Frontend calling `/api/mc/clients`, `/api/mc/clients/new`, `/api/mc/run_demo`. Backend implements `/api/clients`, `/api/clients/add`, `/api/demo_run`.

**Fixes:**
- `mcLoadClients()`: `/api/mc/clients` → `/api/clients`
- `mcSaveNewClient()`: `/api/mc/clients/new` → `/api/clients/add`
- `mcRunDemo()`: `/api/mc/run_demo` → `/api/demo_run`
- `mcApi()`: added `r.ok` guard

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `4c390fe`

---

### Runtime Verification Hotfixes

**Root causes found:**
- `api()` called `r.json()` unconditionally on non-OK responses, throwing `SyntaxError`.
- Map `click` event repositioned active circle on any tile click, wiping result markers.
- `Clear Coverage` button near-invisible.

**Fixes:**
- `api()`: added `if (!r.ok)` guard.
- `_mapInit` click handler: wraps `_mapDrawCircle` in `if (_mapResultItems.length === 0)` guard.
- `.btn-coverage`: raised text contrast.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `2b202cd`

---
### Emergency Fix — Duplicate `let _currentPage` SyntaxError

**Root cause:** Stale duplicate `let _currentPage = 'outreach'` declaration left from Step 1 nav restructure. Browsers enforce strict `let` uniqueness and threw fatal parse error: `Uncaught SyntaxError: Identifier '_currentPage' has already been declared`.

**Fix:** Removed the 5-line stale block. Single declaration remains.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `761faaf`

---

### Step 7 — Human-Readable Discovery Labels

**Changes:**
- Added `_mapAreaLabel(markers)`: frequency-counts `biz.city`, returns most common city name.
- Wired into `mapSearch()` `res.ok`: computes label before history unshift.
- Updated `_mapRenderHistory()`: `entry.label` as primary (fallback to `lat/lng` coords).

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `3f86767`

---

### Step 6 — Discovery History List

**Changes:**
- Added `_mapSearchHistory[]`, `MAP_HISTORY_MAX = 10`
- Added `_mapRenderHistory()` and `_mapClearHistory()`
- Added `#map-history` HTML below `#map-status` (hidden until first entry)

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `6d79c64`

---

### Step 5 — Discovery Coverage Memory

**Changes:**
- Added `_mapCoverageCircles[]` module variable
- Added `_mapClearCoverage()` and `.btn-coverage` CSS
- Wired `mapSearch()` `res.ok` branch to snapshot search area as faint `L.circle` overlay

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `f27a472`

---

### Step 4 — Map Result Usability Polish

**Changes:**
- Added sort select (default / Name A–Z / City A–Z) + email-only checkbox to results panel
- Refactored `_mapRenderPanel()` to read filter+sort state before building list

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `a19bc16`

---

### Step 3 — Results Side Panel (Discovery Map)

**Changes:**
- Added `#map-layout` flex wrapper around `#map-container` and new scrollable results panel
- Added `_mapResultItems[]` storing `{biz, marker}` pairs
- Added `_mapRenderPanel()` with click-to-zoom-and-popup behavior

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `c0caa17`

---

### Step 2 — Marker Clustering (Discovery Map)

**Changes:**
- Added Leaflet.markercluster v1.5.3 via CDN
- Initialized `L.markerClusterGroup()` inside `_mapInit()`
- Result markers now added to cluster group instead of directly to map

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `38da7c3`

---

## 2026-03-14

### Step 1 — Dashboard Navigation Restructure

**Goal:** Reduce 13-tab flat nav to a structured 5-section nav with sub-tabs.

**Changes:**
- Rebuilt top navigation from 13 flat tabs to 5 parent sections: Pipeline | Discovery | Clients | Health | Tools
- Added sub-tab system mapping to original page divs
- All original page divs preserved. No backend changes.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `1dc811a`

---

### Search History Improvements

**Changes:**
- Added summary stats to search history view
- Added rerun buttons to past search entries

**Commit:** `bcac905`

---
### Step 8 — Search Visible Area Button

**Goal:** Add a "Search Visible Area" button that tiles the current map viewport into 1000m-radius grid cells and runs sequential `/api/discover_area` calls.

**Changes:**
- `#btnSearchVisible` + `#btnCancelVisible` added to map toolbar
- `let _mapVisibleSearchActive` — loop-control flag
- `let _mapVisibleSeenKeys` — cross-tile Set for deduplicating markers
- `_mapAppendResultMarkers(markers)` — additive marker helper; never calls `_mapClearResultMarkers`
- `_mapVisibleTiles()` — tiles current viewport into lat/lng grid at 2000m step; rejects runs > 30 tiles
- `mapSearchVisible()` — sequential tiled discovery; 1200ms inter-tile delay; dedup via `_mapVisibleSeenKeys`
- `_mapCancelVisible()` — sets cancel flag; status text update

**Files changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `32ff2bf`

---

### Step 8a — Decouple Search Visible Area Button from Circle State

**Goal:** Remove erroneous dependency on `_mapCenter` / circle lifecycle from `#btnSearchVisible` enable/disable logic.

**Changes (3 lines removed, 1 line modified):**
1. `#map-industry` onchange — removed `||!window._mapCenter` condition.
2. `_mapDrawCircle()` — removed 2 lines that set `btnSearchVisible.disabled`.
3. `mapClearCircle()` — removed 1 line that set `btnSearchVisible.disabled = true`.

**Files changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `651df94`

---

### Pass 9a — Queue Visual Safety

**Goal:** Make scheduled/approved/draft states visually distinct in the outreach queue.

**Changes:**
- Added `.badge-scheduled`, `row-scheduled` CSS, `.panel-save-state` state variants.
- `statusBadge(row)` — new `🕐 Scheduled` amber pill for `send_after && !sent_at` rows.
- Added `🕐 Scheduled` filter tab.
- `panelFieldChanged()` — body edits drive `#panel-save-state`: `Saving…` / `Saved ✓` / `Error saving`.

**Files changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `f712909`

---

### Pass 9b — Scheduled Send Intent

**Goal:** Add `send_after` field to all queue schemas and wire a "Schedule for Tomorrow" button.

**Protected systems modified deliberately:**
- `run_lead_engine.py`, `dashboard_server.py`, `email_sender_agent.py`, `followup_scheduler.py`, `reply_checker.py` — all `PENDING_COLUMNS` extended
- `reply_checker.py` truncated 20-col schema bug fixed simultaneously

**Commits:**
- `24dc5b2` — add send_after to all queue schemas; fix reply_checker column truncation
- `52dd64a` — /api/schedule_email route (intent-only, no send trigger)
- `a5f09c5` — Schedule for Tomorrow button in review panel

---

### Pass 10 — Scheduled Queue UX

**Goal:** Make scheduled rows clearly usable day-to-day.

**Changes:**
- `/api/schedule_email` now accepts `send_after: ""` to clear a schedule.
- `_formatSendAfter(isoStr)` — returns Today/Tomorrow/weekday labels.
- Active filter now excludes `send_after` rows.
- Scheduled filter sorts by `send_after` asc.
- `#panel-schedule-info` added to panel with Clear / +1 day / +2 / +3 actions.
- `panelClearSchedule()` and `panelReschedule(days)` added.

**Files changed:**
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

**Commit:** `d31d720`
### 2026-03-17 - Pass 31: Contact Quality Upgrade

**Goal:** Increase the number of outreach-ready leads by extracting more usable contacts and cleaning message outputs without redesigning the broader system.

**Files changed:**
- `lead_engine/discovery/auto_prospect_agent.py`
- `lead_engine/intelligence/email_extractor_agent.py`
- `lead_engine/outreach/email_draft_agent.py`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- Expanded website email extraction to handle `mailto:` links with query strings, email-bearing attributes, simple `[at]` / `[dot]` obfuscation, paired `data-user` + `data-domain` attributes, and Cloudflare protected email tokens.
- Added bounded contact-page discovery and centralized website contact extraction so discovery and enrichment use the same logic.
- Strengthened extracted-email cleanup and candidate ranking so junk/placeholder values are suppressed more safely and stronger role/domain matches are preferred.
- Replaced the `email_extractor_agent.py` compatibility stub with a working enrichment pass for `prospects.csv`.
- Cleaned up outreach copy pools and guardrails to remove intentional sloppy phrasing, reduce awkward/run-on outputs, and keep social/contact-form companion drafts aligned with the shorter human style.
- Kept the pass off the protected systems: no queue schema, sender core, scheduler core, follow-up system, or `run_lead_engine.py` changes.

**Verification:**
- Ran `python -m py_compile` on all touched product files.
- Ran a targeted Python verification script that exercised representative hidden-email patterns, candidate ranking, enrichment updates on a temporary prospects CSV, and multiple email/social draft outputs.
- Reconfirmed the live dashboard still loads at `http://127.0.0.1:5000` after the backend changes.

**Commit:** `3098082`

---

### 2026-03-17 - Pass 30: Discovery Panel Organization + Edit Stability

**Goal:** Make large discovery result sets manageable inside the dashboard without redesigning the rest of the workflow.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- Reorganized the discovery results rail into grouped sections with workflow, city, email-status, and flat grouping modes.
- Switched the panel to score-first ordering by default and added clearer metadata density for faster scanning.
- Added active-result highlighting and an explicit `Edit` action from discovery results into the existing review panel.
- Stabilized review-panel navigation by anchoring it to a snapshot of the visible lead set instead of only the live filtered table.
- Updated panel actions to use the anchored row context so edit, approve, schedule, unschedule, campaign, and contact-log interactions keep the same lead open.
- Prevented accidental review-panel dismissal from overlay clicks and blocked close while debounced saves are still pending.
- Kept the pass frontend-only. No scheduler core, queue schema, sender, follow-up, or protected pipeline systems changed.

**Verification:**
- Extracted inline dashboard JavaScript and ran `node --check` successfully.
- Ran a live headless-browser smoke pass against the local dashboard server using a synthetic client-side discovery dataset to verify grouped result rendering, group switching, active selection, edit stability, close-guard behavior, and basic Pass 29 control availability without writing real queue edits.
- Confirmed only `lead_engine/dashboard_static/index.html` changed in product code.
- Reconfirmed protected systems were untouched.

**Commit:** `5d11595`

---

### 2026-03-17 - Pass 29: Discovery Coverage Expansion + Bulk Unschedule

**Goal:** Expand neighborhood discovery coverage from the existing map circle and let operators unschedule batches of scheduled outreach safely.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- Restored `lead_engine/dashboard_static/index.html` from the last committed baseline after a failed transfer left the live file as a 63-byte broken stub.
- Added `Search Area Grid` UI using the current map circle as a capped 1000m-cell grid.
- Added multi-industry grid selection, run estimation, hard caps of 36 cells / 120 calls, compact progress status, cancel support, and a single summarized history entry per grid sweep.
- Added current-run dedupe for accumulated grid markers using place ID first and stable fallbacks.
- Added bulk `Unschedule` to the outreach table and allowed scheduled rows to be selected in the Scheduled filter.
- Smoke stabilization fixed one UI bug so bulk `Unschedule` is visibly shown when scheduled rows are selected.
- Kept the pass frontend-only. No scheduler core, queue schema, sender, or follow-up systems changed.

**Verification:**
- Extracted inline dashboard JavaScript and ran `node --check` successfully.
- Ran a live headless-browser smoke checklist covering dashboard load, grid UI, multi-industry selection, oversized blocking, status updates, cancel recovery, history rendering, scheduled-row selection, bulk unschedule visibility/state, and existing single/visible/exhaust discovery actions.
- Confirmed only `lead_engine/dashboard_static/index.html` changed in product code.
- Confirmed protected files (`run_lead_engine.py`, queue schema/pipeline, scheduler core) were untouched.

**Commit:** `aaa3276`

---
### 2026-03-17 - Pass 32: Discovery Triage + Lead Qualification Controls

**Goal:** Reduce operator friction between discovery and outreach by making newly found leads faster to qualify into work-now, maybe-later, needs-contact, and weak/skip buckets.

**Changes:**
- Added a frontend-only qualification model in the discovery results rail using existing lead/result signals such as email presence, website/phone availability, queue state, and existing score/contactability hints.
- Added quick triage chips with live counts for `All`, `Ready`, `Maybe`, `Needs Contact`, `Weak`, and `No Email`.
- Added `Group: Qualification` to the discovery panel so large result sets can be sectioned by readiness rather than only workflow/city/email.
- Added compact qualification badges and reason chips on each discovery result to explain at a glance why a lead is strong, weak, or blocked by missing contactability.
- Kept Pass 30 edit stability intact by preserving the visible review context and verifying that overlay clicks still do not dismiss the review panel.

**Files touched:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**Commit:** `8868847`

---
### 2026-03-17 - Pass 33: Bulk Discovery-to-Outreach Workflow Acceleration

**Goal:** Reduce repetitive operator work once strong discovery leads have been identified by making the visible qualified subset faster to move into outreach review/actions.

**Changes:**
- Added a discovery-panel handoff layer built around the current visible subset after triage/filtering instead of forcing row-by-row `Edit` clicks.
- Added `Review Visible` to open the current visible discovery subset directly in the outreach review panel.
- Added `Prep Outreach` to bulk-approve outreach-ready visible rows and then open that prepared subset in review.
- Added compact visible-set summary counts for reviewable rows, outreach-ready rows, and rows that still need approval.
- Tightened discovery bulk actions to use the actual visible queue-row context rather than weaker business-name matching, keeping bulk behavior aligned with the current qualified view.

**Files touched:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**Commit:** `c1a56a4`

---
