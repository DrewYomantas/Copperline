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
Pass 52a -- Observation Route Recovery + Discovery Connection Hardening + Circle Interaction Review

- Fixed observation-candidate recovery when the live dashboard instance is stale
  or missing the route: the panel now shows a clean operator-facing error or
  blocked state instead of rendering raw Flask HTML.
- Hardened discovery request handling so `/api/discover_area` and
  `/api/discover_area_batch` failures surface their real API error text instead
  of collapsing into vague "Connection error" messaging.
- Kept the circle because current discovery endpoints are still radius-based,
  but demoted it in the map UX so territory cells and "Use Cell" feel like the
  primary way to choose the next search area.
- Territory guidance remains truthful and coarse:
  cells guide where to search next, while the circle remains the working search
  geometry used by the existing discovery flow.

Commit: `PENDING_COMMIT`

## Previous Completed Pass
Pass 52 -- Territory Heatmap Overlay

Commit: `6285e65`

## Next Pass
Industry saturation view

## Protected Systems
- `run_lead_engine.py`
- Queue schema (column order and naming)
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler timing/core
- `safe_autopilot_eligible` logic

## Core Operator Workflow

1. Review the discovery map for coarse territory coverage, lead clustering, and
   underworked versus duplicate-heavy cells
2. Load a territory cell into the working circle or place the circle manually,
   then fine-tune radius and run deliberate area discovery
3. System can generate a grounded observation candidate when real lead evidence
   is strong enough
4. Operator reviews, uses, or edits the observation candidate, then saves the
   final observation to the lead row
5. Observation-led first-touch drafting still blocks when there is no valid
   saved observation
6. System generates observation-led first-touch drafts from the approved/saved
   observation
7. Operator reviews, approves, or schedules for tomorrow morning
8. Emails are sent manually via Gmail
9. Follow-up drafting only proceeds when the lead record has grounded
   continuation context
10. Weak or generic follow-ups block instead of auto-queuing generic nurture copy
11. Clients onboard to missed-call texting service
