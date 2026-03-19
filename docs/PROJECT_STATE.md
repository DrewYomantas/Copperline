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
Pass 52 -- Territory Heatmap Overlay

- Added a bounded territory overlay on the discovery map using real persisted
  search and lead data instead of session-only coverage circles alone.
- Overlay data is built from stored area-search history, AREA planner rows, and
  stored prospect coordinates, then rendered as coarse neighborhood guidance
  cells on the Leaflet map.
- The map now helps the operator see:
  where searches have already clustered, where leads are concentrated, and
  which cells look underworked versus duplicate-heavy.
- Territory cells stay truthful and coarse:
  they are guidance for local exploration, not exact neighborhood boundaries.
- Operator flow remains deliberate:
  the overlay can set the search circle to a chosen cell, but it does not auto-run
  discovery or change the underlying discovery pipeline.

Commit: `PENDING_COMMIT`

## Previous Completed Pass
Pass 51 -- Observation Autowrite + Candidate Approval Layer

Commit: `aea9452`

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
2. Set the search circle manually or from a territory cell, then run deliberate
   area discovery
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
