### 2026-03-16 — Pass 11D: Industry Send Window UX Refinement

**Goal:** Make scheduling feel deliberate and industry-tailored while preserving manual Gmail sending and existing `send_after` queue semantics.

**Changes:**
- Added industry send-window helpers (`_industryWindowTime`, `_industryWindowLabel`, `_buildSendAfterFromWindow`) for coherent, operator-visible scheduling defaults.
- Updated review panel schedule actions and labels:
  - `Tomorrow @ Best Time`
  - `Schedule for Best Time`
  - `Next Best Window`
- Enhanced schedule info block with compact guidance:
  - industry default-time explanation
  - clear Approved vs Scheduled distinction
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
- Added a persistent discovery handoff bar under top navigation with truthful post-run summary and direct actions:
  - Review New Drafts
  - Continue Discovering
  - Return to Last Discovery Area
- Added lightweight session state for continuity:
  - `_lastDiscoveryHandoff`
  - `_lastDiscoveryMapContext`
  - `_captureMapContext(...)`
  - `_publishDiscoveryHandoff(...)`
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
- Added Sent Workspace context using existing fields: sent time, business, subject, reply badge, and follow-up hint.
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
- Simplified top-level navigation to direct destinations (Discovery, Queue, Scheduled, Sent, Follow-Up, Clients, System), reducing parent/sub-tab dependence.
- Added a workflow stage rail inside Outreach with live counts and quick stage jumps.
- Preserved queue-state separation and behavior: Actionable (unsent and not scheduled), Scheduled (send_after and not sent), Sent (sent_at), Replied.
- Improved queue empty-state messaging for mode-switch scenarios (e.g., no actionable rows but scheduled work exists).
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
- Added secondary row treatment and note labels (`stale draft`, `missing email`, `low fit`) to reduce visual weight of lower-priority rows.

**Files touched:**
- `lead_engine/dashboard_static/index.html`

**Commit:** `7da49b5`

---

### 2026-03-16 — Pass 15: Outreach Queue Regression Fix

**Goal:** Restore queue/stats/industry/table loading after the command-center cleanup regression while preserving the new filter architecture.

**Root cause:** `loadAll()` used `Promise.all` for `/api/status` + `/api/queue`, so a failure from either endpoint aborted both updates and left Outreach appearing fully broken. `loadIndustries()` silently swallowed API failures, leaving the industry selector stuck on “Loading…”.

**Changes:**
- Updated `loadAll()` to `Promise.allSettled` with independent status/queue application and endpoint-specific operator toasts.
- Added diagnostics (`console.error`) for status and queue failures.
- Added resilient `loadIndustries()` fallback options so the industry selector still initializes when `/api/industries` fails.
- Preserved existing Actionable/Pending/Approved/Scheduled/Done model and non-actionable bulk disable behavior from prior cleanup.

**Files touched:**
- `lead_engine/dashboard_static/index.html`

**Commit:** `347a842`

---

# AI Development Log

Chronological record of all AI-assisted implementation passes on the Copperline project.
Update this file at the end of every pass.

---

## 2026-03-16

### Pass 20c -- Live Scheduler Verification

**Goal:** Verify the automated scheduled-send system end-to-end against the live codebase.

**Files changed:** None (verification only).

**Verification script:** `_verify_20c.py` (temp, deleted after run).

**Results: 17/17 checks passed.**

Part 1 -- Imports and lock:
- `CSV_WRITE_LOCK` confirmed as a real mutex (`threading.Lock`)
- Second concurrent acquire correctly blocked

Part 2 -- Thread guard:
- `_scheduler_started` flips on first `_start_scheduler_once()` call
- Second call is a confirmed no-op
- Exactly 1 thread named `copperline-scheduler` running after both calls
- Thread is daemon and alive

Part 3 -- Early-send protection:
- Future `send_after` (+2 hours): `_is_send_eligible` returns `False`
- Past-due `send_after` (-5 seconds): returns `True`
- No `send_after`: returns `True`
- Malformed `send_after`: returns `True` (does not block)

Part 4 -- Row selection:
- `send_next_due_email` returns `False` with no due rows
- Injected past-due test row at queue position 26; confirmed selected as `target_idx`
- Queue restored to 26 rows after cleanup

Part 5 -- Future row not selected:
- Future row injected and confirmed NOT selected by scheduler logic
- Cleaned up

**SMTP boundary:** Not tested end-to-end. Verification covers all logic up to and including `_send_email_via_gmail()` call site. Actual delivery requires live Gmail credentials and safe recipient.

**Verdict: READY for overnight scheduled sending.** No fixes required.

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
- Applies all `_FORMAL_OPENER_SUBS` substitutions (strips formal openers, replaces residual banned words)
- Lowercases opener on lines starting with `"Hey "` (not `"Hi "` — intentional)
- Trims to `_WORD_TARGET_MAX` by dropping last paragraph block if over limit — never mid-sentence
- Does NOT sentence-split across `\n\n` paragraph breaks (deliberate: existing 3-paragraph structure is already correct format)

Wired call into `draft_email()` between body assembly and sign-off append:
```python
body_text = enforce_human_style(body_text)  # new
body = body_text + _SIGN_OFF
```

**Sample output verified (5 drafts):** 54–65 words, 2–3 sentences per output, no formal phrases, human tone confirmed.

**No schema changes. No DRAFT_VERSION bump (post-processing only — output structure unchanged). No protected systems touched.**

**Commit:** `ff7564d`

---

### Pass 18a — Discovery State Reset (Phase 2)

**Goal:** Reset discovery-layer data to a clean post-outreach baseline after Pass 17a cleaned the live queue.

**Files changed:**
- `lead_engine/scripts/reset_discovery_state.py` (new)
- `lead_engine/data/prospects.csv` (reset)
- `lead_engine/data/search_history.json` (cleared)
- `lead_engine/data/city_planner.json` (cleared)

**Root cause:** Pass 17a cleaned only `pending_emails.csv`. The three discovery-layer files were untouched, leaving legacy totals visible in the dashboard: "Discovered" KPI still showed 231, Discovery History tab still had 31 old runs, territory planner had stale city data.

**What changed:**

`prospects.csv`: 231 rows → 43 rows. Kept only businesses matching gmail_sent preserve set (by email or name). 188 unmatched rows archived to `_backups/`.

`search_history.json`: 31 entries → `[]`. Full backup archived.

`city_planner.json`: 4 city entries → `{}`. Full backup archived.

`reset_discovery_state.py`: reusable script with dry-run support, backup-before-write safety, and queue integrity check.

**Queue integrity confirmed:** `pending_emails.csv` verified at 26 rows before and after reset.

**Backups in `_backups/` (local, not committed):**
- `prospects_pre_reset_phase2_20260317T012825Z.csv`
- `prospects_archived_unmatched_20260317T012825Z.csv`
- `search_history_pre_reset_phase2_20260317T012825Z.json`
- `city_planner_pre_reset_phase2_20260317T012825Z.json`

**Commit:** `970a55c`

---

### Pass 17b — KPI Stats Audit: Relabel Prospects Card

**Goal:** Correct misleading "Prospects" KPI card that shows discovery pool count (`prospects.csv`) on the outreach queue page, making it appear stale after a queue reset.

**Root cause:** `api_status` returns `prospects_loaded` from `_prospects_count()`, which reads `data/prospects.csv` (all ever-discovered businesses). All other KPI cards read from `pending_emails.csv` (live queue). After Pass 17a's queue reset, the live queue dropped to 26 rows but `prospects.csv` was untouched, causing the "Prospects" card to show a legacy total while everything else reflected the clean state.

**Files changed:**
- `lead_engine/dashboard_static/index.html`

**What changed:**
- Renamed stat card label from `Prospects` → `Discovered`
- Added `title` attribute: `"Total businesses in discovery pool (prospects.csv) — independent of outreach queue"`
- No backend changes, no logic changes, no schema changes

**Commit:** `59d3118`

---

### Pass 17a — Queue Reset: Gmail Preservation Mode

**Goal:** Reset the live outreach queue to a clean state after debugging/testing, preserving only the 47 businesses actually contacted via Gmail.

**Files changed:**
- `lead_engine/scripts/reset_queue_from_gmail.py` (new)
- `lead_engine/scripts/gmail_sent_preserve_set_for_reset.csv` (new)
- `lead_engine/queue/pending_emails.csv` (reset)

**What changed:**

New script `reset_queue_from_gmail.py`: one-time queue cleanup utility. Creates a timestamped backup before any write. Matches queue rows to gmail_sent.csv by normalized email (primary) or normalized business name (fallback). Asset-filename fake emails (e.g. `.webp`) are correctly excluded from email matching and caught by name fallback. Keeps matched rows with `approved=true`, `send_after=""`, and `sent_at` populated from gmail sent_date. Preserves all reply/conversation/followup fields. Archives all unmatched rows to `_backups/` — no permanent deletion.

Live reset executed:
- Original queue: 132 rows
- Kept (Gmail-matched): 26 rows (25 by email, 1 by name)
- Archived to `_backups/`: 106 rows
- Unmatched Gmail entries: 20 (real sends to businesses not in the current queue)
- Backup: `pending_emails_pre_reset_20260317T003530Z.csv`
- Archive: `pending_emails_archived_unmatched_20260317T003530Z.csv`

**No schema changes. No protected-system rewrites. No feature work.**

**Commit:** `8b5723b`

---

### Pass 16a — Bug Stabilization: normalize_business_name, discover 400, None guards

**Goal:** Fix three hard backend failures introduced by prior Codex UX passes that left the dashboard unusable for queue health, exception scanning, and map discovery.

**Files changed:**
- `lead_engine/discovery/prospect_discovery_agent.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/queue/queue_integrity.py`
- `lead_engine/queue/exception_router.py`

**Failure 1 — `NameError: normalize_business_name` (routes: `/api/queue_health`, `/api/exceptions`)**

Root cause: `dedupe_key_for_prospect()` called `normalize_business_name()` which was documented but never written. Every call crashed at runtime, taking down `queue_integrity.py` and `exception_router.py`.

Fix: Added `normalize_business_name()` using existing `_NAME_NOISE_WORDS` and `_PUNCT_RE`. Additive — no existing logic modified.

**Failure 2 — `/api/discover` and `/api/discover_area` returning 400 on all-duplicates**

Root cause: Both routes returned HTTP 400 when all results were already in the pipeline. Frontend treated any non-2xx as a generic connection failure.

Fix: Changed both zero-new-results paths from `400` → `200` with `ok: false, all_duplicates: true`.

**Failure 3 — `None` `.lower()` crashes in queue helpers**

Root cause: `queue_integrity.py` and `exception_router.py` used `row.get("approved", "").lower()` which crashes when the value is `None`. Fixed with `(row.get("approved") or "").lower()`.

**Verification:** `py_compile` clean on all 4 files. No logic changes. No schema changes. No protected systems touched.

**Commit:** `7e34d57`

---

### Pass 15b — Outreach Tone Correction: Operational Problem-First Messaging

**Goal:** Correct Pass 15a copy that drifted into generic automation-agency framing. Lead with operational problems the business owner recognizes, not automation as the hook.

**Root cause of correction:** Pass 15a opened with "do you have automations in place" and "workflow wins" — language that sounds like a tech vendor, not a peer who understands service business operations. The fix is to anchor every opening in a concrete loss scenario the owner already feels.

**Files changed:**
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/dashboard_static/index.html`

**What changed:**

`_OPENING_QUESTIONS` — All three variants rewritten. Old: led with automation/workflows as the frame. New: opens on a specific operational gap (leads going cold, after-hours drop-off, follow-ups that don't happen).

`_BODY_FIXED` — Rewritten. Old: "clean up the gaps / map out the quick wins" (service-agency pitch). New: "capture the work that slips through — calls that don't get answered, estimates that go cold, follow-ups that never happen." CTA is soft and conditional: "worth a few minutes if any of that's a real problem for you."

`cvSendQuick` templates in `index.html` — Reworded to match: demo template now says "how this works in practice… lmk if any of it looks familiar"; call template says "where work might be slipping through"; case study says "what we fixed for a similar business."

`DRAFT_VERSION` bumped `v5` → `v6` to flag stale drafts generated under 15a copy.

**No logic changes. No routing changes. No schema changes. No protected systems touched.**

**Commit:** `fix: Pass 15b — correct outreach tone, lead with operational problems not automation framing`

---

### Pass 15a — Outreach Positioning: Remove Missed-Call-First Framing

**Goal:** Replace missed-call-product-first email templates with automation-audit framing to reflect Copperline's repositioning as a service business operations provider.

**Files changed:**
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/dashboard_static/index.html`

**What changed:**
- `_OPENING_QUESTIONS` — Replaced missed-call-centric questions with automation/workflow-oriented variants.
- `_BODY_FIXED` — Replaced "text-back line" pitch with audit/gap framing.
- `_BANNED` — Removed `"automation"`, `"automate"`, `"workflow"` from banned list. These are now core positioning words; banning them was incompatible with the new direction.
- `DRAFT_VERSION` bumped `v4` → `v5`.
- `cvSendQuick` templates in `index.html` — Removed explicit "Missed Call Text-Back system" references; reworded toward automation overview language.

**Note:** This pass introduced automation-agency tone that was corrected in Pass 15b.

**No logic changes. No protected systems touched.**

**Commit:** `feat: Pass 15a — reposition outreach templates to automation audit framing`

---

## 2026-03-16

### Pass 11 — Sent Mail Reconciliation Recovery

**Goal:** Prevent duplicate resends when Gmail sends succeeded but the dashboard closed before queue state updated.

**Files changed:**
- `lead_engine/outreach/reply_checker.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

**What changed:**
- Added `reconcile_sent_mail()` to scan recent Gmail Sent messages and reconcile only approved+unsent queue rows.
- Matching key is strict: recipient email + exact subject, limited to recent sent window (`lookback_hours`, default 72h).
- Ambiguity handling is fail-safe: if multiple queue rows share a key or multiple Sent messages match a key, rows are skipped and not modified.
- Added dashboard API endpoint `/api/reconcile_sent` and UI action `↺ Check Sent` to trigger operator recovery.
- Reconciliation writes `sent_at` and captures Gmail `Message-ID` when present; no lead deletion and no resend path invoked.

**Commit:** `aae0cb5`

## 2026-03-16


### Pass 12 — Queue Bulk Action + Unschedule Fix

**Goal:** Restore reliable checked-row bulk approvals and provide explicit unschedule action in the panel UI.

**Files changed:**
- `lead_engine/dashboard_static/index.html`

**What changed:**
- Fixed bulk Approve / Unapprove race by replacing parallel `Promise.all` queue writes with sequential row updates.
- Kept bulk Delete/Clear and single-row approve/unapprove behavior intact.
- Changed schedule panel button from `Clear` to explicit `Unschedule` for operator clarity.
- Unschedule path reuses guarded `/api/schedule_email` with `send_after: ""`; no new route added.
- No send logic changes, no queue schema changes, no protected backend edits.

**Commit:** `c40d16d`

## 2026-03-16


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
- Added compatibility helpers expected by `run_lead_engine.py` (`generate_lead_insight`, `draft_social_messages`, `DRAFT_VERSION`, `compute_numeric_score`, `score_priority_label`).
- Added missing modules imported by dashboard server (`city_planner`, `email_extractor_agent`).
- Verified `dashboard_server.py` starts and binds to localhost without the previous import errors.

**Commit:** `c2234ea`

## 2026-03-16

### Pass 14 — Dashboard UX Safety Cleanup

**Goal:** Remove misleading/dead dashboard actions and clarify operator-facing copy without backend changes.

**Files changed:**
- `lead_engine/dashboard_static/index.html`

**What changed:**
- Disabled active navigation into broken client leads surface by making `mcViewLeads` informational only.
- Kept client Leads/Delete surfaces disabled and added explicit tooltips for both.
- Relabeled conversation quick actions to copy-oriented language while preserving clipboard behavior.
- Added safety confirmation to `Approve All` including affected row count and explicit write warning.
- Added short map disclosure note clarifying queue/draft authority and partial marker expectations.
- Marked Tools tab as `Stub` in top navigation.

**Commit:** `014e68c`

## 2026-03-15

### Pass A — Operator Safety Fixes

**Goal:** Prevent broken outreach messages and fix confusing UI without
touching any protected systems.

**Changes:**

1. **`COPPERLINE_LINKS` config block** added at top of JS (above `let allRows`).
   Contains `demo`, `booking`, `caseStudy` URL slots. Operator updates these
   once before sending live templates. `_clinkOr(url, fallback)` helper
   returns the URL if configured, or a `⚠` warning string if still default.

2. **`cvSendQuick` templates** now reference `COPPERLINE_LINKS` via `_clinkOr`.
   If any link is unconfigured, the `⚠` string appears in the copied text AND
   an error toast fires: `⚠ Template contains unconfigured link`. Operator
   cannot accidentally send `[INSERT DEMO LINK]` to a live lead.
   Call template now includes a booking link instead of open-ended question.

3. **`mcRenderClients` table headers** corrected: Twilio Number / Owner Phone /
   Sheet / Notify → Phone / SMS Reply / Status (matches actual backend schema).

4. **`mcRenderClients` tbody cells** corrected: `c.twilio_number` / `c.owner_phone`
   / `c.sheet_name` / `c.notification_channel` (all non-existent) →
   `c.phone`, `c.sms_reply`, `c.active` status badge.

5. **Leads and Delete buttons** in client rows: `disabled` + `opacity:.4` +
   `title="Feature not available yet"`. No longer fire broken 404 routes.

6. **Service badge** initial text: `● Missed-Call: Not Configured` with tooltip
   `"The missed-call automation service has not been configured yet.
   This does not affect discovery or outreach."` `mcCheckHealth` still
   overrides to Online/Offline if the service actually starts running.

**Protected systems modified:** None.
**Backend files modified:** None.
**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `4a169dd`

---

### Clients Route Fix

**Root cause:** Frontend was calling `/api/mc/clients`, `/api/mc/clients/new`,
and `/api/mc/run_demo`. Backend never had those paths — it implements
`/api/clients`, `/api/clients/add`, and `/api/demo_run` respectively. The
mismatch caused 404s that surfaced as `SyntaxError: Unexpected end of input`
before the `api()` HTTP guard was in place.

**Fixes:**
- `mcApi()`: added `r.ok` guard matching the `api()` fix in `2b202cd`
- `mcLoadClients()` (×2 call sites): `/api/mc/clients` → `/api/clients`
- `mcSaveNewClient()`: `/api/mc/clients/new` → `/api/clients/add`
- `mcRunDemo()`: `/api/mc/run_demo` → `/api/demo_run`

**Remaining unimplemented:** `DELETE /api/mc/clients/{id}` and
`GET /api/mc/clients/{id}/leads` — no backend routes exist for these.
Buttons will show a clean error toast. Backend work needed separately.

**Schema note:** Backend client fields use `client_id`, `business_name`,
`phone`, `sms_reply`. Frontend renders `c.twilio_number` which is not in the
backend schema — that cell will render blank until schema is aligned.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `4c390fe`

---

### Runtime Verification Hotfixes

**Diagnosed from live browser session (5 screenshots + console log).**

**Root causes found:**
- `api()` called `r.json()` unconditionally. `/api/mc/clients` (missing backend
  route) returns 404 HTML. Parsing `<!DOCTYPE html>` as JSON throws
  `SyntaxError: Unexpected end of input at (index):1:10`. Fired on every
  health check cycle (30s interval) and every Clients tab open.
- Map `click` event repositioned the active circle on any tile click, wiping
  result markers without warning.
- `Clear Coverage` button was near-invisible (text color `var(--dim)`).

**Fixes:**
- `api()`: added `if (!r.ok)` guard — throws `Error("API /path returned N: ...")`
  on non-OK responses. All callers have `try/catch` so errors surface cleanly.
- `_mapInit` click handler: wraps `_mapDrawCircle` in
  `if (_mapResultItems.length === 0)` guard. Circle repositions freely when
  no results loaded; locked once results are present until `X Clear` used.
- `.btn-coverage`: raised text to `var(--muted)`, border to `var(--border-hi)`,
  hover to `var(--text)` + blue border.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `2b202cd`

**Parse check:** `vm.Script` PARSE OK on served JS post-fix.

---

### Emergency Fix — Duplicate `let _currentPage` SyntaxError

**Root cause:** Stale duplicate `let _currentPage = 'outreach'` declaration
left over from the Step 1 nav restructure (commit `1dc811a`). The duplicate
sat at line 2011, above the real declaration at line 2018. Browsers enforce
strict `let` uniqueness in script scope and threw a fatal parse error:

`Uncaught SyntaxError: Identifier '_currentPage' has already been declared`

This killed the entire script block at parse time — nothing functioned.

**Diagnosis path:** Browser DevTools console showed the exact error at line
2018. Node `vm.Script` parse check on the served JS confirmed the issue and
confirmed the fix.

**Fix:** Removed the 5-line stale block (orphaned comment + duplicate `let`).
Single declaration at line 2013 remains.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `761faaf`

---

### Step 7 — Human-Readable Discovery Labels

**Goal:** Replace raw coordinates as primary history label with a city name
derived from already-loaded result data.

**Changes:**
- Added `_mapAreaLabel(markers)`: frequency-counts `biz.city` across result
  set, returns most common city name, null if no city data present
- Wired `mapSearch()` `res.ok`: computes label before history unshift,
  stores as `label` field on history entry
- Updated `_mapRenderHistory()`: `entry.label` as primary (fallback to
  `lat/lng` coords); secondary shows `X.X mi — N found`; exact coords
  preserved as `title` attribute for hover

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `3f86767`

---

### Step 6 — Discovery History List

**Goal:** Session-only recent searches list below the map. Click to refocus.

**Changes:**
- Added `_mapSearchHistory[]`, `MAP_HISTORY_MAX = 10`
- Added `_mapRenderHistory()`: builds `.mh-item` rows with `lat/lng`, radius
  in miles, and `found` count; click handler sets `_mapRadiusM`, calls
  `_mapDrawCircle()`, then `setView()` to recenter
- Added `_mapClearHistory()`: resets array, hides `#map-history`
- Added `#map-history` HTML below `#map-status` (hidden until first entry)
- Added CSS: `#map-history`, `.mh-hdr`, `.mh-title`, `.mh-clear`,
  `.mh-list`, `.mh-item`, `.mh-item-label`, `.mh-item-meta`
- Wired `mapSearch()` `res.ok`: `unshift` entry, trim to `MAP_HISTORY_MAX`,
  call `_mapRenderHistory()`
- Coverage, clustering, result markers unchanged

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `6d79c64`

---

### Step 5 — Discovery Coverage Memory

**Goal:** Persist prior search areas as faint map overlays for the current
session so the operator can see where they have already searched.

**Changes:**
- Added `_mapCoverageCircles[]` module variable
- Added `_mapClearCoverage()` — calls `.remove()` on each overlay, resets
  array, hides `btnClearCoverage`
- Added `.btn-coverage` CSS class for the toolbar button
- Added `#btnClearCoverage` button to map toolbar (`display:none` by default)
- Wired `mapSearch()` `res.ok` branch to snapshot `_mapCenter` + `_mapRadiusM`
  as `L.circle` with `interactive:false`, `dashArray:'4 4'`, `fillOpacity:0.04`,
  blue tint — pushed to `_mapCoverageCircles[]`, button revealed
- Active circle, drag handle, clustering, result markers all unchanged

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `f27a472`

---

### Step 4 — Map Result Usability Polish

**Goal:** Add sort and filter controls to the results panel without touching
discovery flow, backend, or clustering.

**Changes:**
- Added CSS: `.mrp-controls`, `.mrp-ctrl-select`, `.mrp-ctrl-chk` classes
- Added HTML controls row (`#mrp-controls`) between header and list:
  sort select (default / Name A–Z / City A–Z) + email-only checkbox
- Refactored `_mapRenderPanel()` to read filter+sort state from DOM controls
  before building list; `_mapResultItems[]` is never mutated
- Count shows `(N of M)` when email filter is active
- Extended `_mapClearResultMarkers()` to reset `mrp-sort` and `mrp-email-only`

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `a19bc16`

---

### Step 3 — Results Side Panel (Discovery Map)

**Goal:** Show a scrollable list of discovered businesses alongside the map
after a discovery search completes.

**Changes:**
- Added CSS: `#map-layout`, `#map-results-panel`, `.mrp-hdr`, `.mrp-list`,
  `.mrp-item`, `.mrp-name`, `.mrp-meta`, `.mrp-dot` classes
- Added `#map-layout` flex wrapper in HTML around `#map-container` and new panel
- Added `#map-results-panel` div with header (`mrp-count`) and scrollable list
- Added `_mapResultItems[]` module variable storing `{biz, marker}` pairs
- Added `_mapRenderPanel()` — renders list items, binds click to
  `zoomToShowLayer()` + `openPopup()` per marker
- Extended `_mapClearResultMarkers()` to reset `_mapResultItems` and hide panel
- Extended `_mapPlaceResultMarkers()` to push to `_mapResultItems` and call render

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `c0caa17`

---

### Step 2 — Marker Clustering (Discovery Map)

**Goal:** Group discovery result markers into cluster bubbles that split on
zoom-in and regroup on zoom-out.

**Changes:**
- Added Leaflet.markercluster v1.5.3 CSS + JS via CDN (`<head>`)
- Added `_mapClusterGroup` module variable
- Initialized `L.markerClusterGroup()` inside `_mapInit()` after tile layer
- Changed result marker creation from `.addTo(_mapInstance)` to `.addTo(_mapClusterGroup)`
- Updated `_mapClearResultMarkers()` to call `_mapClusterGroup.clearLayers()`
- Drag handle and circle markers unchanged

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `38da7c3`

---

## 2026-03-14

### Step 1 — Dashboard Navigation Restructure

**Goal:** Reduce 13-tab flat nav to a structured 5-section nav with sub-tabs.

**Changes:**
- Rebuilt top navigation from 13 flat tabs to 5 parent sections
- Added sub-tab system mapping to original page divs
- Sections: Pipeline | Discovery | Clients | Health | Tools
- All original page divs preserved and intact
- No backend changes

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `1dc811a`

---

### Search History Improvements

**Goal:** Improve usability of the Searches page in the dashboard.

**Changes:**
- Added summary stats to search history view
- Added rerun buttons to past search entries

**Commit:** `bcac905`

---

### Step 8 — Search Visible Area Button

**Date:** 2026-03-16

**Goal:** Add a "Search Visible Area" button that tiles the current map
viewport into 1000m-radius grid cells and runs sequential
`/api/discover_area` calls across each cell, accumulating markers without
clearing existing results.

**Changes:**

- `#btnSearchVisible` + `#btnCancelVisible` added to map toolbar
  (after `#btnMapSearch`, before Clear)
- `#map-industry` gains `onchange` to keep `#btnSearchVisible` synced
- `let _mapVisibleSearchActive` — loop-control flag
- `let _mapVisibleSeenKeys` — cross-tile Set for deduplicating markers
- `_mapRenderHistory()` — guards `radiusM: null`; shows "tiled" label;
  click handler no longer overwrites `_mapRadiusM` with null
- `_mapAppendResultMarkers(markers)` — additive marker helper; never
  calls `_mapClearResultMarkers`
- `_mapVisibleTiles()` — tiles current viewport into lat/lng grid at
  2000m step; rejects runs > 30 tiles
- `mapSearchVisible()` — sequential tiled discovery; 1200ms inter-tile
  delay; dedup via `_mapVisibleSeenKeys`; coverage circles per productive
  tile; single history entry with `radiusM: null` on completion
- `_mapCancelVisible()` — sets cancel flag; status text update
- `_mapDrawCircle` / `mapClearCircle` extended to mirror `#btnSearchVisible`
  enable/disable state

**Files changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `32ff2bf`

---

### Step 8a — Decouple Search Visible Area Button from Circle State

**Date:** 2026-03-16

**Goal:** Remove erroneous dependency on `_mapCenter` / circle lifecycle from
`#btnSearchVisible` enable/disable logic. Button should be gated on industry
selection only.

**Root cause:** Step 8 added `btnSearchVisible` enable/disable calls into
`_mapDrawCircle()` and `mapClearCircle()`, and the `onchange` handler on
`#map-industry` included `!window._mapCenter` as a secondary gate.

**Changes (3 lines removed, 1 line modified):**

1. `#map-industry` onchange — removed `||!window._mapCenter` condition.
   Button now enables on industry selection regardless of circle state.

2. `_mapDrawCircle()` — removed 2 lines that read `map-industry` value and
   set `btnSearchVisible.disabled`. Circle draw no longer affects button.

3. `mapClearCircle()` — removed 1 line that set `btnSearchVisible.disabled = true`.
   Clearing the circle no longer affects button.

**Preserved:**
- `mapSearchVisible()` still disables button during active run and re-enables on completion
- `#btnSearchVisible` starts `disabled` in HTML (correct — no industry selected yet)
- All other map behavior unchanged

**Files changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `651df94`

---

### Pass 9a — Queue Visual Safety

**Date:** 2026-03-16

**Goal:** Make scheduled/approved/draft states visually distinct in the
outreach queue without any backend changes. Add save state feedback to the
draft panel body editor.

**Changes (frontend-only, `index.html`):**

1. **CSS** — Added `.badge-scheduled`, `tbody tr.row-scheduled td:first-child`
   (amber left border), `.panel-save-state` with `.saving` / `.saved` /
   `.save-err` state variants.

2. **`statusBadge(row)`** — New priority slot between stale and approved:
   `send_after && !sent_at` → `🕐 Scheduled` amber pill with send time tooltip.

3. **Filter tab HTML** — `🕐 Scheduled` tab appended after `High Score`.

4. **`applyFiltersAndSort()`** — `scheduled` branch:
   `rows.filter(r => r.send_after && !r.sent_at)`.

5. **`renderTable()`** — `scheduledClass` variable added; applied to `<tr>`.

6. **`panelFieldChanged()`** — Body edits drive `#panel-save-state`:
   `Saving…` on keystroke, `Saved ✓` on resolve, `Error saving` on reject.
   Subject/email edits use silent save (unchanged).

**Pre-flight audit finding (blocking Pass 9b):**
`_write_pending_rows()` in `run_lead_engine.py` uses `PENDING_COLUMNS` as the
exclusive column list. Any `send_after` field written externally will be
silently stripped on next engine run. Pass 9b requires adding `send_after` to
`PENDING_COLUMNS` — a protected-system change needing operator approval.

**Files changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `f712909`

---

### Pass 9b — Scheduled Send Intent

**Date:** 2026-03-16

**Goal:** Add `send_after` field to all queue schemas and wire a "Schedule
for Tomorrow" button that writes send intent without triggering any send.

**Protected systems modified deliberately:**
- `run_lead_engine.py` — `PENDING_COLUMNS` extended
- `dashboard_server.py` — `PENDING_COLUMNS` extended + new route
- `send/email_sender_agent.py` — `PENDING_EMAIL_COLUMNS` extended
- `outreach/followup_scheduler.py` — `PENDING_COLUMNS` extended
- `outreach/reply_checker.py` — schema corrected (was truncated to 20 cols)

**Pre-flight audit finding resolved:**
`reply_checker.py` had a pre-existing data-loss bug: its `PENDING_COLUMNS`
was truncated to 20 fields. All reply-matched row writes silently stripped
21 fields. Fixed in Commit A alongside the schema extension.

---

**Commit A — `24dc5b2`**
`fix+feat: add send_after to all queue schemas; fix reply_checker column truncation`

Files: `run_lead_engine.py`, `dashboard_server.py`, `email_sender_agent.py`,
`followup_scheduler.py`, `reply_checker.py`

Appended `"send_after"` to end of all five `PENDING_COLUMNS` lists.
Replaced `reply_checker.py` truncated 20-col list with full 42-col schema.

Verification: all 5 modules 42 cols, `send_after` last, first-41 order
preserved. CSV loads 174 rows cleanly, `send_after` defaults to `""`.

---

**Commit B — `52dd64a`**
`feat: Pass 9b — /api/schedule_email route (intent-only, no send trigger)`

File: `dashboard_server.py`

Added `POST /api/schedule_email`. Validates index, business_name, send_after,
index/name match. Writes `send_after` only. No send triggered.

Verification: all 10 static checks passed.

---

**Commit C — `a5f09c5`**
`feat: Pass 9b — Schedule for Tomorrow button in review panel`

File: `lead_engine/dashboard_static/index.html`

Added `SEND_WINDOWS` const, `panelScheduleTomorrow()` function,
`#panel-schedule-btn` in panel footer, `fillPanel` show/hide wiring.
Button hidden on sent rows. Intent-only — no auto-send.

Verification: all 19 static checks passed.

---

### Pass 10 — Scheduled Queue UX

**Date:** 2026-03-16

**Goal:** Make scheduled rows clearly usable day-to-day — readable send times
in the table, panel schedule info block, clear/reschedule actions, Active
filter exclusion, and chronological sort of the Scheduled view.

**Changes:**

**`dashboard_server.py`:**
- `/api/schedule_email` updated to accept `send_after: ""` for clearing
- `send_after_raw is None` → 400 (absent); `""` → accepted (clears);
  non-empty string → schedules
- All identity/bounds/name-match validation preserved
- No other field touched, no send triggered

**`dashboard_static/index.html`:**
- `_formatSendAfter(isoStr)` — local date parser, returns Today/Tomorrow/weekday labels
- Table `td-status` cell: muted sub-line with formatted send time for scheduled rows
- `applyFiltersAndSort` Active filter: added `!r.send_after` exclusion
- `applyFiltersAndSort` Scheduled filter: added `localeCompare` sort by `send_after` asc
- CSS: `.panel-sched-info`, `.sched-time`, `.btn-sched-act` added
- `#panel-schedule-info` HTML element added to panel
- `fillPanel` extended: renders schedule info block with formatted time + 4 action buttons
- `panelClearSchedule()` — clears via `/api/schedule_email` with `send_after: ""`
- `panelReschedule(days)` — reschedules to today+N at SEND_WINDOWS time

**No send logic changed. No schema changes. No auto-send.**

**Files changed:**
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

**Commit:** `d31d720`
