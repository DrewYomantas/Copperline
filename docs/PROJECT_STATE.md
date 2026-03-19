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
Pass 51 -- Observation Autowrite + Candidate Approval Layer

- Added a bounded observation-candidate layer that builds short grounded
  observation suggestions from real lead evidence already on file instead of
  forcing the operator to author every observation from scratch.
- New candidate generation stays inside the existing observation-led workflow:
  operators can generate, review, load into the observation field, edit, save,
  and then regenerate the draft from the approved observation.
- Candidate generation only uses safe existing context:
  saved lead memory observations, matched prospect contactability, visible
  contact routes on file, and limited queue insight signals when they support a
  concrete operational/contact-path observation.
- Weak evidence now blocks cleanly with structured reasons instead of inventing
  category-level or salesy observation text.
- Observation validation is now shared across save and regenerate paths, so
  banned generic growth/agency language stays blocked even if manually entered.

Commit: `PENDING_COMMIT`

## Previous Completed Pass
Pass 50a / 51a -- Stale Draft Refresh Workflow

Commit: `5b43aaa`

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
2. System can generate a grounded observation candidate when real lead evidence
   is strong enough
3. Operator reviews or edits the observation, then saves it to the lead row
4. System generates observation-led first-touch drafts from the approved/saved
   observation
5. Operator reviews, approves, or schedules for tomorrow morning
6. Emails are sent manually via Gmail
7. Follow-up drafting only proceeds when the lead record has grounded
   continuation context
8. Weak or generic follow-ups block instead of auto-queuing generic nurture copy
9. Clients onboard to missed-call texting service
