# Current Build Pass

## Active System
Pass 50a / 51a -- Stale Draft Refresh Workflow

## Status
Pass 50a / 51a complete.

---

## Completed: Pass 50a / 51a -- Stale Draft Refresh Workflow -- `pending`

Product changes across one code file:
- `lead_engine/dashboard_static/index.html`

Docs updated in:
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/CHANGELOG_AI.md`
- `docs/AI_CONTROL_PANEL.md`

No queue schema reorder/rename changes. No `run_lead_engine.py` changes.
No email sender core changes. No scheduler timing changes.

### Problem addressed

Stale outreach rows were correctly blocked from sending, but the operator path
to fix them still required too much back-and-forth inside the review panel.
Rows that needed an observation and regenerate step did not have a direct queue
action, did not auto-land on the observation field, and did not provide a fast
way to move to the next stale row once one draft was repaired.

### What was added

**`lead_engine/dashboard_static/index.html`**

- Queue rows that need refresh now show a dedicated stale action:
  `Add Obs` when no observation is on file, `Refresh` when one exists.
- That action opens the existing review panel with refresh intent and focuses the
  observation textarea so the operator can fix the row immediately.
- The existing "Refresh before send" panel block now includes direct stale-repair
  actions:
  - `Add/Edit observation`
  - `Regenerate now`
  - `Next stale` when another stale row exists in the current review set
- The review flow bar now shows stale-specific actions and adds
  `Regen + Next Stale` when the current row already has an observation.
- Review session chrome now surfaces stale-row counts so operators can see how
  much stale cleanup remains in the current set.
- Failed regenerate attempts keep the operator on the observation field and show
  the blocked reason in-panel; successful regenerates can advance directly to the
  next stale row without closing the panel.

### What remains intentionally out of scope

- Scheduler timing model and due-date math
- Send Approved behavior or Gmail/manual send flow
- Queue schema redesign
- Auto-generation of observations
- Hidden or automatic bulk draft rewrites
- Protected send-path rewrites

### Verification

- Dashboard JS extracted and `new vm.Script(...)` parses clean.
- Live local app endpoints:
  - `GET /api/status` -> `200`, current draft version `v9`
  - `GET /api/queue` -> `200`, current local queue `180` rows with `130` stale
    rows under the existing stale rules
  - served dashboard HTML contains the new stale-refresh hooks:
    `openPanelForRefresh`, `panelJumpNextStale`,
    `panelRegenerateAndNextStale`
- Real blocked regenerate check on stale row `Integrity Auto Care`:
  `POST /api/regenerate_draft` -> `400` with
  `blocked_reason=observation_missing`, confirming observation-led regeneration
  remains enforced.

---

## Previous Completed: Pass 50 -- Follow-Up System Rebuild -- `4ab7bd5`

- Added deterministic, context-aware follow-up drafting with explicit angle families and stronger blocking.
