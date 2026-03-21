"""
Pass 41 — V2 Stage 2D: Stable Key Propagation + Stronger Discovery<->Queue Linking

Changes:
1. Add _leadKeyIndex module var after allRows declaration
2. Add _buildLeadKeyIndex(rows) function near allRows initialization
3. Wire _buildLeadKeyIndex into loadAll after allRows = ...
4. Rewrite _mrpResolveRow to use key-index first, fuzzy fallback second
"""
import re

PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

original_len = len(src)
changes = []

# ─────────────────────────────────────────────────────────────────────────────
# 1. Add _leadKeyIndex var declaration next to allRows
# ─────────────────────────────────────────────────────────────────────────────

OLD_VAR = "let allRows = [];"
NEW_VAR = (
    "let allRows = [];\n"
    "let _leadKeyIndex = new Map(); // Pass 41: stable-key index for _mrpResolveRow"
)
if OLD_VAR in src:
    src = src.replace(OLD_VAR, NEW_VAR, 1)
    changes.append("_leadKeyIndex var added next to allRows")
else:
    print("WARNING: 'let allRows = [];' not found")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Add _buildLeadKeyIndex function
#    Inject it immediately before _mrpResolveRow (they're related, natural home)
# ─────────────────────────────────────────────────────────────────────────────

BUILD_INDEX_FN = """
// ── Pass 41: stable key index ────────────────────────────────────────────────
// Pre-indexes allRows by _leadKey so _mrpResolveRow can do O(1) exact-key
// lookup instead of sequential fuzzy scan. Rebuilt every time allRows changes.
function _buildLeadKeyIndex(rows) {
  const idx = new Map();
  if (!Array.isArray(rows)) return idx;
  for (const row of rows) {
    const k = _leadKey(row);
    if (k && !idx.has(k)) idx.set(k, row); // first occurrence wins on collision
  }
  _leadKeyIndex = idx;
  return idx;
}

"""

# Inject just before "function _mrpResolveRow(biz) {"
ANCHOR_RESOLVE = "function _mrpResolveRow(biz) {"
if ANCHOR_RESOLVE in src:
    src = src.replace(ANCHOR_RESOLVE, BUILD_INDEX_FN + ANCHOR_RESOLVE, 1)
    changes.append("_buildLeadKeyIndex function injected before _mrpResolveRow")
else:
    print("WARNING: 'function _mrpResolveRow(biz) {' anchor not found")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Wire _buildLeadKeyIndex into loadAll after allRows is assigned
# ─────────────────────────────────────────────────────────────────────────────

OLD_ALLROWS_ASSIGN = (
    "    allRows = Array.isArray(queue) ? queue : [];\n"
    "    if (!Array.isArray(queue)) console.error('Queue API returned non-array:', queue);"
)
NEW_ALLROWS_ASSIGN = (
    "    allRows = Array.isArray(queue) ? queue : [];\n"
    "    if (!Array.isArray(queue)) console.error('Queue API returned non-array:', queue);\n"
    "    _buildLeadKeyIndex(allRows); // Pass 41: rebuild stable-key index"
)
if OLD_ALLROWS_ASSIGN in src:
    src = src.replace(OLD_ALLROWS_ASSIGN, NEW_ALLROWS_ASSIGN, 1)
    changes.append("_buildLeadKeyIndex wired into loadAll after allRows assignment")
else:
    print("WARNING: allRows assignment block not found exactly — trying partial match")
    OLD_PARTIAL = "    allRows = Array.isArray(queue) ? queue : [];"
    if OLD_PARTIAL in src:
        src = src.replace(
            OLD_PARTIAL,
            OLD_PARTIAL + "\n    _buildLeadKeyIndex(allRows); // Pass 41: rebuild stable-key index",
            1
        )
        changes.append("_buildLeadKeyIndex wired into loadAll (partial match)")
    else:
        print("WARNING: allRows assignment not found — index not wired")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Rewrite _mrpResolveRow body
#    Old: stub place_id comment + name+city scan + name-only fallback
#    New: _leadKey exact lookup + name+city fallback for legacy rows with no stable key
# ─────────────────────────────────────────────────────────────────────────────

OLD_RESOLVE_BODY = re.compile(
    r"(function _mrpResolveRow\(biz\) \{)\s*"
    r"if \(!biz \|\| !allRows \|\| !allRows\.length\) return null;.*?"
    r"  return null;\s*\}",
    re.DOTALL
)

NEW_RESOLVE_BODY = r"""\1
  // Pass 41: key-index first, fuzzy fallback for legacy rows
  if (!biz || !allRows || !allRows.length) return null;

  // 1. Exact stable-key lookup via _leadKey (website → phone → name+city)
  //    This is O(1) and works for 90-99% of rows that have website or phone.
  const stableKey = _leadKey(biz);
  if (stableKey && _leadKeyIndex.size > 0) {
    const hit = _leadKeyIndex.get(stableKey);
    if (hit) return hit;
  }

  // 2. Name+city scan fallback — handles legacy rows where stable key produces
  //    different normalizations (e.g. website URL format changed, phone stripped).
  const nameKey = (biz.name || '').trim().toLowerCase();
  const cityKey = (biz.city || '').trim().toLowerCase();
  if (nameKey && cityKey) {
    const hit = allRows.find(r =>
      (r.business_name || '').trim().toLowerCase() === nameKey &&
      (r.city || '').trim().toLowerCase() === cityKey
    );
    if (hit) return hit;
  }

  // 3. Name-only last resort (original behaviour — least reliable, preserved for compat)
  if (nameKey) {
    return allRows.find(r => (r.business_name || '').trim().toLowerCase() === nameKey) || null;
  }
  return null;
}"""

if OLD_RESOLVE_BODY.search(src):
    src = OLD_RESOLVE_BODY.sub(NEW_RESOLVE_BODY, src, count=1)
    changes.append("_mrpResolveRow rewritten: key-index lookup + name+city fallback + name-only last resort")
else:
    print("WARNING: _mrpResolveRow body pattern not matched")

# ─────────────────────────────────────────────────────────────────────────────
# Write
# ─────────────────────────────────────────────────────────────────────────────

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\n{len(changes)}/4 changes applied:")
for c in changes:
    print(f"  + {c}")
print(f"File: {original_len} -> {len(src)} chars (+{len(src)-original_len})")
