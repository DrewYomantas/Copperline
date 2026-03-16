# Copperline AI Control Panel

Last Updated: 2026-03-16
Repository Version: v0.2

---

## Project Phase
Lead Acquisition Engine

## Current Focus
Outreach Command-Center Refinement

## Current Build Pass
Pass 16 — Outreach Command-Center Refinement (complete)

## Last Completed Pass
Pass 16 — Outreach Command-Center Refinement

Commit: `7da49b5`

## Next Pass
Pass 17 — TBD (territory heatmap, saturation view, or tiled backend improvements)

## Upcoming Passes
- Search Visible Area button
- Tiled discovery backend (neighborhood-level grid)
- Territory discovery system

---

## Core Product

Copperline is an internal platform used to:

- Discover local service businesses
- Generate cold outreach drafts
- Send outreach manually via Gmail
- Track replies and follow-ups
- Convert prospects into clients
- Deploy missed-call texting automation

## Target Industries

- Plumbers
- HVAC companies
- Electricians
- Locksmiths
- Garage door companies
- Restoration contractors

---

## Key Systems

| System | Location |
|---|---|
| Lead discovery engine | `lead_engine/discovery/` |
| Outreach drafting | `lead_engine/outreach/` |
| Email queue | `lead_engine/queue/pending_emails.csv` |
| Follow-up automation | `lead_engine/run_lead_engine.py` |
| Map discovery interface | `lead_engine/dashboard_static/index.html` |
| Dashboard API | `lead_engine/dashboard_server.py` |

## Protected Systems

- `run_lead_engine.py`
- Queue schema (column order and naming)
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler
- `safe_autopilot_eligible` logic

## Active Constraints

- Discovery must be intentional — no auto-search on pan or zoom
- Large search areas surface only prominent businesses (by design)
- Neighborhood-level searches required to find independent operators
- No build steps — frontend is a single HTML file, CDN dependencies only
- Email sending is manual — auto-send not enabled
- Quick reply templates require `COPPERLINE_LINKS` config to be filled in before use

---

## Operator Goal

1. Find businesses via map
2. Start conversations via outreach
3. Close clients
4. Deploy missed-call texting automation

---

## Repo Quick Reference

| Question | File |
|---|---|
| What is being built now? | `docs/CURRENT_BUILD.md` |
| What is the project state? | `docs/PROJECT_STATE.md` |
| What must not be touched? | `docs/PROTECTED_SYSTEMS.md` |
| What is the map strategy? | `docs/DISCOVERY_MAP_VISION.md` |
| Full system overview | `docs/COPPERLINE_OVERVIEW.md` |
| Build rules | `docs/CLAUDE_BUILD_RULES.md` |
| Dev history | `docs/CHANGELOG_AI.md` |
