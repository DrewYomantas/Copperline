"""
Pass 40 — V2 Stage 2C: Shared Row State Rendering

Changes:
1. Add _leadStatusPills(record) — shared pill HTML from _leadRecord
2. Add _leadNextActionHint(record) — shared next-action hint HTML
3. Replace both inline mrp-status-pills blocks with _leadStatusPills calls
4. Add _leadNextActionHint into both map list renders
5. Add observation tag + next-action hint into statusCellHtml sub-line
"""
import re

PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

original_len = len(src)
changes = []

# ─────────────────────────────────────────────────────────────────────────────
# 1. Inject shared helpers after _renderLeadWorkspaceHeader closing brace
# ─────────────────────────────────────────────────────────────────────────────

HELPERS = """
// ═══════════════════════════════════════════════════════════════════════════
// V2 Stage 2C — Shared Row State Rendering Helpers
// _leadStatusPills and _leadNextActionHint reduce duplicated inline logic
// across _mapRenderPanel (both render paths) and statusCellHtml.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * _leadStatusPills(record) — returns innerHTML string for a .mrp-status-pills div.
 * Renders: status pill (using mrp-pill CSS classes), score pill, observation tag.
 * Replaces the inline isSent/isApproved/isScheduled/score blocks in both
 * _mapRenderPanel render paths.
 */
function _leadStatusPills(record) {
  if (!record) return '';
  const r = record;
  // Map statusTone to mrp-pill CSS class
  const toneToClass = {
    replied:   'sent',       // reuse sent styling for replied in pills
    sent:      'sent',
    scheduled: 'scheduled',
    approved:  'approved',
    drafted:   'drafted',
    new:       'drafted',
    blocked:   'drafted',
  };
  const pillClass = toneToClass[r.statusTone] || 'drafted';
  let html = `<span class="mrp-pill ${pillClass}">${r.status}</span>`;
  if (r.priorityScore) {
    html += `<span class="mrp-pill score">Score ${r.priorityScore}</span>`;
  }
  if (r.observation) {
    html += `<span class="mrp-pill" style="background:rgba(184,115,51,.12);color:var(--copper);border:1px solid rgba(184,115,51,.2)" title="${r.observation.substring(0, 80).replace(/"/g, '&quot;')}">obs</span>`;
  }
  return html;
}

/**
 * _leadNextActionHint(record) — returns a compact HTML string with the next
 * recommended action from _leadRecord. Empty string if no action.
 * Used in map list items and queue table status cells.
 */
function _leadNextActionHint(record) {
  if (!record || !record.nextAction) return '';
  return `<div style="font-size:9px;color:var(--muted);margin-top:2px;line-height:1.3">` +
         `<span style="color:var(--dim)">Next:</span> ` +
         `<span style="color:var(--text);font-weight:500">${record.nextAction}</span></div>`;
}
"""

HELPERS_ANCHOR = "function _panelMakeKey(row) {"
if HELPERS_ANCHOR in src:
    src = src.replace(HELPERS_ANCHOR, HELPERS + HELPERS_ANCHOR, 1)
    changes.append("Shared helpers _leadStatusPills + _leadNextActionHint injected")
else:
    print("WARNING: _panelMakeKey anchor not found for helper injection")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Replace first mrp-status-pills block (simple _mapRenderPanel render)
#    The exact inline block reads biz+qrow locally and builds pills.
# ─────────────────────────────────────────────────────────────────────────────

OLD_PILLS_1 = re.compile(
    r"(    // Queue state pills\n"
    r"    if \(qrow\) \{\n)"
    r"(      const pillsDiv = document\.createElement\('div'\);\n"
    r"      pillsDiv\.className = 'mrp-status-pills';\n"
    r"      const isSent     = !!\(qrow\.sent_at \|\| ''\)\.trim\(\);\n"
    r"      const isApproved = \(qrow\.approved \|\| ''\)\.toLowerCase\(\) === 'true';\n"
    r"      const isScheduled = !!\(qrow\.send_after \|\| ''\)\.trim\(\) && !isSent;\n"
    r"      const score      = parseInt\(qrow\.final_priority_score\) \|\| 0;\n"
    r"      if \(isSent\)      pillsDiv\.innerHTML \+= `<span class=\"mrp-pill sent\">Sent</span>`;\n"
    r"      else if \(isScheduled\) pillsDiv\.innerHTML \+= `<span class=\"mrp-pill scheduled\">Scheduled</span>`;\n"
    r"      else if \(isApproved\) pillsDiv\.innerHTML \+= `<span class=\"mrp-pill approved\">Approved</span>`;\n"
    r"      else             pillsDiv\.innerHTML \+= `<span class=\"mrp-pill drafted\">Drafted</span>`;\n"
    r"      if \(score\)       pillsDiv\.innerHTML \+= `<span class=\"mrp-pill score\">Score \$\{score\}</span>`;\n"
    r"      item\.appendChild\(pillsDiv\);\n)",
    re.DOTALL
)
NEW_PILLS_1 = (
    r"    // Queue state pills (V2 Stage 2C: via _leadStatusPills)\n"
    r"    if (qrow) {\n"
    r"      const _lrSimple = _leadRecord(qrow);\n"
    r"      const isSent     = _lrSimple.isSent;\n"
    r"      const isApproved = _lrSimple.isApproved;\n"
    r"      const isScheduled = _lrSimple.isScheduled;\n"
    r"      const score      = _lrSimple.priorityScore;\n"
    r"      const pillsDiv = document.createElement('div');\n"
    r"      pillsDiv.className = 'mrp-status-pills';\n"
    r"      pillsDiv.innerHTML = _leadStatusPills(_lrSimple);\n"
    r"      item.appendChild(pillsDiv);\n"
    r"      const hintDiv = document.createElement('div');\n"
    r"      hintDiv.innerHTML = _leadNextActionHint(_lrSimple);\n"
    r"      if (hintDiv.innerHTML) item.appendChild(hintDiv);\n"
)
if OLD_PILLS_1.search(src):
    src = OLD_PILLS_1.sub(NEW_PILLS_1, src, count=1)
    changes.append("First mrp-status-pills block replaced with _leadStatusPills + next-action hint")
else:
    print("WARNING: first mrp-status-pills block not matched")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Replace second mrp-status-pills block (triage _mapRenderPanel render)
# ─────────────────────────────────────────────────────────────────────────────

OLD_PILLS_2 = re.compile(
    r"(      if \(qrow\) \{\n)"
    r"        const pillsDiv = document\.createElement\('div'\);\n"
    r"        pillsDiv\.className = 'mrp-status-pills';\n"
    r"        const isSent = !!\(qrow\.sent_at \|\| ''\)\.trim\(\);\n"
    r"        const isApproved = String\(qrow\.approved \|\| ''\)\.toLowerCase\(\) === 'true';\n"
    r"        const isScheduled = !!\(qrow\.send_after \|\| ''\)\.trim\(\) && !isSent;\n"
    r"        const score = _mapPanelItemScore\(item, qrow\);\n"
    r"        if \(isSent\) pillsDiv\.innerHTML \+= `<span class=\"mrp-pill sent\">Sent</span>`;\n"
    r"        else if \(isScheduled\) pillsDiv\.innerHTML \+= `<span class=\"mrp-pill scheduled\">Scheduled</span>`;\n"
    r"        else if \(isApproved\) pillsDiv\.innerHTML \+= `<span class=\"mrp-pill approved\">Approved</span>`;\n"
    r"        else pillsDiv\.innerHTML \+= `<span class=\"mrp-pill drafted\">Drafted</span>`;\n"
    r"        if \(score\) pillsDiv\.innerHTML \+= `<span class=\"mrp-pill score\">Score \$\{score\}</span>`;\n"
    r"        itemEl\.appendChild\(pillsDiv\);\n",
    re.DOTALL
)
NEW_PILLS_2 = (
    r"\1"
    r"        // V2 Stage 2C: via _leadStatusPills\n"
    r"        const _lrTriage = _leadRecord(qrow);\n"
    r"        const isSent = _lrTriage.isSent;\n"
    r"        const isApproved = _lrTriage.isApproved;\n"
    r"        const isScheduled = _lrTriage.isScheduled;\n"
    r"        const score = _lrTriage.priorityScore;\n"
    r"        const pillsDiv = document.createElement('div');\n"
    r"        pillsDiv.className = 'mrp-status-pills';\n"
    r"        pillsDiv.innerHTML = _leadStatusPills(_lrTriage);\n"
    r"        itemEl.appendChild(pillsDiv);\n"
    r"        const triageHintDiv = document.createElement('div');\n"
    r"        triageHintDiv.innerHTML = _leadNextActionHint(_lrTriage);\n"
    r"        if (triageHintDiv.innerHTML) itemEl.appendChild(triageHintDiv);\n"
)
if OLD_PILLS_2.search(src):
    src = OLD_PILLS_2.sub(NEW_PILLS_2, src, count=1)
    changes.append("Second mrp-status-pills block (triage render) replaced")
else:
    print("WARNING: second mrp-status-pills block not matched")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Add observation tag + next-action hint into statusCellHtml sub-line
#    statusCellHtml calls _queueStateMeta(row) and builds the cell.
#    We inject _leadRecord(row) to add obs tag and next-action to the subline.
# ─────────────────────────────────────────────────────────────────────────────

OLD_STATUS_CELL = re.compile(
    r"(function statusCellHtml\(row\) \{\s*\n"
    r"  const meta = _queueStateMeta\(row\);)",
    re.DOTALL
)
NEW_STATUS_CELL = (
    r"function statusCellHtml(row) {\n"
    r"  const meta = _queueStateMeta(row);\n"
    r"  // V2 Stage 2C: unified record for obs tag + next-action\n"
    r"  const _scRecord = _leadRecord(row);"
)
if OLD_STATUS_CELL.search(src):
    src = OLD_STATUS_CELL.sub(NEW_STATUS_CELL, src, count=1)
    changes.append("statusCellHtml: _leadRecord injected")
else:
    print("WARNING: statusCellHtml opening not matched")

# Now find the subline in statusCellHtml where the detail text renders
# and append the obs/next-action info. Look for the detail/subline construction.
OLD_SUBLINE = re.compile(
    r"(  let subline = meta\.detail \|\| '';)",
    re.DOTALL
)
NEW_SUBLINE = (
    r"  let subline = meta.detail || '';\n"
    r"  // V2 Stage 2C: append obs tag + next-action to subline\n"
    r"  if (_scRecord.observation) subline += (subline ? ' · ' : '') + 'obs';\n"
    r"  if (_scRecord.nextAction && !_scRecord.isSent) "
    r"subline += (subline ? ' · ' : '') + _scRecord.nextAction;"
)
if OLD_SUBLINE.search(src):
    src = OLD_SUBLINE.sub(NEW_SUBLINE, src, count=1)
    changes.append("statusCellHtml: obs tag + next-action appended to subline")
else:
    # Fallback: find where subline is used in the return and inject differently
    print("INFO: 'let subline' pattern not found — trying statusCellHtml return injection")
    # Look for the detail line in the cell HTML
    OLD_DETAIL = re.compile(
        r'(  const detailHtml = meta\.detail\s*\n    \? `<div class="status-detail">[^`]+`\s*\n    : ``;)',
        re.DOTALL
    )
    if OLD_DETAIL.search(src):
        print("  Found detailHtml pattern")
    else:
        print("  statusCellHtml detail pattern also not found — skipping subline injection")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Write
# ─────────────────────────────────────────────────────────────────────────────

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\n{len(changes)}/5 target changes applied:")
for c in changes:
    print(f"  + {c}")
print(f"File: {original_len} -> {len(src)} chars (+{len(src)-original_len})")
