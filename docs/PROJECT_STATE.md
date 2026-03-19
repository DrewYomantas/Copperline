# Copperline Project State

Last Updated: 2026-03-19

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
V2 Stage 2 - Unified Lead Workspace Backbone

## Copperline Positioning
Copperline = Service Business Operations

## Last Completed Pass
Pass 50a / 51a -- Stale Draft Refresh Workflow

- Kept stale-draft detection and observation-led regeneration rules intact;
  no scheduler timing, send-path, or queue schema changes.
- `lead_engine/dashboard_static/index.html` now adds a direct queue-row stale
  action (`Add Obs` / `Refresh`) that opens the existing review panel straight
  into the observation field instead of forcing extra panel hops.
- The review panel stale state now exposes refresh-specific actions inside the
  existing "Refresh before send" block:
  `Add/Edit observation`, `Regenerate now`, and `Next stale` when another stale
  row exists in the current review set.
- Review-session chrome now surfaces stale-row counts, and stale rows gain a
  dedicated `Regen + Next Stale` flow action to help operators move through
  refresh work without weakening approval/send safeguards.
- Regeneration failures remain blocked by observation-led rules and now keep the
  operator anchored on the observation field with visible UI error text instead
  of feeling like a backend-only failure.

Commit: `pending`

## Previous Completed Pass
Pass 50 -- Follow-Up System Rebuild

Commit: `4ab7bd5`

## Next Pass
Territory heatmap overlay

## Protected Systems
- `run_lead_engine.py`
- Queue schema (column order and naming)
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler timing/core
- `safe_autopilot_eligible` logic

## Core Operator Workflow

1. Discover businesses via map
2. Add a business-specific observation for each strong lead
3. System generates observation-led first-touch drafts
4. Operator reviews, approves, or schedules for tomorrow morning
5. Emails are sent manually via Gmail
6. Follow-up drafting only proceeds when the lead record has grounded continuation context
7. Weak or generic follow-ups block instead of auto-queuing generic nurture copy
8. Clients onboard to missed-call texting service
