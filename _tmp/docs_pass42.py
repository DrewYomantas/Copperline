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
        print(f"  OK  {os.path.basename(path)}")
        return True
    print(f"  MISS {os.path.basename(path)}: {old[:50]!r}")
    return False

def prepend(path, block, anchor):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if anchor in src and "Pass 42" not in src:
        src = src.replace(anchor, block + anchor, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"  PREPENDED {os.path.basename(path)}")
    else:
        print(f"  SKIP {os.path.basename(path)}")

# ── PROJECT_STATE ─────────────────────────────────────────────────────────────
swap(STATE,
    "## Last Completed Pass\nPass 41 - V2 Stage 2D — Stable Key Propagation + Stronger Discovery-Queue Linking",
    "## Last Completed Pass\nPass 42 - V2 Stage 2E — Qualification + Status Derivation Unification"
)

OLD_DETAIL = (
    "- Added `_leadKeyIndex` module var \u2014 a `Map<_leadKey, row>` rebuilt on every `loadAll()` call.\n"
    "- Added `_buildLeadKeyIndex(rows)` \u2014 builds the index using `_leadKey(row)` (website \u2192 phone \u2192 name+city priority) for O(1) stable-key lookup. Zero collisions confirmed against live queue (162 unique websites, 179 unique phones).\n"
    "- Wired `_buildLeadKeyIndex(allRows)` into `loadAll()` immediately after `allRows` is assigned.\n"
    "- Rewrote `_mrpResolveRow(biz)`: (1) exact `_leadKeyIndex.get(_leadKey(biz))` lookup; (2) name+city scan fallback for legacy rows; (3) name-only last resort preserved for full backward compatibility.\n"
    "- All `_mrpResolveRow` call sites unchanged \u2014 upgrade is entirely internal to the function.\n"
    "- Zero backend changes. No queue schema changes. No protected systems touched.\n"
    "\nCommit: `4159c60`"
)
NEW_DETAIL = (
    "- Extended `_leadRecord` with `hasWebsite`, `hasPhone` (contact), `isStale`, `isReadyScheduled` (workflow) so shared helpers can read all qualification + status signals from one place.\n"
    "- Added `_leadQualBucket(record, extras)` \u2014 shared qualification bucket logic (ready/maybe/needs-contact/weak/closed) extracted from `_mapPanelQualification` and generalized for both Discovery and Pipeline.\n"
    "- Added `_leadStatusMeta(record)` \u2014 shared status badge/label/subline/detail/tone logic extracted from `_queueStateMeta` and derived entirely from `_leadRecord`.\n"
    "- `_queueStateMeta` rewritten as a one-line wrapper: `return _leadStatusMeta(_leadRecord(row))`.\n"
    "- `_mapPanelQualification` rewritten as a thin wrapper: builds `_leadRecord`, merges biz-only extras, calls `_leadQualBucket`, returns compatible shape.\n"
    "- Discovery and Pipeline now derive qualification bucket and status meaning from the same two shared helpers.\n"
    "- Zero backend changes. No queue schema changes. No protected systems touched.\n"
    "\nCommit: TBD"
)
swap(STATE, OLD_DETAIL, NEW_DETAIL)

swap(STATE,
    "## Previous Completed Pass\nPass 40 - V2 Stage 2C \u2014 Shared Row State Rendering",
    "## Previous Completed Pass\nPass 41 - V2 Stage 2D \u2014 Stable Key Propagation"
)

# ── CURRENT_BUILD ─────────────────────────────────────────────────────────────
with open(BUILD, "r", encoding="utf-8") as f:
    build_src = f.read()

P42_BLOCK = """## Active System
V2 Stage 2E \u2014 Qualification + Status Derivation Unification

## Status
Pass 42 complete.

---

## Completed: Pass 42 - V2 Stage 2E \u2014 Qualification + Status Derivation Unification - TBD

Product change: `lead_engine/dashboard_static/index.html` only.
No backend changes. No protected systems touched.

### Problem addressed

`_mapPanelQualification` (Discovery) and `_queueStateMeta` (Pipeline) both
computed `isSent`, `isApproved`, `isScheduled`, qualification bucket logic,
and status badge/label/tone independently. Same lead = different derivation path.

### Changes

**`_leadRecord` extensions**
- `hasWebsite` and `hasPhone` added to contact section and return object.
- `isStale` and `isReadyScheduled` added to workflow section and return object.
- These four fields were previously recomputed inline in both `_mapPanelQualification`
  and `_queueStateMeta` on every call. Now derived once in `_leadRecord`.

**`_leadQualBucket(record, extras)`** (new, before Stage 2B header)
- Shared qualification bucket: ready / maybe / needs-contact / weak / closed.
- Takes a `_leadRecord` plus optional biz-only extras (rating, reviewCount, contactability).
- Extras allow Discovery to pass map-result signals not present in queue rows.
- Returns `{ key, label, order, tone, reasons }` — same shape as old inline code.

**`_leadStatusMeta(record)`** (new, before Stage 2B header)
- Shared status badge/label/subline/detail/tone from `_leadRecord`.
- Reads `isReplied`, `isSent`, `isStale`, `isScheduled`, `isReadyScheduled`, `isApproved`
  from the record, plus `sendAfter` for schedule formatting.
- Returns same shape as old `_queueStateMeta` body.

**`_queueStateMeta(row)` rewritten**
- Was: 60-line function with full inline derivation.
- Now: `return _leadStatusMeta(_leadRecord(row));`
- Return shape identical. All callers (`statusCellHtml`, `fillPanel`, etc.) unchanged.

**`_mapPanelQualification(item, qrow)` rewritten**
- Was: 80-line function recomputing all contact/status fields inline.
- Now: builds `_leadRecord(baseInput)`, merges biz-object overrides for contact fields,
  builds extras object with biz-only signals, calls `_leadQualBucket`.
- Return shape identical. All callers (`_mapRenderPanel`, triage render, etc.) unchanged.

### What now derives from shared helpers

| Concern | Old source | New source |
|---|---|---|
| Qualification bucket (ready/maybe/etc.) | Inline in `_mapPanelQualification` | `_leadQualBucket` |
| Status badge/label/subline | Inline in `_queueStateMeta` | `_leadStatusMeta` |
| isStale | Inline in `_queueStateMeta` | `_leadRecord.isStale` |
| isReadyScheduled | Inline in `_queueStateMeta` | `_leadRecord.isReadyScheduled` |
| hasWebsite, hasPhone | Inline in `_mapPanelQualification` | `_leadRecord.hasWebsite/Phone` |

### What remains separate on purpose

- `statusBadge(row)` \u2014 compact table badge with different visual purpose; still reads row directly.
  Could call `_leadStatusMeta` in a future pass.
- Biz-only extras in `_mapPanelQualification` (rating, reviewCount, contactability) \u2014 these come
  from map-result biz objects and are intentionally not in `_leadRecord` or queue rows.
- `isRowActionable(row)` / filter logic \u2014 separate concern; reads `row.is_ready` directly.

### Verification

- `node --check` on extracted dashboard JS: clean.
- `python -c "import dashboard_server"` import: clean.
- All 8 change sites confirmed: `_leadQualBucket` at line ~1493, `_leadStatusMeta` at ~1545,
  `_queueStateMeta` wrapper at ~2048, `_mapPanelQualification` wrapper at ~5379,
  `_leadRecord` extensions at ~6275, 6343, 6348.

---

"""

old_hdr = "## Active System\nV2 Stage 2D \u2014 Stable Key Propagation + Stronger Discovery-Queue Linking\n\n## Status\nPass 41 complete.\n\n---\n\n"
if old_hdr in build_src:
    build_src = build_src.replace(old_hdr, P42_BLOCK, 1)
    print("  BUILD header replaced")
else:
    build_src = P42_BLOCK + build_src
    print("  BUILD prepended")
with open(BUILD, "w", encoding="utf-8") as f:
    f.write(build_src)

# ── AI_CONTROL_PANEL ──────────────────────────────────────────────────────────
swap(PANEL,
    "## Current Build Pass\nPass 41 - V2 Stage 2D \u2014 Stable Key Propagation (complete)",
    "## Current Build Pass\nPass 42 - V2 Stage 2E \u2014 Qualification + Status Derivation Unification (complete)"
)
swap(PANEL,
    "## Last Completed Pass\nPass 41 - V2 Stage 2D \u2014 Stable Key Propagation\n\nCommit: `4159c60`",
    "## Last Completed Pass\nPass 42 - V2 Stage 2E \u2014 Qualification + Status Derivation Unification\n\nCommit: TBD"
)

# ── CHANGELOG ─────────────────────────────────────────────────────────────────
P42_LOG = """### 2026-03-17 - Pass 42: V2 Stage 2E \u2014 Qualification + Status Derivation Unification

**Goal:** Centralize qualification bucket and status badge/label derivation so Discovery and Pipeline use the same shared helpers, not parallel inline logic.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- `_leadRecord` extended: `hasWebsite`, `hasPhone`, `isStale`, `isReadyScheduled` added.
- `_leadQualBucket(record, extras)` \u2014 shared qualification bucket (ready/maybe/needs-contact/weak/closed).
- `_leadStatusMeta(record)` \u2014 shared status badge/label/subline/detail/tone.
- `_queueStateMeta` rewritten as `return _leadStatusMeta(_leadRecord(row))`.
- `_mapPanelQualification` rewritten as thin wrapper over `_leadRecord` + `_leadQualBucket`.

**No backend changes. No queue schema changes. No protected systems touched.**
All caller shapes preserved.

**Commit:** TBD

---

"""
prepend(CHLOG, P42_LOG, "### 2026-03-17 - Pass 41:")

print("\nDone.")
