# Copperline Project State

Last Updated: 2026-03-17

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
V2 Stage 2 — Unified Lead Workspace Backbone

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work - missed calls, cold estimates, follow-ups that never happen - and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel

- Added `_leadKey(input)` — single stable identity key from either a biz object or queue row (place_id → website → phone → name+city priority).
- Added `_leadRecord(input)` — canonical normalizer returning one flat record covering identity, contact, qualification, workflow status, draft, observation, and history from either input type.
- Added `_leadResolve(input)` — resolves either input to a `{ biz, qrow, key }` pair. Synthesizes the missing half when only one side is provided.
- Added `_renderLeadWorkspaceHeader(record)` — shared HTML renderer for status badge, channel badges, score, observation hint, and next recommended action. Used in both Pipeline panel and Discovery preview modal.
- Wired `_renderLeadWorkspaceHeader` into `fillPanel` (Pipeline panel meta section).
- Wired `_renderLeadWorkspaceHeader` into `_mrpPreview` (Discovery map preview modal header).
- Added `mrp-modal-lws-header` div to modal HTML.
- Zero backend changes. No queue schema changes. No protected systems touched.

Commit: TBD


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
Pass 37 - Discovery Review Recovery + Action Feedback

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
