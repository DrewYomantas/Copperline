# Outreach Operator Panel + Lead Engine (local internal tool)

This is a **local operator workflow**, not a SaaS product.

This README is the current merged operator-panel source of truth (legacy V1 sections should not be duplicated below).

Core flow:
1. pick industry
2. pick quantity
3. click **Discover + Draft Outreach**
4. review queues
5. click **Dry Run Send**
6. click **Live Send** when ready

The existing deterministic internals remain:
- CSV ingestion
- heuristic discovery
- deterministic website scanning
- deterministic scoring
- deterministic email drafting
- approval-gated sending

## Launch the operator panel

From repo root:

```bat
launch_operator_panel.bat
```

Or directly:

```bash
python lead_engine/ui/operator_panel.py
```

## UI controls

Main window: **Outreach Operator Panel**

- Industry dropdown (loaded from `lead_engine/data/industries.csv`)
- Quantity dropdown (5, 10, 20, 30, 50; default 20)
- Optional city input (`Dallas, TX` style)
- Discover + Draft Outreach
- Install Playwright Help
- Open Email Queue
- Open Contact Form Queue
- Open Queue Folder
- Dry Run Send
- Live Send
- Refresh Status
- Read-only status/output area

Top summary counters show:
- Prospects rows
- Pending email rows
- Pending contact form rows
- Approved-ready emails
- Sent today / 20

## Playwright setup on Windows

If discovery reports a missing Playwright browser executable, run:

```bash
pip install playwright
python -m playwright install
```

The panel also includes an **Install Playwright Help** button that logs these commands and attempts to copy them to clipboard.

## Queue files

- Email queue: `lead_engine/queue/pending_emails.csv`
- Contact form queue: `lead_engine/queue/pending_contact_forms.csv`
- Contact history: `lead_engine/data/contact_history.csv`

If required CSV files are missing, the panel auto-creates them with headers.

Queue buttons use Explorer/file manager behavior (including opening the queue folder and selecting queue files on Windows), rather than depending on Excel.

If preferred, CSV queues can also be uploaded manually into Google Sheets for review and approval edits.

## Send safety rules

Live sending still requires all of the following:
- `approved=true`
- `to_email` present
- `sent_at` blank
- explicit live action (UI confirm dialog / `--send-live`)
- daily cap `MAX_DAILY_SEND = 20`

No auto-approve, no auto-send after drafting.

## Dry run vs live send

- **Dry Run Send**: shows what would send and cap impact, sends nothing.
- **Live Send**: requires confirmation and Gmail env vars.

## Gmail env vars (Windows PowerShell)

```powershell
$env:GMAIL_ADDRESS="you@gmail.com"
$env:GMAIL_APP_PASSWORD="your-16-char-app-password"
```

No extra pip install is required for sender logic (stdlib SMTP).

## Discovery reliability notes

Discovery is deterministic heuristic parsing (bounded web requests), not magical.
It can fail or return 0 results if search/network access is blocked.
When that happens, import leads into `lead_engine/data/prospects.csv` and run draft generation normally.

## CLI still available

Discovery + draft:
```bash
python lead_engine/run_lead_engine.py --discover HVAC --limit 30
python lead_engine/run_lead_engine.py --discover Plumbing --limit 30 --city "Dallas, TX"
```

Process existing prospects CSV:
```bash
python lead_engine/run_lead_engine.py --input lead_engine/data/prospects.csv --limit 50
```

Sender dry run:
```bash
python lead_engine/send/email_sender_agent.py --queue lead_engine/queue/pending_emails.csv --dry-run
```
