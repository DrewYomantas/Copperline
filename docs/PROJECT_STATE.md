# Copperline Project State

Last Updated: 2026-03-16

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Pass 11C — Discovery-to-Queue Continuity UX

## Last Completed Pass
Pass 11C — Discovery-to-Queue Continuity UX

- Added a session handoff bar that appears after discovery runs with truthful summary text and direct next actions.
- Added one-click continuity actions: Review New Drafts, Continue Discovering, and Return to Last Discovery Area.
- Captured map context (center/radius/industry/city-state label) and restored it when returning from queue review.
- Preserved explicit discovery triggers and existing queue/send behavior (no auto-search, no send logic changes).

Commit: `70f1f96`

## Previous Completed Pass
Pass 9b — Scheduled Send Intent

Commits: A `24dc5b2` / B `52dd64a` / C `a5f09c5`

## Next Pass
Pass 17 — TBD (territory heatmap, saturation view, or tiled backend improvements)

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
