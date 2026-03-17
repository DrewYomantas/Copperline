# Copperline Project State

Last Updated: 2026-03-17

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Discovery Panel Organization + Edit Stability

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work - missed calls, cold estimates, follow-ups that never happen - and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 30 - Discovery Panel Organization + Edit Stability

- Reorganized the discovery results panel into practical grouped sections so larger map result sets are easier to scan.
- Added grouping controls for workflow, city, email status, and flat mode, with score-first ordering as the default.
- Added clearer active-result highlighting and an explicit `Edit` action from discovery results into the review panel.
- Stabilized the review panel by anchoring it to a snapshot of the visible lead set instead of the live filtered table only.
- Prevented accidental dismissal from overlay clicks and blocked close while debounced panel saves are still pending.
- Smoke-verified dashboard load, grouped result rendering, marker/result interaction, stable edit state across queue filter changes, and basic Pass 29 discovery controls.
- Kept the pass frontend-only. No scheduler core, queue schema, sender, follow-up, or other protected systems changed.

Commit: pending

## Previous Completed Pass
Pass 29 - Discovery Coverage Expansion + Bulk Unschedule

## Next Pass
TBD

## Protected Systems
- `run_lead_engine.py`
- Queue schema (column order and naming)
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler
- `safe_autopilot_eligible` logic

## Core Operator Workflow

1. Discover businesses via map
2. System generates outreach drafts
3. Operator reviews, approves, or schedules for tomorrow morning
4. Scheduled queue sorted by send time - open it in the morning, send in order
5. Emails sent manually via Gmail
6. Follow-ups tracked automatically
7. Clients onboarded to missed-call texting service
