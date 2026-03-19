# Current Build Pass

## Active System
Pass 51 -- Observation Autowrite + Candidate Approval Layer

## Status
Pass 51 complete.

---

## Completed: Pass 51 -- Observation Autowrite + Candidate Approval Layer -- `PENDING_COMMIT`

Product changes across three code files:
- `lead_engine/outreach/observation_candidate_agent.py`
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

Docs updated in:
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/CHANGELOG_AI.md`
- `docs/AI_CONTROL_PANEL.md`

No queue schema reorder/rename changes. No `run_lead_engine.py` changes.
No email sender core changes. No scheduler timing changes.

### Problem addressed

Observation-led drafting was working, but it still depended too heavily on the
operator writing observation text manually before first-touch drafts could be
created or stale rows could be refreshed. That manual bottleneck limited
throughput even when Copperline already had enough grounded lead evidence on
file to suggest a safe observation candidate.

### What was added

**`lead_engine/outreach/observation_candidate_agent.py`** (new)

- Added deterministic observation candidate generation with explicit families:
  `prior_observation_restore`, `limited_contact_methods`,
  `single_contact_route`, and `phone_only_listing`.
- Added shared observation validation used by both save and regenerate flows.
- Added structured blocking for weak evidence, generic copy, banned
  growth/agency language, missing context overlap, and overlong observations.

**`lead_engine/dashboard_server.py`**

- Added `POST /api/generate_observation_candidate` to build a candidate from
  safe stored lead context only.
- `POST /api/update_observation` now uses shared validation and returns
  structured blocked reasons on invalid save attempts.
- `POST /api/regenerate_draft` now also re-validates the observation before
  rebuilding copy, preserving observation-led quality gates.
- Added prospect matching helpers so candidate generation can safely reuse
  existing business context already stored in `prospects.csv`.

**`lead_engine/dashboard_static/index.html`**

- Added panel observation actions:
  `Generate Obs`, `Save Observation`, `Use Candidate`, and
  `Regenerate Candidate`.
- Added a candidate review box that shows:
  candidate text, family, confidence, rationale, evidence, source labels, or
  a clear blocked reason when no safe candidate exists.
- Candidate generation runs inside the existing observation panel flow instead
  of creating a parallel review system.
- Unsaved observation edits, blocked save/regenerate states, and candidate-ready
  states now surface directly in-panel.

### What remains intentionally out of scope

- Scheduler timing model and due-date math
- Send Approved behavior or Gmail/manual send flow
- Queue schema redesign
- Hidden or automatic bulk mutation of all leads
- Auto-accepting observation candidates without operator review
- Protected send-path rewrites

### Verification

- Dashboard JS extracted and `new vm.Script(...)` parses clean.
- Python imports clean for `lead_engine.dashboard_server` and
  `lead_engine.outreach.observation_candidate_agent`.
- Flask test client verification on the real local repo:
  - ready candidate on `Massie Heating and Air Conditioning` -> `200`,
    family `limited_contact_methods`
  - blocked candidate on `Integrity Auto Care` -> `200`,
    `blocked_reason=weak_source_context`
  - invalid save attempt using banned growth language -> `400`,
    `blocked_reason=observation_banned_language`
  - invalid regenerate attempt using the same banned observation -> `400`,
    `blocked_reason=observation_banned_language`
- Current local queue evaluation through the new candidate layer:
  `49` ready candidates, `131` blocked
  (`110` `weak_source_context`, `21` `insufficient_context`).

---

## Previous Completed: Pass 50a / 51a -- Stale Draft Refresh Workflow -- `5b43aaa`

- Added direct stale row refresh actions and faster queue-to-observation repair flow.
