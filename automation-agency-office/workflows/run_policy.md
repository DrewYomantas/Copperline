# Run Policy

## Core Rules
1. Agents only run on schedule, event trigger, or explicit founder request.
2. No agent runs just to create activity.
3. No external action without approval if policy requires it.
4. If signal is weak or no new input exists, an agent may skip run and must log skip reason.
5. All runs must log to `office_health_log.md` or relevant operational logs.
6. Event-triggered runs override scheduled cadence when urgent.
7. Agents must respect cooldown windows to avoid spammy repeated actions.

## Operational Clarifications
- A "run" means execution with observable input evaluation and a logged outcome (`executed`, `skipped`, `escalated`, or `blocked`).
- Skip logs should include timestamp, agent, trigger source, and explicit reason.
- Urgent event-triggered runs should execute immediately when safety and authority constraints are satisfied.
- Cooldowns apply especially to outreach and social-response drafting flows to prevent repetitive output loops.

## Compliance Constraints
- All runs must comply with `memory/agent_authority.md`, `memory/external_interaction_policy.md`, and `memory/agent_security_policy.md`.
- Agents must not bypass founder approvals for external communications, pricing exceptions, or other approval-gated actions.
