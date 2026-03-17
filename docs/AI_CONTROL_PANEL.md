# Copperline AI Control Panel

Last Updated: 2026-03-17
Repository Version: v0.2

---

## Project Phase
Lead Acquisition Engine

## Current Focus
Discovery Panel Organization + Edit Stability

## Current Build Pass
Pass 30 - Discovery Panel Organization + Edit Stability (complete)

## Last Completed Pass
Pass 30 - Discovery Panel Organization + Edit Stability

Commit: `pending`

## Next Pass
TBD

## Upcoming Passes
- Territory heatmap overlay
- Industry saturation view
- Tiled backend improvements (rate-limit handling)
- Update `Copperline-Outreach-Sequence.md` and `Copperline-Proposal-Template.md`

---

## Execution Model

Passes use bounded cohesive blocks, not artificially tiny micro-changes.

- A pass may include 3-6 tightly related changes if they all improve one operator workflow
- Scope is defined by workflow cohesion: all sub-changes must serve the same outcome
- Unrelated systems must not be bundled in a single pass
- Passes must be testable end-to-end when complete
- No redesigns or protected-system drift without explicit operator approval

Examples:
- Correct: grouped discovery results + stable edit state + active selection because all three improve one discovery-review workflow
- Incorrect: discovery + scheduler UX + message quality in one pass
- Previous completed example: Pass 29 combined circle-grid sweep, multi-industry selection, dedupe, history summary, cancel support, and bulk unschedule because all of them served one bounded operator workflow

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

- Discovery must be intentional - no auto-search on pan or zoom
- Large search areas surface only prominent businesses by design
- Neighborhood-level searches are required to find independent operators
- No build steps - frontend is a single HTML file with CDN dependencies only
- Email sending is manual - auto-send is not enabled
- Quick reply templates require `COPPERLINE_LINKS` config before live use

## Operator Goal

1. Find businesses via map
2. Start conversations via outreach
3. Close clients
4. Deploy missed-call texting automation

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
