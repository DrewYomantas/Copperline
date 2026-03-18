# Copperline Project State

Last Updated: 2026-03-18

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
Pass 46 -- Contacted Memory Seeding + Safer Contact Recording

- New script `lead_engine/scripts/seed_contacted_memory.py`: idempotent one-shot
  seed of 34 real-sent rows into lead_memory.json as 'contacted'. Uses is_real_send()
  as the gate (confirmed SMTP sends only, not logged-only rows). Dry-run by default.
  Executed: 34/34 seeded, all with web: identity keys.
- `api_log_contact` hook: when result=='sent', calls _lm.record_suppression(row,
  'contacted'). Forward-looking -- all future manual contact logs auto-seed memory.
- Panel footer: 'Mark Contacted' button (hidden when row already has sent_at,
  visible for unsent rows). Calls /api/suppress_lead with state='contacted'.
- fillPanel visibility block updated to toggle the new button alongside approve/schedule.
- No protected systems touched. No queue schema changes. 6/6 checks passed.

Commit: `65d113e`

## Previous Completed Pass
Pass 45 -- Durable Memory Coverage Hardening

Commit: `e7c382c`

## Queue State Management Note -- Pass 38
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
