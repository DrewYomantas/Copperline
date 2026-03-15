# Copperline Project State

Last Updated: 2026-03-15

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Discovery Map System

## Last Completed Pass
Runtime Verification Hotfixes

- `api()`: throws descriptive `Error` on non-OK HTTP — fixes `SyntaxError: Unexpected end of input` from 404 pages
- Map click guard: `_mapDrawCircle` only fires when `_mapResultItems` is empty — prevents accidental result wipe
- `.btn-coverage` contrast raised — button now readable in toolbar
- Parse check: `vm.Script` PARSE OK on served JS post-fix

Commit: `2b202cd`

## Previous Completed Pass
Stabilization Pass — Defensive Fixes (Steps 3–7) — `03faaf8`

- Added `_mapAreaLabel(markers)`: frequency-counts `biz.city` from result set, returns most common city name, null if no city data
- History entry now stores `label` field alongside existing fields
- `_mapRenderHistory()` uses `entry.label` as primary text, falls back to `lat/lng` coords; secondary shows radius + found count; exact coords preserved as `title` tooltip
- No new API calls, no reverse geocoding

Commit: `3f86767`

## Previous Pass
Step 6 — Discovery History List

Commit: `6d79c64`

## Next Pass
Step 8 — Search Visible Area (scope questions in CURRENT_BUILD.md)

## Upcoming Passes
- Search Visible Area button
- Tiled discovery backend (neighborhood-level grid search)
- Territory heatmap overlay
- Industry saturation view

## Protected Systems
- `run_lead_engine.py`
- Queue schema
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler
- Exception router
- `safe_autopilot_eligible` logic

## Core Operator Workflow

1. Discover businesses via map
2. System generates outreach drafts
3. Operator reviews and approves
4. Emails sent manually via Gmail
5. Follow-ups tracked automatically
6. Clients onboarded to missed-call texting service
