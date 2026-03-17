# Copperline Project State

Last Updated: 2026-03-17

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Observation-Led Outreach Rewrite

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work - missed calls, cold estimates, follow-ups that never happen - and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 36 - Observation-Led Outreach Rewrite

- Rewrote `email_draft_agent.py` (DRAFT_VERSION v9) so first-touch email and DM generation requires a `business_specific_observation` field.
- First-touch generation fails with a clear `ObservationMissingError` if observation is absent or too generic.
- Validation layer (`validate_draft`) deterministically blocks banned buzzwords, hard CTAs, links, pricing, and drafts that don't materially reflect the observation.
- Three controlled variation families (A/B/C) are the only allowed output patterns — no open-ended variation that can drift back into sales copy.
- Added `business_specific_observation` as an additive non-send-path column to `PENDING_COLUMNS` in `dashboard_server.py`.
- Added `/api/update_observation` and `/api/regenerate_draft` endpoints — both block clearly when observation is missing or invalid.
- Added observation input field + regenerate button to the review panel in `index.html`, with blocked state messaging when observation is absent.
- Verified 23/23 checks pass: blocking, validation, output quality, variation, field-vs-arg observation routing.

Commit: TBD

## Previous Completed Pass
Pass 35 - Scheduling Clarity + Queue Timeline UX

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
