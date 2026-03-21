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
        return True
    print(f"  MISS {os.path.basename(path)}: {old[:55]!r}")
    return False

def prepend_entry(path, block, anchor):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if anchor in src and "Pass 41" not in src:
        src = src.replace(anchor, block + anchor, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"  PREPENDED {os.path.basename(path)}")
    else:
        print(f"  SKIP {os.path.basename(path)}")

# ── PROJECT_STATE ────────────────────────────────────────────────────────────
swap(STATE,
    "## Last Completed Pass\nPass 40 - V2 Stage 2C — Shared Row State Rendering",
    "## Last Completed Pass\nPass 41 - V2 Stage 2D — Stable Key Propagation + Stronger Discovery-Queue Linking"
)

OLD_DETAIL = ("- Added `_leadStatusPills(record)` — shared pill HTML from `_leadRecord`. Replaces duplicate inline isSent/isApproved/isScheduled/score logic across both `_mapRenderPanel` render paths. Now also surfaces observation tag in both Discovery list views.\n"
"- Added `_leadNextActionHint(record)` — shared next-action hint HTML from `_leadRecord`. Added to both Discovery list renders (simple and triage).\n"
"- Replaced both inline `mrp-status-pills` blocks in `_mapRenderPanel` with calls to `_leadStatusPills` + `_leadNextActionHint`.\n"
"- Augmented `statusCellHtml` (Pipeline queue table): `_scSubline` now appends obs tag (when observation present) and next-action hint (when unsent) via `_leadRecord(row)`.\n"
"- Both Discovery list views and the Pipeline queue table now show materially consistent status, observation presence, and next-action from the same shared logic.\n"
"- Zero backend changes. No queue schema changes. No protected systems touched.\n"
"\nCommit: `8abbb57`")

NEW_DETAIL = ("- Added `_leadKeyIndex` module var — a `Map<_leadKey, row>` rebuilt on every `loadAll()` call.\n"
"- Added `_buildLeadKeyIndex(rows)` — builds the index using `_leadKey(row)` (website → phone → name+city priority) for O(1) stable-key lookup. Zero collisions confirmed against live queue (162 unique websites, 179 unique phones).\n"
"- Wired `_buildLeadKeyIndex(allRows)` into `loadAll()` immediately after `allRows` is assigned.\n"
"- Rewrote `_mrpResolveRow(biz)`: (1) exact `_leadKeyIndex.get(_leadKey(biz))` lookup; (2) name+city scan fallback for legacy rows; (3) name-only last resort preserved for full backward compatibility.\n"
"- All `_mrpResolveRow` call sites unchanged — upgrade is entirely internal to the function.\n"
"- Zero backend changes. No queue schema changes. No protected systems touched.\n"
"\nCommit: TBD")

swap(STATE, OLD_DETAIL, NEW_DETAIL)
swap(STATE,
    "## Previous Completed Pass\nPass 39 - V2 Stage 2A+2B — Unified Lead Record + Workspace Panel",
    "## Previous Completed Pass\nPass 40 - V2 Stage 2C — Shared Row State Rendering"
)

# ── CURRENT_BUILD ─────────────────────────────────────────────────────────────
with open(BUILD, "r", encoding="utf-8") as f:
    build_src = f.read()

P41_BLOCK = """## Active System
V2 Stage 2D — Stable Key Propagation + Stronger Discovery-Queue Linking

## Status
Pass 41 complete.

---

## Completed: Pass 41 - V2 Stage 2D — Stable Key Propagation + Stronger Discovery-Queue Linking - TBD

Product change: `lead_engine/dashboard_static/index.html` only.
No backend changes. No protected systems touched.

### Problem addressed

`_mrpResolveRow` — the only bridge between Discovery map `biz` objects and
Pipeline queue rows — relied entirely on fuzzy name+city string matching.
Website (present on 90% of rows) and phone (99%) were completely unused,
even though both are stable identifiers with zero collision in the live queue.

### Changes

**`_leadKeyIndex` module var** (line ~1458)
- `let _leadKeyIndex = new Map()` — initialized empty, rebuilt on every `loadAll`.

**`_buildLeadKeyIndex(rows)`** (line ~5714)
- Iterates `allRows`, calls `_leadKey(row)` on each, inserts into the Map.
- `_leadKey` priority: website → phone → name+city (same as Pass 39).
- First-occurrence wins on any key collision. In practice: zero collisions
  confirmed against live queue (162 unique websites, 179 unique phones, 180 unique name+city).
- Returns the populated Map and also sets `_leadKeyIndex`.

**Wired into `loadAll()`** (line ~1826)
- `_buildLeadKeyIndex(allRows)` called immediately after `allRows = Array.isArray(queue) ? queue : []`.
- Index is fresh on every queue refresh, discovery load, approve, schedule, delete, etc.

**`_mrpResolveRow(biz)` rewrite** (line ~5726)
- Layer 1 (new): `_leadKeyIndex.get(_leadKey(biz))` — O(1) exact lookup via
  stable key. Succeeds for ~90% of biz objects that have a website.
- Layer 2 (preserved): name+city composite scan — catches legacy rows where
  website/phone normalisation differs from what the biz object carries.
- Layer 3 (preserved): name-only scan — original fallback, least reliable,
  retained for full backward compatibility.
- All existing `_mrpResolveRow` call sites are unchanged.

### Identity matching: exact vs fallback

| Key type | Coverage | Match type | Collisions |
|---|---|---|---|
| website (normalized) | 90% of queue rows | Exact O(1) | 0 |
| phone (digits only) | 99% of queue rows | Exact O(1) | 0 |
| name+city | 100% of queue rows | Exact O(1) via index, linear scan fallback | 0 |
| name-only | 100% (last resort) | Linear scan | Possible for common names |

### What remains fuzzy on purpose

- Name-only last resort (Layer 3) — preserved for compat with legacy callers
  like `_mrpFindQueueRow(bizName)` that have no city context.
- `_mrpFindQueueRow` shim is unchanged — still delegates to `_mrpResolveRow`
  with a synthetic `{ name: bizName, city: '' }` biz object.

### Verification

- `node --check` on extracted dashboard JS: clean.
- `python -c "import dashboard_server"` import: clean.
- All 4 change sites confirmed via targeted search.
- Live queue inspection: 0 website collisions, 0 phone collisions across 180 rows.

---

"""

old_hdr = "## Active System\nV2 Stage 2C — Shared Row State Rendering\n\n## Status\nPass 40 complete.\n\n---\n\n"
if old_hdr in build_src:
    build_src = build_src.replace(old_hdr, P41_BLOCK, 1)
    print("  BUILD header replaced")
else:
    build_src = P41_BLOCK + build_src
    print("  BUILD prepended (header not matched)")

with open(BUILD, "w", encoding="utf-8") as f:
    f.write(build_src)

# ── AI_CONTROL_PANEL ──────────────────────────────────────────────────────────
swap(PANEL,
    "## Current Build Pass\nPass 40 - V2 Stage 2C — Shared Row State Rendering (complete)",
    "## Current Build Pass\nPass 41 - V2 Stage 2D — Stable Key Propagation (complete)"
)
swap(PANEL,
    "## Last Completed Pass\nPass 40 - V2 Stage 2C — Shared Row State Rendering\n\nCommit: `8abbb57`",
    "## Last Completed Pass\nPass 41 - V2 Stage 2D — Stable Key Propagation\n\nCommit: TBD"
)

# ── CHANGELOG ─────────────────────────────────────────────────────────────────
P41_LOG = """### 2026-03-17 - Pass 41: V2 Stage 2D — Stable Key Propagation + Stronger Discovery-Queue Linking

**Goal:** Replace `_mrpResolveRow`'s fuzzy name+city scan with a stable key-indexed lookup. Website (90% coverage, 0 collisions) and phone (99%, 0 collisions) are now the primary match signals.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**
- `_leadKeyIndex = new Map()` module var added alongside `allRows`.
- `_buildLeadKeyIndex(rows)` function: builds Map from `_leadKey(row)` for all rows. Called in `loadAll()` after `allRows` assignment.
- `_mrpResolveRow(biz)` rewritten: Layer 1 = `_leadKeyIndex.get(_leadKey(biz))` exact lookup; Layer 2 = name+city scan fallback; Layer 3 = name-only last resort (compat preserved).

**No backend changes. No queue schema changes. No protected systems touched.**
All `_mrpResolveRow` call sites unchanged.

**Commit:** TBD

---

"""
prepend_entry(CHLOG, P41_LOG, "### 2026-03-17 - Pass 40:")

print("\nDone.")
