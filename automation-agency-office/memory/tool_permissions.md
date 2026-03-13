# Tool Permissions

## Purpose
Define tool usage boundaries for agents and approval requirements.

## Allowed Without Additional Approval (Internal Use)
- Read/write approved internal memory files
- Spreadsheet/CSV updates for pipeline tracking
- Public web research tools (read-only)
- Draft generation tools for outreach/proposals/content

## Requires Founder Review
- CRM updates that trigger automated external communications
- Bulk data imports that may alter client/prospect records
- Changes to workflow logic affecting delivery commitments

## Requires Founder Approval
- Any tool action that sends external email/SMS/DMs
- Connecting new third-party integrations with account credentials
- Accessing billing, payments, or contract-signing systems
- Creating/changing API keys, webhooks, or production automations

## Security Conditions
- Use least-privilege access.
- Never share credentials in plain text.
- Log meaningful tool actions for auditability.
