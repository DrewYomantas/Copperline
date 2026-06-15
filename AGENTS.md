# OfficeAutomation (Copperline) — Codex Instructions

## ⚠️ LIVE PRODUCTION SYSTEM
This pipeline sends real outbound emails to real leads. 100+ emails sent, live replies active as of March 2026.

**Before running ANY command that triggers the pipeline:**
- Confirm you intend to run against production
- Never use production lead lists for testing
- Changes to email generation, send scheduling, or suppression logic require explicit review before execution

## What This Is
Copperline — a 7-agent AI pipeline for outbound lead acquisition.
Agents: prospecting → website scanning → opportunity scoring → AI draft generation → send scheduling → reply detection → suppression management.

## Tech Stack
- Backend: Python/Flask
- Frontend: Leaflet.js (map-based UI)
- AI pipeline: 7 agents (details in lead_engine/)
- Email delivery: configured via .env

## Critical Files
| File/Folder | Notes |
|---|---|
| `.env` | **Never commit. Contains API keys and email credentials.** |
| `lead_engine/` | Core pipeline — edit with caution |
| `automation-agency-office/` | Agency-facing UI and configuration |
| `missed_call_service/` | Separate service |

## Commands
```bash
# Always activate the virtual environment first
source .venv/bin/activate   # macOS/Linux
.venv\Scripts\activate      # Windows

# Then run Flask
flask run
# or check for a specific entrypoint in the project
```

## Safety Rules
1. `.env` must never be staged or committed — verify before every commit
2. Never trigger a send loop during debugging — use test mode / dry run if available
3. If you're not sure whether a command will send real emails, ask before running it
4. The suppression list is critical — do not truncate or overwrite it

## Git
- Remote: `origin → https://github.com/DrewYomantas/Copperline.git` (migrated from BeyondDrewTV)
- Branch: main

## Repo-Level Codex Settings
`.Codex/settings.json` exists with a production guard hook. It fires a warning before any `flask run`, `run_lead_engine`, or send/outreach commands, and before any `git add/commit`.
