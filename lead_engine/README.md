# Copperline — Lead Engine (V1)

A lightweight Python pipeline to:
1. Load local service business prospects from CSV
2. Scan each website with bounded deterministic multi-page heuristics
3. Score opportunity priority (1-5)
4. Draft deterministic outreach emails
5. Queue emails for human approval
6. Send only approved emails when live-send is explicitly enabled

## Important limitations

- **Autonomous lead discovery is not implemented in V1.** Input must come from `data/prospects.csv`.
- The system does not scrape directories or discover new companies on its own.

## Folder layout

- `discovery/` prospect ingestion
- `intelligence/` website signal scanning
- `scoring/` lead prioritization
- `outreach/` outreach drafting
- `send/` approved email sending
- `queue/` email approval queue CSV
- `data/` source prospects CSV

## Setup

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate
```

## Input data

Populate `data/prospects.csv` with rows using this header:

```csv
business_name,city,state,website,phone,contact_method,likely_opportunity,priority_score
```

## Run lead processing

This builds/updates `queue/pending_emails.csv`.

```bash
python lead_engine/run_lead_engine.py --input lead_engine/data/prospects.csv --limit 50
```

Useful flags:
- `--input <path>` custom prospects CSV
- `--limit <n>` process only first n rows
- `--skip-scan` skip website fetch/scanning

Behavior:
- Scans real HTTP/HTTPS URLs with a small bounded crawl (homepage + common contact/service paths + discovered internal contact/service links)
- Detects deterministic signals (reachability, forms, phone/email visibility, booking/quote/schedule CTAs, chat vendors, mobile viewport hint, weak-site clues)
- Scores each lead
- Drafts email subject + body
- Adds to queue with `approved=false`
- Skips duplicates by `business_name + website`
- Prints startup summary with rows loaded, websites scanned, drafts created, skipped, and send-eligible count

Scanner notes:
- Deterministic heuristic analysis only (not ML/LLM).
- Fetch is bounded by timeout and max pages to keep runs safe.
- Failures (timeouts/403/SSL/etc.) are handled as warnings and do not crash pipeline runs.

## Approval workflow (required before sending)

1. Open `queue/pending_emails.csv`
2. Fill `to_email`
3. Set `approved=true` for rows ready to send
4. Leave unapproved rows as `approved=false`

The sender only processes rows where:
- `approved=true`
- `sent_at` is blank
- `to_email` is present
- `send_live=True` is passed explicitly

## Gmail app password usage

Set environment variables before live sends:

```bash
export GMAIL_ADDRESS=drewyomantas@gmail.com
export GMAIL_APP_PASSWORD=shxl ubrr smht nflv

```

Use a Gmail App Password (Google account security settings), not your normal Gmail password.

## Send script usage

Exact send flow:
1. Generate drafts:

```bash
python lead_engine/run_lead_engine.py --input lead_engine/data/prospects.csv
```

2. Manually review `lead_engine/queue/pending_emails.csv`.
3. Set `approved=true` for rows you want to send, and fill `to_email`.
4. Run sender in dry run (default):

```bash
python lead_engine/send/email_sender_agent.py --queue lead_engine/queue/pending_emails.csv --dry-run
```

5. Run sender live:

```bash
python lead_engine/send/email_sender_agent.py --queue lead_engine/queue/pending_emails.csv --send-live
```

CLI flags:
- `--queue <path>` queue CSV path
- `--dry-run` (default behavior; no emails are sent)
- `--send-live` (sends approved rows with blank `sent_at` and non-empty `to_email`)

Sender prints counts for:
- drafted
- skipped
- approved-ready
- sent
- failed

## Paste/import workflow (run immediately)

1. Copy the sample file and paste your own rows:

```bash
cp lead_engine/data/prospects.sample.csv lead_engine/data/prospects.csv
```

2. Keep at least these required values per row:
- `business_name`
- `city`
- `state`

3. Optional fields (`website`, `phone`, `contact_method`, etc.) can be blank.

4. Blank-like values are normalized to empty automatically: `""`, `unknown`, `n/a`, `na`, `none`, `null`, `-`, `--`.

5. Run the pipeline:

```bash
python lead_engine/run_lead_engine.py --input lead_engine/data/prospects.csv
```

Dedupe logic used by queueing:
- `business_name + website` (when website exists)
- otherwise `business_name + city`
