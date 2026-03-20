# Current Build Pass

## Active System
Pass 55 -- First-Touch Service Positioning Hardening

## Status
Pass 55 complete. Repo is ready for the next product pass.

---

## Completed: Pass 55 -- First-Touch Service Positioning Hardening

Product changes in:
- `lead_engine/outreach/email_draft_agent.py`

Docs updated in:
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/CHANGELOG_AI.md`
- `docs/AI_CONTROL_PANEL.md`

No queue schema reorder/rename changes. No `run_lead_engine.py` changes.
No email sender core changes. No scheduler timing/core changes.
No send-path changes. No follow-up system changes.

### Problem addressed

Observation-led first-touch drafts were still at risk of sounding vague,
category-generic, or loosely "random observation" driven instead of sounding
like a believable one-person operator helping service businesses fix real lead
handling bottlenecks.

### What was added

**`lead_engine/outreach/email_draft_agent.py`**

- Bumped `DRAFT_VERSION` from `v9` to `v10` so stale detection can treat the
  new first-touch positioning as a real copy revision.
- Replaced the old controlled families with deterministic angle-based first-touch
  framing:
  after-hours response, estimate follow-up, service requests, inquiry routing,
  callback recovery, and a general owner-workflow fallback.
- Each first-touch draft now follows the same bounded structure:
  observation -> concrete operational consequence -> what Drew actually helps
  with -> soft ask.
- Added deterministic language controls to block vague positioning like
  `workflow gap`, `another set of eyes`, or `business side` drift.
- Added validation that a first-touch draft must mention a concrete
  service-business bottleneck or fix, not just a generic observation.

### What remains intentionally out of scope

- Observation generation or evidence refresh logic
- Queue/send/scheduler changes
- `run_lead_engine.py` changes
- Follow-up drafting
- Discovery/map work
- Hidden bulk regeneration or auto-send behavior

### Verification

- Python compile check:
  - `lead_engine/outreach/email_draft_agent.py`
- Direct draft-agent verification:
  - missing observation still blocks
  - generic observation still blocks
  - vague positioning and banned sales language now block deterministically
  - multiple example first-touch drafts now mention believable service-business
    fixes tied to the observation instead of generic consulting language

---

## Previous Completed: Pass 54 -- On-Demand Observation Evidence Refresh

- Added a bounded single-lead evidence refresh path that can re-check business
  evidence and retry observation candidate generation without auto-saving the
  observation.
