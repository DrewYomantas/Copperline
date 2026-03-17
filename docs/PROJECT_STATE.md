# Copperline Project State

Last Updated: 2026-03-17

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Bulk Discovery-to-Outreach Workflow Acceleration

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work - missed calls, cold estimates, follow-ups that never happen - and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 33 - Bulk Discovery-to-Outreach Workflow Acceleration

- Added a discovery-panel handoff layer that works on the current visible qualified subset instead of forcing row-by-row `Edit` clicks after triage.
- Added visible-set review/prep controls in the discovery bulk bar so operators can open the current filtered subset in the outreach review panel or bulk-prepare outreach-ready visible rows first.
- Added compact visible-subset summary counts showing how many current results are reviewable, outreach-ready, and still need approval.
- Tightened the discovery bulk helpers to use the actual visible queue-row context rather than weaker name-only lookups, keeping actions aligned with Pass 30/32 filtered subsets.
- Verified the dashboard still loads, triage views still narrow correctly, the new handoff actions open the expected visible subset in review, and prep-first review works without disturbing Pass 29-32 behaviors.
- Reconfirmed no protected systems were touched; the pass stayed in `lead_engine/dashboard_static/index.html`.

Commit: `c1a56a4`

## Previous Completed Pass
Pass 32 - Discovery Triage + Lead Qualification Controls

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
