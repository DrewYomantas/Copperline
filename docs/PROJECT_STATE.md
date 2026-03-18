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
Pass 44 — Durable Lead Memory + Suppression Registry

- New standalone module `lead_engine/lead_memory.py` persists suppression/contact
  memory to `lead_engine/data/lead_memory.json`, independent of the queue CSV.
- Deleting a queue row now records `deleted_intentionally` in memory before the pop.
- Opting out a lead records `do_not_contact` in durable memory.
- Four new API routes: `/api/suppress_lead`, `/api/revive_lead`, `/api/lead_memory`,
  `/api/lead_memory/check`.
- `api_discover_area` filters suppressed leads from marker results by default
  (`?include_suppressed=1` to override).
- Panel footer gains Hold button (suppresses from discovery without deleting).
- Tools nav gains Lead Memory sub-tab: searchable table with suppressed-only
  filter and per-row Revive action.
- No protected systems touched. No queue schema changes.
- 6/6 functional verification checks passed.

Commit: `e4cfc38`

## Previous Completed Pass
Pass 43 - V2 Stage 2F -- Next-Action-Driven Controls + History Visibility

Commit: `5a09991`

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
