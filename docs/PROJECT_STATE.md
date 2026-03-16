# Copperline Project State

Last Updated: 2026-03-16

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Outreach Queue — Scheduled Send UX

## Last Completed Pass
Pass 10 — Scheduled Queue UX

- Scheduled rows now display readable send times (Today · 7:30am / Tomorrow · 7:30am / Fri Mar 20 · 8:00am) under the badge in the table
- Active filter now excludes scheduled rows — Active = "actionable now" only
- Scheduled filter now sorts by send_after ascending (earliest first)
- Panel schedule info block shows formatted time + Clear / +1 / +2 / +3 day action buttons
- `panelClearSchedule()` clears send_after via guarded /api/schedule_email route
- `panelReschedule(days)` reschedules to today+N at industry window time
- `/api/schedule_email` backend updated to accept empty string (clear) while keeping all identity/bounds validation
- No send logic changed. No auto-send. No schema changes.

Commit: `d31d720`

## Previous Completed Pass
Pass 9b — Scheduled Send Intent

Commits: A `24dc5b2` / B `52dd64a` / C `a5f09c5`

## Next Pass
Pass 11 — TBD (territory heatmap, saturation view, or tiled backend improvements)

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
