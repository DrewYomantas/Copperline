# Lead Engine Audit Status (Current State)

This document captures a blunt audit of the current `lead_engine` implementation as it exists in the repository.

## Real status now

- CSV-driven ingestion, scoring, deterministic drafting, queue writing, and gated sender CLI are implemented and runnable.
- Website intelligence and scoring are heuristic-level only (not robust lead intelligence).
- Sending safeguards are present and enforced by code path (`approved=true`, blank `sent_at`, non-empty `to_email`, plus explicit `--send-live`).
- Autonomous lead discovery is not implemented.

## Capability status

| Area | Status | Evidence |
|---|---|---|
| Input/ingestion | usable | `load_prospects_from_csv` validates header presence, required fields, normalizes blank-like values, and skips invalid rows. |
| Website scanning | weak | Single-page HTML fetch with simple string/regex checks and broad exception fallback to all-false signals. |
| Scoring | partial | Implemented 1-5 heuristic scoring with concise reasons; no deeper business context/modeling. |
| Draft generation | usable | Deterministic hash-rotated templates with local tone and explicit signer. |
| Queue generation | usable | Draft rows appended to CSV queue with dedupe and approval defaults; no sender action here. |
| Sending | usable | CLI sender supports dry-run/live modes and fails live with non-zero only on true send failures. |
| Autonomous discovery | missing | Explicitly documented as not implemented. |

## Highest-risk gaps

1. Website scan quality is simplistic and can misclassify modern JS-heavy sites.
2. Scoring is shallow heuristic logic, not evidence-backed performance prediction.
3. No automated test suite; behavior confidence is runtime/manual only.

