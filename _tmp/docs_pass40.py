import os

BASE  = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs"
STATE = os.path.join(BASE, "PROJECT_STATE.md")
BUILD = os.path.join(BASE, "CURRENT_BUILD.md")
PANEL = os.path.join(BASE, "AI_CONTROL_PANEL.md")
CHLOG = os.path.join(BASE, "CHANGELOG_AI.md")

def swap(path, old, new):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if old in src:
        src = src.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"  OK  {os.path.basename(path)}: {old[:55]!r}")
    else:
        print(f"  MISS {os.path.basename(path)}: {old[:55]!r}")

def prepend_entry(path, block, anchor):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if anchor in src and "Pass 40" not in src:
        src = src.replace(anchor, block + anchor, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"  PREPENDED {os.path.basename(path)}")
    else:
        print(f"  SKIP {os.path.basename(path)} (already present or anchor missing)")

# ── PROJECT_STATE ────────────────────────────────────────────────────────────
swap(STATE,
    "## Last Completed Pass\nPass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel",
    "## Last Completed Pass\nPass 40 - V2 Stage 2C — Shared Row State Rendering"
)

OLD_DETAIL = """- Added `_leadKey(input)` — single stable identity key from either a biz object or queue row (place_id → website → phone → name+city priority).
- Added `_leadRecord(input)` — canonical normalizer returning one flat record covering identity, contact, qualification, workflow status, draft, observation, and history from either input type.
- Added `_leadResolve(input)` — resolves either input to a `{ biz, qrow, key }` pair. Synthesizes the missing half when only one side is provided.
- Added `_renderLeadWorkspaceHeader(record)` — shared HTML renderer for status badge, channel badges, score, observation hint, and next recommended action. Used in both Pipeline panel and Discovery preview modal.
- Wired `_renderLeadWorkspaceHeader` into `fillPanel` (Pipeline panel meta section).
- Wired `_renderLeadWorkspaceHeader` into `_mrpPreview` (Discovery map preview modal header).
- Added `mrp-modal-lws-header` div to modal HTML.
- Zero backend changes. No queue schema changes. No protected systems touched.

Commit: `40f7db2`"""

NEW_DETAIL = """- Added `_leadStatusPills(record)` — shared pill HTML from `_leadRecord`. Replaces duplicate inline isSent/isApproved/isScheduled/score logic across both `_mapRenderPanel` render paths. Now also surfaces observation tag in both Discovery list views.
- Added `_leadNextActionHint(record)` — shared next-action hint HTML from `_leadRecord`. Added to both Discovery list renders (simple and triage).
- Replaced both inline `mrp-status-pills` blocks in `_mapRenderPanel` with calls to `_leadStatusPills` + `_leadNextActionHint`.
- Augmented `statusCellHtml` (Pipeline queue table): `_scSubline` now appends obs tag (when observation present) and next-action hint (when unsent) via `_leadRecord(row)`.
- Both Discovery list views and the Pipeline queue table now show materially consistent status, observation presence, and next-action from the same shared logic.
- Zero backend changes. No queue schema changes. No protected systems touched.

Commit: TBD"""

swap(STATE, OLD_DETAIL, NEW_DETAIL)
swap(STATE,
    "## Previous Completed Pass\nPass 37 - Discovery Review Recovery + Action Feedback",
    "## Previous Completed Pass\nPass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel"
)

# ── CURRENT_BUILD ─────────────────────────────────────────────────────────────
with open(BUILD, "r", encoding="utf-8") as f:
    build_src = f.read()

P40_BLOCK = """## Active System
V2 Stage 2C — Shared Row State Rendering

## Status
Pass 40 complete.

---

## Completed: Pass 40 - V2 Stage 2C — Shared Row State Rendering - TBD

Product change: `lead_engine/dashboard_static/index.html` only.
No backend changes. No protected systems touched.

Builds on the `_leadRecord` backbone from Pass 39.
Replaces duplicated inline row-state logic across Discovery and Pipeline
with two shared helpers, and adds observation + next-action visibility
to both views.

### New helpers

**`_leadStatusPills(record)`** (line ~1570)
- Returns innerHTML for a `.mrp-status-pills` div from a `_leadRecord`.
- Status pill uses the `mrp-pill` CSS classes (sent/scheduled/approved/drafted).
- Score pill added when `priorityScore > 0`.
- Observation tag (`obs` in copper) added when `observation` is present.
- Single source of truth for pill rendering — no more inline copies.

**`_leadNextActionHint(record)`** (line ~1599)
- Returns a compact `div` HTML string with `record.nextAction`.
- Empty string when no action is defined.
- Consistent next-action text across both Discovery renders.

### Changes to existing renders

**First `_mapRenderPanel` block (simple render)**
- Replaced 8-line inline `isSent / isApproved / isScheduled / score / pill` block
  with `_leadRecord(qrow)` → `_leadStatusPills` + `_leadNextActionHint`.
- `isSent`, `isApproved`, `isScheduled`, `score` variables preserved from `_lrSimple`
  for the downstream action buttons that still need them.

**Second `_mapRenderPanel` block (triage render)**
- Same replacement pattern via `_lrTriage`.
- Both list views now show observation tag when present.
- Both list views now show next-action hint below pills.

**`statusCellHtml` (Pipeline queue table)**
- `_leadRecord(row)` already injected as `_scRecord` in Pass 40.
- Added `_scSubExtra` and `_scSubline` to append:
  - `obs` to the subline text when `_scRecord.observation` is present.
  - `nextAction` text to the subline when unsent and action is defined.
- Same `statusBadge` and `_queueStateMeta` behavior preserved — only the
  subline text is extended.

### What this achieves

| Concern | Before | After |
|---|---|---|
| Status pills | Duplicated in 2 places | Shared via `_leadStatusPills` |
| Observation presence | Not visible in Discovery list | Visible in both list views |
| Next-action hint | Not visible anywhere in lists | Visible in Discovery lists + Pipeline status subline |
| Pipeline status subline | `_queueStateMeta` text only | Extended with obs + next-action |

### Verification

- `node --check` on extracted dashboard JS: clean.
- `python -c "import dashboard_server"` import: clean.
- All 5 change sites confirmed via targeted search at expected line numbers.

---

"""

old_header = "## Active System\nV2 Stage 2 — Unified Lead Workspace Backbone\n\n## Status\nPass 39 complete.\n\n---\n\n"
if old_header in build_src:
    build_src = build_src.replace(old_header, P40_BLOCK, 1)
    print("  BUILD header replaced")
else:
    build_src = P40_BLOCK + build_src
    print("  BUILD prepended (header not matched)")

with open(BUILD, "w", encoding="utf-8") as f:
    f.write(build_src)

# ── AI_CONTROL_PANEL ──────────────────────────────────────────────────────────
swap(PANEL,
    "## Current Build Pass\nPass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel (complete)",
    "## Current Build Pass\nPass 40 - V2 Stage 2C — Shared Row State Rendering (complete)"
)
swap(PANEL,
    "## Last Completed Pass\nPass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel\n\nCommit: `40f7db2`",
    "## Last Completed Pass\nPass 40 - V2 Stage 2C — Shared Row State Rendering\n\nCommit: TBD"
)

# ── CHANGELOG ─────────────────────────────────────────────────────────────────
P40_LOG = """### 2026-03-17 - Pass 40: V2 Stage 2C — Shared Row State Rendering

**Goal:** Reduce duplicated row-state logic between Discovery and Pipeline renders. Add observation visibility and next-action hints to both views consistently.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- Added `_leadStatusPills(record)` — shared pill renderer from `_leadRecord`. Replaces both inline `mrp-status-pills` blocks in `_mapRenderPanel`. Now also shows observation tag in Discovery list items.
- Added `_leadNextActionHint(record)` — shared next-action hint HTML. Added to both Discovery list renders.
- Both `_mapRenderPanel` pill blocks replaced with `_leadStatusPills` + `_leadNextActionHint` via `_leadRecord(qrow)`.
- `statusCellHtml` subline extended: `obs` tag appended when observation present; `nextAction` text appended when unsent.

**No backend changes. No queue schema changes. No protected systems touched.**

**Commit:** TBD

---

"""

prepend_entry(CHLOG, P40_LOG, "### 2026-03-17 - Pass 39:")

print("\nDone.")
