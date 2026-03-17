# Copperline Project State

Last Updated: 2026-03-17

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Discovery Review Recovery + Action Feedback

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work - missed calls, cold estimates, follow-ups that never happen - and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 37 - Discovery Review Recovery + Action Feedback

- Restored editable map preview modal: subject input + body textarea + Save Edits button so operator can edit and save directly from the Discovery map panel without returning to Pipeline.
- Added Unschedule button to the map preview modal for scheduled rows.
- Added pending-state feedback to all slow panel actions: panelApprove, panelUnapprove, panelScheduleTomorrow, panelUnschedule — buttons disable and show in-progress label during the API call.
- Fixed backdrop close: clicking outside the review panel now closes it (was blocked by a toast). True backdrop mousedown+click required; drag-select inside panel never closes it.
- Added mousedown origin guard (`_panelMousedownOnBackdrop`) so text selection or input interaction inside the panel cannot accidentally dismiss it.
- Pending-state helpers `_btnPending` / `_btnRestore` added as shared utilities.

Commit: `4224d78`


## Queue State Management Note — Pass 38
**Date:** 2026-03-17
**Operation:** Bulk unschedule of 56 pre-Pass-36 (v7 draft) scheduled rows.

All 56 rows were scheduled for 2026-03-18 morning windows but carry old-style
pre-observation drafts that should not auto-send. `send_after` was cleared on
each. No rows deleted. No other fields altered. 50 sent rows untouched.
Total row count unchanged at 180.

Backup: `_backups/pending_emails_pre_p38_20260317_182909.csv`

**Queue state after:**
- total rows: 180
- sent rows: 50
- scheduled+unsent: 0
- unscheduled+unsent: 130

## Previous Completed Pass
Pass 36 - Observation-Led Outreach Rewrite

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
2. Add a business_specific_observation for each strong lead
3. System generates observation-led outreach drafts
4. Operator reviews, approves, or schedules for tomorrow morning
5. Scheduled queue sorted by send time - open it in the morning, send in order
6. Emails sent manually via Gmail
7. Follow-ups tracked automatically
8. Clients onboarded to missed-call texting service
