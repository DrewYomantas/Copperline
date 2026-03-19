# Copperline AI Control Panel

Last Updated: 2026-03-19
Repository Version: v0.2

---

## Project Phase
Lead Acquisition Engine

## Current Focus
V2 Stage 2 - Unified Lead Workspace Backbone

## Current Build Pass
Pass 52 -- Territory Heatmap Overlay (complete)

## Last Completed Pass
Pass 52 -- Territory Heatmap Overlay

Commit: `6285e65`

## Next Pass
Industry saturation view

## Upcoming Passes
- Industry saturation view

---

## Execution Model

Bounded cohesive passes. Each pass delivers one operator outcome end-to-end.
Unrelated systems must not be bundled. No protected-system drift without explicit approval.

---

## Core Product

Copperline: discover local service businesses, draft outreach, send manually,
track replies, convert to clients, deploy missed-call texting.

---

## Key Systems

| System | Location |
|---|---|
| Lead discovery engine | `lead_engine/discovery/` |
| First-touch drafting | `lead_engine/outreach/email_draft_agent.py` |
| Observation candidate generation | `lead_engine/outreach/observation_candidate_agent.py` |
| Follow-up drafting | `lead_engine/outreach/followup_draft_agent.py` |
| Follow-up scheduler | `lead_engine/outreach/followup_scheduler.py` |
| Email queue | `lead_engine/queue/pending_emails.csv` |
| Map discovery interface | `lead_engine/dashboard_static/index.html` |
| Dashboard API | `lead_engine/dashboard_server.py` |
| Durable lead memory + timeline | `lead_engine/lead_memory.py` + `lead_engine/data/lead_memory.json` |

## Protected Systems

- `run_lead_engine.py`
- Queue schema (column order and naming)
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler timing/core send logic
- `safe_autopilot_eligible` logic

## Governance Distinction

- Protected delivery-core systems remain constrained. Do not loosen sender,
  queue, scheduling, or orchestration protections casually.
- Operator-visible intelligence layers may evolve additively when changes are
  truthful, documented, reversible, and do not introduce hidden send-path or
  bulk-mutation behavior.

## Active Constraints

- Discovery must be intentional - no auto-search on pan or zoom
- No build steps - frontend is a single HTML file with CDN dependencies only
- Territory overlay uses coarse stored search centers and stored lead coordinates only - no fake neighborhood precision
- Email sending is manual/operator-reviewed - auto-send must not drift into generic nurture behavior
- Observation-led drafting remains required
- Generated observations are allowed only when grounded in real available lead context
- Generated observations remain operator-reviewed by default during hardening
- No hidden bulk observation mutation or auto-accept behavior is in scope
- Territory cells may guide the operator to the next search area, but do not auto-run discovery
- Follow-up drafting blocks when lead-specific continuation context is weak
- Stale first-touch rows still keep the direct refresh path from queue row -> observation field -> regenerate -> next stale row
- Suppressed/contacted leads filtered from all discovery entry points by default

---

## Lifecycle Event Registry (as of Pass 52)

| Constant | Event | Hook point | Status |
|---|---|---|---|
| EVT_DRAFTED | Draft created | run_pipeline (protected) | Deferred |
| EVT_OBSERVATION_ADDED | Observation saved | api_update_observation | Live |
| EVT_DRAFT_REGENERATED | Draft regenerated | api_regenerate_draft | Live |
| EVT_REPLIED | Replied | api_log_contact result=replied | Live |
| EVT_NOTE_ADDED | Note added | api_update_conversation | Live |
| EVT_FOLLOWUP_SENT | Follow-up sent | api_send_followup | Live |
| EVT_APPROVED | Approved | api_approve_row | Live |
| EVT_UNAPPROVED | Approval removed | api_unapprove_row | Live |
| EVT_SCHEDULED | Scheduled | api_schedule_email (set) | Live |
| EVT_UNSCHEDULED | Unscheduled | api_schedule_email (clear) | Live |

## Repo Quick Reference

| Question | File |
|---|---|
| What is being built now? | `docs/CURRENT_BUILD.md` |
| What is the project state? | `docs/PROJECT_STATE.md` |
| What must not be touched? | `docs/PROTECTED_SYSTEMS.md` |
| Dev history | `docs/CHANGELOG_AI.md` |
