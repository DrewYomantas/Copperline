# Copperline Project State

Last Updated: 2026-03-17

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Discovery Coverage Expansion + Bulk Unschedule

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work - missed calls, cold estimates, follow-ups that never happen - and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 29 - Discovery Coverage Expansion + Bulk Unschedule

- Restored the dashboard after a failed transfer left `lead_engine/dashboard_static/index.html` as a broken 63-byte stub.
- Added circle-based grid sweep controls using the existing map circle as the boundary.
- Added multi-industry grid selection, capped grid/call planning, sequential execution, current-run dedupe, compact progress text, cancel support, and one summarized history entry per grid run.
- Added bulk unschedule for scheduled outreach rows and allowed scheduled rows to be selected in the Scheduled filter.
- Smoke-verified the dashboard load, grid run/cancel/history behavior, scheduled-row selection, bulk unschedule UI state, and existing single/visible/exhaust discovery actions.
- Fixed a small stabilization bug so bulk `Unschedule` becomes visibly available when scheduled rows are selected.
- Kept the pass frontend-only. No scheduler core, queue schema, or protected pipeline logic changed.

Commit: `aaa3276`

## Previous Completed Pass
Pass 18b - Human Draft Enforcement Layer

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
