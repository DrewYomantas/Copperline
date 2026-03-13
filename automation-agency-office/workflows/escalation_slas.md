# Escalation SLAs

## Severity Levels

| Severity | Definition | Initial Response Expectation | Escalation Deadline | Typical Owner |
|---|---|---|---|---|
| Critical | Active client-impacting failure, severe security risk, or major operational outage. | <= 15 minutes | Immediate founder escalation; continuous updates until stabilized. | `automation_health_monitor_agent` + `maintenance_response_agent` |
| High | Time-sensitive issue likely to cause near-term revenue, delivery, or trust impact if delayed. | <= 1 hour | Escalate to founder within 2 hours if unresolved. | `revenue_operations_supervisor_agent` / domain owner |
| Medium | Important issue with moderate impact; can wait for same-day handling. | <= 4 hours | Escalate within 1 business day if unresolved. | Relevant functional agent + supervisor |
| Low | Routine optimization, minor delay, or informational gap with limited near-term impact. | <= 1 business day | Escalate in weekly summary if still open. | Relevant functional agent |

## Example Classification Guide

| Scenario | Recommended Severity | Response Expectation | Escalation Notes |
|---|---|---|---|
| client automation down | Critical | Start incident workflow immediately; acknowledge <= 15 min. | Founder notified immediately; track fixes and validation in incident logs. |
| prospect reply waiting too long | High | Draft follow-up and pipeline update <= 1 hour after breach. | Escalate to RevOps supervisor; founder if repeated SLA misses. |
| social DM ignored too long | High | Draft compliant response <= 1 hour after breach. | Escalate to supervisor; founder for sensitive/reputational messages. |
| stale proposal | Medium | Re-open proposal task and update ETA same day. | Escalate to founder next business day if blocked or out-of-range pricing requested. |
| missed weekly brief | Medium | Chief of Staff generates catch-up brief same day. | Escalate to founder if still missing by next business day. |
| unresolved maintenance incident | High (or Critical if client impact active) | Re-prioritize and assign owner <= 1 hour after breach. | Founder escalation within 2 hours if unresolved under High, immediate if Critical. |

## SLA Logging Requirements
- Every SLA breach must be logged with timestamp, owner, and next action.
- Escalation hops (agent -> supervisor -> founder) must be recorded in relevant logs.
- Closed incidents should include root cause and prevention note.
