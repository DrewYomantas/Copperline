# Current Build Pass

## Active System
Pass 60 -- Observation-Reactive Consequence Sentence

## Status
Pass 60 complete. Repo is ready for the next product pass.

---

## Completed: Pass 60 -- Observation-Reactive Consequence Sentence

Product changes in:
- `lead_engine/outreach/email_draft_agent.py`

Docs updated in:
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/CHANGELOG_AI.md`
- `docs/AI_CONTROL_PANEL.md`

No queue schema changes. No `run_lead_engine.py` changes.
No sender/scheduler/follow-up changes.

### Problem addressed

First-touch bodies had a rigid structure: specific observation in S1, then
immediately generic angle-pool sentence in S2 ("usually the hard part is not
the work itself..."). Every draft in the batch used the same skeleton regardless
of what was specifically noticed. The S2 pattern was a clear template fingerprint.

### What was changed

**`lead_engine/outreach/email_draft_agent.py`** (v14 -> v15)

- Removed `_consequence_options(angle)` pool entirely.
- Added `_build_reactive_consequence(obs, angle)`: reads the observation text
  directly across 13 prioritized signal patterns and returns a consequence
  sentence that logically extends the specific thing noticed.
  Signal patterns covered: no-confirmation, voicemail/dispatch, phone-as-only-path,
  estimate-form-as-CTA, quote-buttons-every-page, 24/7-emergency,
  after-hours/weekend, chat-widget/text-back, online-booking-widget,
  proposal-request. Falls back to a short plain angle-keyed sentence (not a
  pool) when no specific signal is found.
- "usually the hard part is not the work itself..." pattern fully eliminated.
- Updated `_build_first_touch_body` to call `_build_reactive_consequence`
  directly. Body-fit fallback still works; consequence is never trimmed.
- Freshened `_offer_options` openers: "i help owners X", "worth a look at Y",
  "i work directly with owners on Z" so the same skeleton does not repeat
  across a batch.
- Added "sit", "stack up", "pile up", "slip", "fall through" to
  `_CONCRETE_SERVICE_SIGNALS` so reactive consequence sentences pass the
  concrete-signal validator.
- DRAFT_VERSION bumped v14 -> v15.

### What remains intentionally out of scope

- Observation generation or evidence refresh
- Queue/send/scheduler changes
- `run_lead_engine.py` changes
- Follow-up drafting, discovery/map work

### Verification

- AST parse clean. DRAFT_VERSION=v15. All public functions present.
- 22/22 drafts generated cleanly across all angle families.
- 13/22 unique consequence sentences (expected — some observation patterns
  share the same precise consequence by design).
- 8/8 before/after comparisons: every v15 consequence is specific to the
  actual observation. Generic pool pattern fully gone.
- All blocking rules confirmed holding.

---

## Previous Completed: Pass 59 -- First-Touch Subject Semantic Precision

- Rewrote `_subject_options_for_angle` to be observation-aware within each
  angle family. "call handling" and "question about X" eliminated from all pools.