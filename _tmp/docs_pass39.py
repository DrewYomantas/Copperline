import re, os

BASE  = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs"
STATE = os.path.join(BASE, "PROJECT_STATE.md")
BUILD = os.path.join(BASE, "CURRENT_BUILD.md")
PANEL = os.path.join(BASE, "AI_CONTROL_PANEL.md")
CHLOG = os.path.join(BASE, "CHANGELOG_AI.md")

def replace_first(path, old, new):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if old in src:
        src = src.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"  REPLACED in {os.path.basename(path)}: {old[:50]!r}")
        return True
    print(f"  MISS in {os.path.basename(path)}: {old[:50]!r}")
    return False

def prepend(path, block, anchor):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if anchor in src and block[:40] not in src:
        src = src.replace(anchor, block + anchor, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"  PREPENDED to {os.path.basename(path)}")
    else:
        print(f"  SKIP (already present or anchor missing): {os.path.basename(path)}")

# ── PROJECT_STATE ────────────────────────────────────────────────────────────
replace_first(STATE, "## Current Focus\nDiscovery Review Recovery + Action Feedback",
                      "## Current Focus\nV2 Stage 2 — Unified Lead Workspace Backbone")

replace_first(STATE, "## Last Completed Pass\nPass 37 - Discovery Review Recovery + Action Feedback",
                      "## Last Completed Pass\nPass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel")

# Replace the pass 37 detail block
OLD_DETAIL = """- Restored editable map preview modal: subject input + body textarea + Save Edits button so operator can edit and save directly from the Discovery map panel without returning to Pipeline.
- Added Unschedule button to the map preview modal for scheduled rows.
- Added pending-state feedback to all slow panel actions: panelApprove, panelUnapprove, panelScheduleTomorrow, panelUnschedule — buttons disable and show in-progress label during the API call.
- Fixed backdrop close: clicking outside the review panel now closes it (was blocked by a toast). True backdrop mousedown+click required; drag-select inside panel never closes it.
- Added mousedown origin guard (`_panelMousedownOnBackdrop`) so text selection or input interaction inside the panel cannot accidentally dismiss it.
- Pending-state helpers `_btnPending` / `_btnRestore` added as shared utilities.

Commit: `4224d78`"""

NEW_DETAIL = """- Added `_leadKey(input)` — single stable identity key from either a biz object or queue row (place_id → website → phone → name+city priority).
- Added `_leadRecord(input)` — canonical normalizer returning one flat record covering identity, contact, qualification, workflow status, draft, observation, and history from either input type.
- Added `_leadResolve(input)` — resolves either input to a `{ biz, qrow, key }` pair. Synthesizes the missing half when only one side is provided.
- Added `_renderLeadWorkspaceHeader(record)` — shared HTML renderer for status badge, channel badges, score, observation hint, and next recommended action. Used in both Pipeline panel and Discovery preview modal.
- Wired `_renderLeadWorkspaceHeader` into `fillPanel` (Pipeline panel meta section).
- Wired `_renderLeadWorkspaceHeader` into `_mrpPreview` (Discovery map preview modal header).
- Added `mrp-modal-lws-header` div to modal HTML.
- Zero backend changes. No queue schema changes. No protected systems touched.

Commit: TBD"""

replace_first(STATE, OLD_DETAIL, NEW_DETAIL)
replace_first(STATE, "## Previous Completed Pass\nPass 36 - Observation-Led Outreach Rewrite",
                      "## Previous Completed Pass\nPass 37 - Discovery Review Recovery + Action Feedback")

# ── CURRENT_BUILD ────────────────────────────────────────────────────────────
with open(BUILD, "r", encoding="utf-8") as f:
    build_src = f.read()

P39_BLOCK = """# Current Build Pass

## Active System
V2 Stage 2 — Unified Lead Workspace Backbone

## Status
Pass 39 complete.

---

## Completed: Pass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel - TBD

Product change: `lead_engine/dashboard_static/index.html` only.
No backend changes. No protected systems touched.

### Stage 2A — Unified Lead Record Backbone

Added three shared JS utilities that give Discovery and Pipeline a common
record shape for any business, regardless of which side the data comes from.

**`_leadKey(input)`**
- Single identity key from either a `biz` map object or a queue `row`.
- Priority: `place_id` → normalized `website` → normalized `phone` → `name|city`.
- Produces the same key for the same business regardless of input type.
- Reuses existing `_mapNormalizeWebsite` / `_mapNormalizePhone` helpers.

**`_leadResolve(input)`**
- Returns `{ biz, qrow, key }` from either input type.
- Populates the missing half: biz → qrow via `_mrpResolveRow`; qrow → biz synthesized inline.
- `_mrpResolveRow` and existing callers unchanged — this wraps them.

**`_leadRecord(input)`**
- Canonical normalizer. Returns one flat object covering:
  - identity: name, city, state, website, phone, industry
  - contact: email, facebookUrl, instagramUrl, formUrl, hasEmail/hasFacebook/hasInstagram/hasForm, bestChannel
  - qualification: priorityScore, opportunityScore, scoringReason
  - workflow status: isSent, isApproved, isScheduled, isReplied, isDNC, isLegacyDraft, status (label), statusTone, nextAction
  - draft: subject, body, facebookDraft, observation
  - history: sentAt, repliedAt, replySnippet, contactAttempts, lastContactedAt, sendAfter, messageId
  - refs: rowIndex, _qrow, _biz

### Stage 2B — Unified Workspace Panel Header

**`_STATUS_TONE_STYLES`** — shared style map for status badges (replied, sent, scheduled, approved, drafted, new, blocked).

**`_renderLeadWorkspaceHeader(record)`**
- Shared HTML renderer for both panels.
- Renders: status badge (toned), score chip, observation tag (if present), city/state/industry, contact channel badges with links, next recommended action.
- Does not include edit controls — sits above them.

**Wired into fillPanel (Pipeline panel)**
- `panel-meta` innerHTML now prepends `_renderLeadWorkspaceHeader(_leadRecord(row))`.
- Existing meta parts (city link, phone, website, scan_note) still rendered below.
- No other fillPanel behavior changed.

**Wired into _mrpPreview (Discovery map preview modal)**
- Added `mrp-modal-lws-header` div to modal HTML.
- `_mrpPreview` now populates it via `_renderLeadWorkspaceHeader(_leadRecord(qrow))`.
- Existing title/sub/subject-input/textarea/footer unchanged.

### What's still separate (by design)

- Discovery list item rendering (`_mapRenderPanel`) still uses its own qualification logic — unifying that is a future pass.
- Queue table row rendering (`renderTable`) still uses `statusCellHtml` — unifying that is a future pass.
- `_mrpResolveRow` still does the fuzzy name+city lookup — `_leadResolve` calls through it, doesn't replace it.
- All send/approve/schedule/unschedule paths unchanged.

### Verification

- `node --check` on extracted dashboard JS: clean.
- `python -c "import dashboard_server"` import: clean.
- All 7 new symbols confirmed at expected line numbers via targeted search.

---

"""

old_header = """# Current Build Pass

## Active System
Discovery Review Recovery + Action Feedback

## Status
Pass 37 complete.

---

"""
if old_header in build_src:
    build_src = build_src.replace(old_header, P39_BLOCK, 1)
    print("BUILD: replaced header with Pass 39 block")
else:
    build_src = P39_BLOCK + build_src
    print("BUILD: prepended Pass 39 block")

with open(BUILD, "w", encoding="utf-8") as f:
    f.write(build_src)

# ── AI_CONTROL_PANEL ─────────────────────────────────────────────────────────
replace_first(PANEL, "## Current Focus\nDiscovery Review Recovery + Action Feedback",
                      "## Current Focus\nV2 Stage 2 — Unified Lead Workspace Backbone")
replace_first(PANEL, "## Current Build Pass\nPass 37 - Discovery Review Recovery + Action Feedback (complete)",
                      "## Current Build Pass\nPass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel (complete)")
replace_first(PANEL, "## Last Completed Pass\nPass 37 - Discovery Review Recovery + Action Feedback\n\nCommit: `4224d78`",
                      "## Last Completed Pass\nPass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel\n\nCommit: TBD")

# ── CHANGELOG ────────────────────────────────────────────────────────────────
P39_LOG = """### 2026-03-17 - Pass 39: V2 Stage 2A+2B — Unified Lead Record + Workspace Panel

**Goal:** Introduce a canonical lead record shape and shared workspace panel header so Discovery and Pipeline read/write through the same data model for a business.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**Stage 2A — new functions:**
- `_leadKey(input)` — stable identity key from biz or queue row
- `_leadResolve(input)` — resolves to `{ biz, qrow, key }` from either input
- `_leadRecord(input)` — canonical normalizer covering identity, contact, qualification, status, draft, observation, history

**Stage 2B — new functions + wiring:**
- `_STATUS_TONE_STYLES` — shared status badge style map
- `_renderLeadWorkspaceHeader(record)` — shared HTML for status + channels + score + obs tag + next action
- Wired into `fillPanel` (Pipeline panel meta section)
- Wired into `_mrpPreview` (Discovery map modal header)
- `mrp-modal-lws-header` div added to modal HTML

**No backend changes. No queue schema changes. No protected systems touched.**
All existing send/approve/schedule/unschedule behavior preserved.

**Commit:** TBD

---

"""

with open(CHLOG, "r", encoding="utf-8") as f:
    cl = f.read()

anchor = "### 2026-03-17 - Pass 38:"
if anchor in cl and "Pass 39" not in cl:
    cl = cl.replace(anchor, P39_LOG + anchor, 1)
    with open(CHLOG, "w", encoding="utf-8") as f:
        f.write(cl)
    print("CHANGELOG: Pass 39 prepended")
else:
    print("CHANGELOG: already present or anchor missing")

print("\nDone.")
