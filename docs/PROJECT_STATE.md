# Copperline Project State

Last Updated: 2026-03-17

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Outreach Review Throughput + Queue Control

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work - missed calls, cold estimates, follow-ups that never happen - and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 34 - Outreach Review Throughput + Queue Control

- Added a review-session status bar in the outreach panel showing the active review set label plus compact queue-state counts for the current subset.
- Added throughput-oriented flow actions inside the review panel: `Approve + Next`, `Schedule + Next`, `Unschedule + Next`, `Undo + Next`, and `Skip`, all built on the existing review actions without changing scheduler or sender logic.
- Added keyboard shortcuts for faster sequential review: arrows to move, `A` approve, `Shift+A` approve and continue, `S` schedule, `Shift+S` schedule and continue, `U` unschedule, and `N` skip to the next row.
- Preserved discovery-to-review continuity by carrying a `Discovery review subset` session label through the Pass 33 bridge, so review context stays clear after opening a visible discovery subset.
- Verified dashboard load, session labeling, queue-position visibility, rapid review actions, overlay-close protection, and basic Pass 29-33 control availability with a focused live headless smoke pass using a synthetic review subset and stubbed API writes.
- Reconfirmed no protected systems were touched; the pass stayed in `lead_engine/dashboard_static/index.html`.

Commit: `COMMIT_PENDING`

## Previous Completed Pass
Pass 33 - Bulk Discovery-to-Outreach Workflow Acceleration

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
