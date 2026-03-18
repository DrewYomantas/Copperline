### 2026-03-17 - Pass 43: V2 Stage 2F — Next-Action-Driven Controls + History Visibility

### 2026-03-18 - Pass 44: Durable Lead Memory + Suppression Registry

**Goal:** Ensure leads that were contacted, deleted, suppressed, held, or opted-out are durably remembered and do not casually resurface in fresh discovery. Provide an operator-accessible inspector and revive path.

**Files changed:**
- `lead_engine/lead_memory.py` (new)
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**

`lead_memory.py` (new standalone module):
- Persists to `lead_engine/data/lead_memory.json` — fully independent of queue CSV.
- Identity key mirrors frontend `_leadKey()`: `pid:` > `web:` > `ph:` > `nc:name|city`.
- Suppression states: `contacted`, `suppressed`, `deleted_intentionally`, `do_not_contact`, `hold`, `revived`.
- All writes are lock-protected with atomic tmp-then-rename.
- Public API: `record_suppression`, `revive_lead`, `is_suppressed`, `get_record`, `get_suppressed_keys`, `suppressed_identity_sets`, `lead_key`.

`dashboard_server.py`:
- `import lead_memory as _lm` added.
- `api_delete_row` — records `deleted_intentionally` before queue pop. Memory survives deletion.
- `api_opt_out_row` — records `do_not_contact` in durable memory after queue write.
- `POST /api/suppress_lead` — operator-triggered suppression with explicit state.
- `POST /api/revive_lead` — clears suppression, adds `revived` history entry.
- `GET /api/lead_memory` — all records, filterable by `suppressed_only` and `q`.
- `POST /api/lead_memory/check` — single-lead suppression check by any identity signal.
- `api_discover_area` markers — suppressed leads excluded from default results; `?include_suppressed=1` to override.
- All memory calls wrapped in try/except — failure never blocks a queue operation.

`index.html`:
- Hold button added to panel footer — suppresses from discovery without deleting the row.
- Tools nav gains Lead Memory sub-tab with searchable, filterable record table.
- Per-row Revive button for suppressed leads in the memory inspector.
- `_runPageHooks` wired: navigating to `lead-memory` auto-loads the table.

**No protected systems touched. No queue schema changes.**

**Verification:**
- `python -c "import lead_memory; import dashboard_server"` — both clean.
- `node --check` on extracted dashboard JS — clean.
- 6/6 functional checks passed (deleted_intentionally, hold, revive, do_not_contact, suppressed_identity_sets, revived absent from suppressed_keys).

**Commit:** `e4cfc38`

---

### 2026-03-17 - Pass 43: V2 Stage 2F — Next-Action-Driven Controls + History Visibility

**Goal:** Make operator controls and visibility cues follow the shared lead record model more clearly so the next step is easier to see and act on.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- Added shared UI helpers: `_leadNeedsDraftRefresh`, `_leadHistoryItems`, `_leadHistoryChipsHtml`, `_leadNextActionContext`, and `_leadControlGuidance`.
- Shared header and status renderers now lean on `_leadStatusMeta(_leadRecord(...))` for clearer blocked/sent/replied/stale meaning.
- Queue status cells now show shared history chips for approved, scheduled, sent, replied, stale, and observation-present state.
- `_leadRecord.nextAction` now prioritizes stale / missing-observation refresh work before send-oriented actions.
- Review panel footer actions, discovery list actions, flow notes, and preview-modal buttons now relabel and emphasize controls from shared control guidance.

**No backend changes. No queue schema changes. No protected systems touched.**

**Verification:**
- `node --check` clean on extracted dashboard JS.
- Live dashboard verified at `http://127.0.0.1:5051`.
- Port `5000` was occupied by another local app, so verification used `5051`.

**Commit:** `5a09991`

---

### 2026-03-17 - Pass 42: V2 Stage 2E — Qualification + Status Derivation Unification

**Goal:** Centralize qualification bucket and status badge/label derivation so Discovery and Pipeline use the same shared helpers, not parallel inline logic.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- `_leadRecord` extended: `hasWebsite`, `hasPhone`, `isStale`, `isReadyScheduled` added.
- `_leadQualBucket(record, extras)` — shared qualification bucket (ready/maybe/needs-contact/weak/closed).
- `_leadStatusMeta(record)` — shared status badge/label/subline/detail/tone.
- `_queueStateMeta` rewritten as `return _leadStatusMeta(_leadRecord(row))`.
- `_mapPanelQualification` rewritten as thin wrapper over `_leadRecord` + `_leadQualBucket`.

**No backend changes. No queue schema changes. No protected systems touched.**
All caller shapes preserved.

**Commit:** `118b787`

---

### 2026-03-17 - Pass 41: V2 Stage 2D — Stable Key Propagation + Stronger Discovery-Queue Linking

**Goal:** Replace `_mrpResolveRow`'s fuzzy name+city scan with a stable key-indexed lookup. Website (90% coverage, 0 collisions) and phone (99%, 0 collisions) are now the primary match signals.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- `_leadKeyIndex = new Map()` module var added alongside `allRows`.
- `_buildLeadKeyIndex(rows)` function: builds Map from `_leadKey(row)` for all rows. Called in `loadAll()` after `allRows` assignment.
- `_mrpResolveRow(biz)` rewritten: Layer 1 = `_leadKeyIndex.get(_leadKey(biz))` exact lookup; Layer 2 = name+city scan fallback; Layer 3 = name-only last resort (compat preserved).

**No backend changes. No queue schema changes. No protected systems touched.**
All `_mrpResolveRow` call sites unchanged.

**Commit:** `4159c60`

---

### 2026-03-17 - Pass 40: V2 Stage 2C — Shared Row State Rendering

**Goal:** Reduce duplicated row-state logic between Discovery and Pipeline renders. Add observation visibility and next-action hints to both views consistently.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- Added `_leadStatusPills(record)` — shared pill renderer from `_leadRecord`. Replaces both inline `mrp-status-pills` blocks in `_mapRenderPanel`. Now also shows observation tag in Discovery list items.
- Added `_leadNextActionHint(record)` — shared next-action hint HTML. Added to both Discovery list renders.
- Both `_mapRenderPanel` pill blocks replaced with `_leadStatusPills` + `_leadNextActionHint` via `_leadRecord(qrow)`.
- `statusCellHtml` subline extended: `obs` tag appended when observation present; `nextAction` text appended when unsent.

**No backend changes. No queue schema changes. No protected systems touched.**

**Commit:** `8abbb57`

---

### 2026-03-17 - Pass 39: V2 Stage 2A+2B — Unified Lead Record + Workspace Panel

**Goal:** Introduce a canonical lead record shape and shared workspace panel header so Discovery and Pipeline read/write through the same data model for a business.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**Stage 2A — new functions:**
- `_leadKey(input)` — stable identity key from biz or queue row
- `_leadResolve(input)` — resolves to `{ biz, qrow, key }` from either input
- `_leadRecord(input)` — canonical normalizer covering identity, contact, qualification, status, draft, observation, history

**Stage 2B — new functions + wiring:**
- `_STATUS_TONE_STYLES` — shared status badge style map
- `_renderLeadWorkspaceHeader(record)` — shared HTML for status + channels + score + obs tag + next action
- Wired into `fillPanel` (Pipeline panel meta section)
- Wired into `_mrpPreview` (Discovery map modal header)
- `mrp-modal-lws-header` div added to modal HTML

**No backend changes. No queue schema changes. No protected systems touched.**
All existing send/approve/schedule/unschedule behavior preserved.

**Commit:** `40f7db2`

---

### 2026-03-17 - Pass 38: Pre-Pass-36 Queue State Cleanup (Bulk Unschedule)

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

**Commit:** `b12cf5e`

---

### 2026-03-17 - Pass 37: Discovery Review Recovery + Action Feedback

**Goal:** Fix operator friction introduced by recent dashboard passes — restore editable map preview, add pending-state feedback, fix backdrop close with drag guard, surface Unschedule clearly.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**

`index.html`:
- Added `_panelMousedownOnBackdrop` state variable for drag-close guard.
- Added `_panelOverlayMousedown(e)` — sets flag only when mousedown lands on the backdrop itself.
- Rewrote `closePanelOnOverlay` — now performs real close instead of toast-only block. Requires mousedown origin to have been the backdrop; pending saves still temporarily block.
- Wired `onmousedown="_panelOverlayMousedown(event)"` onto the overlay element.
- Added `_btnPending(btn, label)` and `_btnRestore(btn)` shared helpers.
- `panelApprove` — pending state (Approving...), try/catch, restore.
- `panelUnapprove` — pending state (Removing...), try/catch, restore.
- `panelScheduleTomorrow` — pending state (Scheduling...), restore on all exit paths.
- `panelUnschedule` — pending state (Clearing...), restore.
- `mrp-modal` HTML — replaced `<pre>` + static subject `<div>` with `<input>` + `<textarea>` + save-status line.
- `_mrpPreview` — fully rewritten: populates inputs, wires Save Edits (calls `/api/update_row`), Approve, Unschedule (for scheduled rows) / Schedule Tomorrow (for unscheduled), Delete, Close — all with pending state.

**No backend changes. No protected systems touched.**

**Verification:**
- `node --check` clean on extracted dashboard JS.
- `python -c "import dashboard_server"` clean.
- All change sites confirmed via targeted search (line numbers documented in CURRENT_BUILD.md).

**Commit:** `4224d78`

---

### 2026-03-17 - Pass 36: Observation-Led Outreach Rewrite

**Goal:** Rewrite first-touch email and DM generation so every draft is observation-led, business-specific, and invalid when generic. This is a product rule change — not copy polish.

**Files changed:**
- `lead_engine/outreach/email_draft_agent.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**

`email_draft_agent.py` (v8 → v9):
- Removed all previous industry-angle templates. Generation is now entirely observation-driven.
- Added `ObservationMissingError` and `DraftInvalidError` for structured failure signaling.
- Added `_require_observation()` — fails if observation is absent or under 15 chars.
- Added `_is_generic_observation()` — rejects category labels ("noticed you do roofing") that would fit most businesses in the category.
- Added `validate_draft()` — deterministic validation blocking banned buzzwords, hard CTAs, links, pricing, sender-centered filler openers, and observation-absent drafts.
- Added three controlled variation families (A/B/C). No open-ended variation allowed.
- `draft_email()` and `draft_social_messages()` both require observation. Both fail clearly with `ObservationMissingError` if absent.
- Added prefix normalization so observations starting with "saw"/"noticed" don't double-stack with the variant prefix.

`dashboard_server.py`:
- Added `business_specific_observation` as final column in `PENDING_COLUMNS`. Additive, non-send-path, safe for existing rows via DictReader `.get()`.
- Added `/api/update_observation` — persists observation, rejects absent/short/generic values.
- Added `/api/regenerate_draft` — requires observation (stored or inline override). Returns structured `blocked_reason` field. On success writes new subject/body/DM drafts to queue row.

`index.html`:
- Added observation CSS block.
- Added observation panel section (textarea, hint, required/status tag, regen button, status line).
- Added `_panelPopulateObs(row)` wired into `fillPanel()` — hydrates field, shows blocked state when observation absent.
- Added `panelObsChanged(value)` — live handler that enables/disables regen button and updates hint text.
- Added `panelRegenerateDraft()` — calls `/api/regenerate_draft`, updates panel fields on success, shows structured blocked/invalid reason on failure.

**Verification:**
- `python -m py_compile` clean on both Python files.
- `node --check` clean on extracted dashboard JS.
- 23/23 targeted checks passed: blocking, generic rejection, validation layer, observation-in-body requirement, variation distinctness, field-vs-arg routing.

**No protected systems touched:** `run_lead_engine.py`, sender core, scheduler core, follow-up system, and queue pipeline behavior are all unchanged.

**Commit:** `00add5d`

---

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
### 2026-03-17 - Pass 35: Scheduling Clarity + Queue Timeline UX

**Goal:** Make outreach queue timing and scheduled state easier to understand without changing scheduler logic.

**Changes:**
- Added a queue timeline explainer bar under the outreach filters so operators can tell how `Actionable`, `Approved`, `Scheduled`, and `All` relate to future send windows.
- Added a queue-state helper layer that distinguishes future scheduled rows from schedule-window-reached rows and clearer ready-now approved rows.
- Added exact plus relative local-time schedule formatting and expanded the review-panel schedule block with clearer waiting vs ready-now explanations.
- Updated scheduling feedback copy so schedule/unschedule actions clearly explain whether a row is waiting for later or back in a ready-now queue.

**Files touched:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**Verification:**
- Extracted the inline dashboard JavaScript and ran `node --check`.
- Ran a live headless-browser smoke pass against `http://127.0.0.1:5000` with a synthetic queue subset and stubbed API writes to verify queue timeline notes, status clarity, review-panel timing explanations, schedule/unschedule transitions, schedule button wording, and basic Pass 29 discovery control availability.
- Reconfirmed the pass stayed frontend-only and did not touch protected systems.

**Commit:** `4e18c3c`

---

### 2026-03-17 - Pass 34: Outreach Review Throughput + Queue Control

**Goal:** Increase operator throughput while reviewing large outreach subsets after discovery handoff.

**Changes:**
- Added review-session context directly inside the outreach panel with a clear subset label and live queue-state counts for the active review set.
- Added context-aware quick flow actions: `Approve + Next`, `Schedule + Next`, `Unschedule + Next`, `Undo + Next`, and `Skip`.
- Added keyboard shortcuts for faster sequential review (`A`, `Shift+A`, `S`, `Shift+S`, `U`, `N`, and arrow navigation) without changing scheduler or sender logic.
- Preserved Pass 33 discovery-to-review continuity by carrying a `Discovery review subset` label into the outreach panel when review opens from discovery-visible subsets.

**Files touched:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**Verification:**
- Extracted the inline dashboard JavaScript and ran `node --check`.
- Ran a live headless-browser smoke pass against `http://127.0.0.1:5000` with a synthetic review subset and stubbed API writes to verify subset labeling, queue visibility, rapid review actions, skip/next flow, overlay-close protection, and basic Pass 29 discovery control availability.
- Reconfirmed the pass stayed frontend-only and did not touch protected systems.

**Commit:** `67716ce`

---
