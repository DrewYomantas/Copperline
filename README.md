# Copperline

Copperline is the live outbound lead engine inside OfficeAutomation. It handles discovery, website review, scoring, draft generation, operator approval, scheduling, send gating, and reply-state tracking.

This repo is production-facing. Treat changes to queue truth, send eligibility, scheduling, suppression, and draft validation as high-risk until verified live.

## Start Here

- [docs/README.md](docs/README.md)
- [docs/AI_START_HERE.md](docs/AI_START_HERE.md)
- [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md)
- [docs/CURRENT_BUILD.md](docs/CURRENT_BUILD.md)
- [docs/PROTECTED_SYSTEMS.md](docs/PROTECTED_SYSTEMS.md)

## Live App

- Dashboard: `http://127.0.0.1:5000/`
- Main frontend: `lead_engine/dashboard_static/index.html`
- Main backend: `lead_engine/dashboard_server.py`
- Shared send truth: `lead_engine/send/email_sender_agent.py`
- Outbound sender identity: `drewyomantas@copperlineops.com` through Google Workspace SMTP, configured in `lead_engine/send/mail_config.py`

## Current Baseline

- Queue recovery / batch repair architecture: `30efab893269e27acf266cedca108878efeebc78`
- Global app-shell / nav regression recovery: `c41e141cb3814767cad7e324af706ad582675881`
- Queue repair stabilization: `b6a54f53334e28bf74398b71b0c0cef9ade8cafa`

## Repo Layout

- `lead_engine/` core pipeline, dashboard, queue, send logic
- `docs/` active operating docs and durable project reference
- `docs/reference/` proposal, outreach, and go-live reference assets
- `automation-agency-office/` agency-facing UI/config work
- `missed_call_service/` separate delivery-side service

## Cleanup Rule

The repo root should stay limited to launchers, top-level config, and essential entry docs. Reference assets belong under `docs/reference/`. Scratch scripts, browser output, and temp QA files belong in ignored temp folders, not in the root.
