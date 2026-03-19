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
Pass 53 -- Industry Saturation View

- Added a bounded industry saturation layer inside the discovery map workflow
  using the existing coarse territory overlay data rather than inventing a new
  polygon or county model.
- The map now shows visible-territory industry coverage, best-next industry
  suggestions, and working-area industry mix built from stored lead, search,
  duplicate, and planner counts per territory cell.
- Saturation remains heuristic and truthful:
  labels are derived from stored area-search history, AREA planner rows, and
  stored lead coordinates only.
- Territory cells remain the primary guidance layer and the circle remains the
  actual working search geometry used by current discovery endpoints.

Commit: `PENDING_COMMIT`

## Previous Completed Pass
Pass 52a -- Observation Route Recovery + Discovery Connection Hardening + Circle Interaction Review

Commit: `fdbd2fb`

## Next Pass
TBD

## Protected Systems
- `run_lead_engine.py`
- Queue schema (column order and naming)
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler timing/core
- `safe_autopilot_eligible` logic

## Core Operator Workflow

1. Review the discovery map for coarse territory coverage, industry saturation,
   lead clustering, and underworked versus duplicate-heavy cells
2. Load a territory cell into the working circle or place the circle manually,
   compare industry saturation in that area, then fine-tune radius and run
   deliberate area discovery
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
