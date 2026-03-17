# Copperline Project State

Last Updated: 2026-03-16

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Outreach Positioning Correction

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work — missed calls, cold estimates, follow-ups that never happen — and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 16a — Bug Stabilization

- Added missing `normalize_business_name()` to `prospect_discovery_agent.py` — fixes `/api/queue_health` and `/api/exceptions` 500s
- Changed all-duplicates discovery path from HTTP 400 → 200 with `all_duplicates: true` flag — fixes misleading connection error in map UI
- Added `None` guards on `approved` field in `queue_integrity.py` and `exception_router.py`
- No logic changes, no schema changes, no protected systems touched

Commit: `7e34d57`

## Previous Completed Pass
Pass 15b — Outreach Tone Correction: Operational Problem-First Messaging

## Next Pass
Pass 16b — TBD (territory heatmap, saturation view, tiled backend improvements, or outreach doc updates)

## Protected Systems
- `run_lead_engine.py`
- Queue schema (column order and naming)
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler
- `safe_autopilot_eligible` logic

## Core Operator Workflow

1. Discover businesses via map
2. System generates outreach drafts
3. Operator reviews, approves, or schedules for tomorrow morning
4. Scheduled queue sorted by send time — open it in the morning, send in order
5. Emails sent manually via Gmail
6. Follow-ups tracked automatically
7. Clients onboarded to missed-call texting service
