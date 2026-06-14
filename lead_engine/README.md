# Copperline Core

`lead_engine/` contains the live Copperline pipeline and dashboard.

## Primary Files

- `dashboard_static/index.html`: main frontend shell
- `dashboard_server.py`: Flask routes and queue API
- `send/email_sender_agent.py`: shared send-readiness and validation truth
- `send/mail_config.py`: centralized Google Workspace SMTP identity and live-send gate
- `send/mail_config.py`: centralized Google Workspace SMTP sender identity and live-send gate
- `run_lead_engine.py`: main protected pipeline entrypoint
- `queue/pending_emails.csv`: live queue data

## Working Rule

Most operator-facing UI work lands in `dashboard_static/index.html`. Most queue truth work lands in `dashboard_server.py` and `send/email_sender_agent.py`. Treat changes across those files as production-impacting until verified live.

## High-Risk Areas

- send eligibility
- approval truth
- scheduling truth
- suppression and dedupe
- draft validation

## Outbound Mail

- Current path: Google Workspace SMTP through `drewyomantas@copperlineops.com`
- Required env vars are listed in the repo root `.env.example`
- Live sends are blocked unless `COPPERLINE_LIVE_SEND_ENABLED=true`
- Safe verification path: run `python lead_engine/send/email_sender_agent.py --dry-run --queue lead_engine/queue/pending_emails.csv`

## Mail Setup

Outbound mail sends through Google Workspace SMTP as `Drew @ Copperline <drewyomantas@copperlineops.com>`. Keep `COPPERLINE_LIVE_SEND_ENABLED=false` for local dry-run checks; set it to `true` only on the production operator machine after the Workspace account, app password, and DNS authentication are verified.

## Related Docs

- `../docs/README.md`
- `../docs/PROJECT_STATE.md`
- `../docs/PROTECTED_SYSTEMS.md`
