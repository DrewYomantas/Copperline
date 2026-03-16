# Copperline Project State

Last Updated: 2026-03-16

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Outreach Queue — Sent Reconciliation Safety

## Last Completed Pass
Pass 11 — Sent Mail Reconciliation Recovery

- Added `/api/reconcile_sent` operator action in dashboard backend
- Added Gmail Sent mailbox scan + queue reconciliation helper (`reconcile_sent_mail`)
- Matching logic is strict: recipient email + subject on approved rows where `sent_at` and `message_id` are blank
- Ambiguous matches are skipped safely (no write)
- Reconciliation sets `sent_at` and fills `message_id` from Gmail when available
- New toolbar action `↺ Check Sent` triggers reconciliation from the dashboard
- No lead deletion, no resends, no queue schema changes

Commit: `aae0cb5`

## Previous Completed Pass
Pass 9b — Scheduled Send Intent

Commits: A `24dc5b2` / B `52dd64a` / C `a5f09c5`

## Next Pass
Pass 12 — TBD (territory heatmap, saturation view, or tiled backend improvements)

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
