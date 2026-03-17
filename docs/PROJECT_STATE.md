# Copperline Project State

Last Updated: 2026-03-17

## Copperline Version
v0.2

## Current Phase
Lead Acquisition Engine

## Current Focus
Contact Quality Upgrade

## Copperline Positioning
Copperline = Service Business Operations

We identify where service businesses are losing work - missed calls, cold estimates, follow-ups that never happen - and install simple systems to fix it.

Automation is the implementation layer, not the headline.
Missed-call texting is one downstream solution, not the primary pitch.
Outreach goal: start a conversation about operational problems, not sell a product.

## Last Completed Pass
Pass 31 - Contact Quality Upgrade

- Expanded website contact extraction to capture more hidden-but-valid email patterns, including `mailto:` actions, attribute-based email values, simple `[at]` / `[dot]` obfuscation, paired `data-user` + `data-domain` attributes, and Cloudflare-style protected email tokens.
- Strengthened email normalization and candidate ranking so duplicate/junk candidates are filtered more safely and stronger role/domain matches are preferred.
- Replaced the no-op enrichment helper with a working prospect email-enrichment pass that can upgrade stored discovery rows using the same extraction logic.
- Tightened outreach draft guardrails so generated email and social/contact-form messages stay shorter, cleaner, and less awkward while preserving the existing short local-business tone.
- Verified extraction behavior on representative hidden-email patterns, enrichment updates on a temp prospects CSV, and cleaned draft outputs through targeted Python smoke checks.
- Reconfirmed the live dashboard still loads after the backend changes and did not touch protected systems.

Commit: `3098082`

## Previous Completed Pass
Pass 30 - Discovery Panel Organization + Edit Stability

## Next Pass
TBD

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
4. Scheduled queue sorted by send time - open it in the morning, send in order
5. Emails sent manually via Gmail
6. Follow-ups tracked automatically
7. Clients onboarded to missed-call texting service
