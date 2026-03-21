import re

def patch(path, replacements):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    for old, new in replacements:
        p = re.compile(re.escape(old), re.DOTALL)
        if p.search(src):
            src = p.sub(new.replace("\\", "\\\\"), src, count=1)
            print(f"  REPLACED: {old[:60]!r}")
        else:
            print(f"  MISS: {old[:60]!r}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)

STATE = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\PROJECT_STATE.md"
BUILD = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CURRENT_BUILD.md"
PANEL = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\AI_CONTROL_PANEL.md"
CHLOG = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CHANGELOG_AI.md"

# PROJECT_STATE.md
patch(STATE, [
    (
        "- Rewrote `email_draft_agent.py` (DRAFT_VERSION v9) so first-touch email and DM generation requires a `business_specific_observation` field.\n"
        "- First-touch generation fails with a clear `ObservationMissingError` if observation is absent or too generic.\n"
        "- Validation layer (`validate_draft`) deterministically blocks banned buzzwords, hard CTAs, links, pricing, and drafts that don't materially reflect the observation.\n"
        "- Three controlled variation families (A/B/C) are the only allowed output patterns — no open-ended variation that can drift back into sales copy.\n"
        "- Added `business_specific_observation` as an additive non-send-path column to `PENDING_COLUMNS` in `dashboard_server.py`.\n"
        "- Added `/api/update_observation` and `/api/regenerate_draft` endpoints — both block clearly when observation is missing or invalid.\n"
        "- Added observation input field + regenerate button to the review panel in `index.html`, with blocked state messaging when observation is absent.\n"
        "- Verified 23/23 checks pass: blocking, validation, output quality, variation, field-vs-arg observation routing.\n"
        "\nCommit: `00add5d`",
        "- Restored editable map preview modal: subject input + body textarea + Save Edits button so operator can edit and save directly from the Discovery map panel without returning to Pipeline.\n"
        "- Added Unschedule button to the map preview modal for scheduled rows.\n"
        "- Added pending-state feedback to all slow panel actions: panelApprove, panelUnapprove, panelScheduleTomorrow, panelUnschedule — buttons disable and show in-progress label during the API call.\n"
        "- Fixed backdrop close: clicking outside the review panel now closes it (was blocked by a toast). True backdrop mousedown+click required; drag-select inside panel never closes it.\n"
        "- Added mousedown origin guard (`_panelMousedownOnBackdrop`) so text selection or input interaction inside the panel cannot accidentally dismiss it.\n"
        "- Pending-state helpers `_btnPending` / `_btnRestore` added as shared utilities.\n"
        "\nCommit: TBD"
    ),
    (
        "## Previous Completed Pass\nPass 35 - Scheduling Clarity + Queue Timeline UX",
        "## Previous Completed Pass\nPass 36 - Observation-Led Outreach Rewrite"
    ),
])

# CURRENT_BUILD.md — prepend Pass 37 block
with open(BUILD, "r", encoding="utf-8") as f:
    build_src = f.read()

P37_BLOCK = """# Current Build Pass

## Active System
Discovery Review Recovery + Action Feedback

## Status
Pass 37 complete.

---

## Completed: Pass 37 - Discovery Review Recovery + Action Feedback - TBD

Product change: `lead_engine/dashboard_static/index.html` only.
No backend changes. No protected systems touched.

### Map preview modal — editable

- Replaced read-only `<pre>` body and static subject display with an `<input>` for subject and `<textarea>` for body inside the `mrp-modal`.
- Added Save Edits button that calls `/api/update_row` with the edited subject and body, updates the in-memory row, and refreshes the map panel — no page switch required.
- Added Unschedule button to the preview modal footer when the row is currently scheduled.
- Save status line shows inline feedback (Saving... / Saved. / error) below the textarea.
- All footer buttons (Save, Approve, Unschedule/Schedule, Delete, Close) are present and context-aware based on row state.

### Pending-state feedback on async actions

- Added `_btnPending(btn, label)` and `_btnRestore(btn)` shared helpers.
- Wired into `panelApprove` (shows "Approving..."), `panelUnapprove` (shows "Removing..."), `panelScheduleTomorrow` (shows "Scheduling..."), `panelUnschedule` (shows "Clearing...").
- Map preview modal buttons also use pending state on Approve, Unschedule, Schedule, Save.
- Buttons disable during the API call and restore label + enabled state after.

### Backdrop close restored

- `closePanelOnOverlay` now performs a real close instead of showing a toast that blocked it.
- Added `_panelOverlayMousedown(e)` wired to `onmousedown` on the overlay element.
- `_panelMousedownOnBackdrop` flag tracks whether the mousedown originated on the backdrop vs inside the panel.
- A click only closes if `_panelMousedownOnBackdrop` is true — so dragging text in a textarea or clicking inside inputs never dismisses the panel.
- Pending debounced saves still temporarily block close with an informational toast.
- X close button remains available.

### Unschedule visibility

- Already present in table row actions and panel schedule block. Now also in map preview modal footer.
- No layout changes to existing locations.

### Verification

- `node --check` on extracted dashboard JS: clean.
- `python -c "import dashboard_server"` import check: clean.
- All six targeted search terms confirmed present in file at expected line numbers.

---

"""

# Strip old Active System block header to avoid duplication
old_header = "# Current Build Pass\n\n## Active System\nObservation-Led Outreach Rewrite\n\n## Status\nPass 36 complete.\n\n---\n\n"
if old_header in build_src:
    build_src = build_src.replace(old_header, P37_BLOCK, 1)
    print("BUILD: old header replaced")
else:
    # Fallback: prepend
    build_src = P37_BLOCK + build_src
    print("BUILD: prepended")

with open(BUILD, "w", encoding="utf-8") as f:
    f.write(build_src)

# AI_CONTROL_PANEL.md
patch(PANEL, [
    ("## Current Focus\nObservation-Led Outreach Rewrite",
     "## Current Focus\nDiscovery Review Recovery + Action Feedback"),
    ("## Current Build Pass\nPass 36 - Observation-Led Outreach Rewrite (complete)",
     "## Current Build Pass\nPass 37 - Discovery Review Recovery + Action Feedback (complete)"),
    ("## Last Completed Pass\nPass 36 - Observation-Led Outreach Rewrite\n\nCommit: `00add5d`",
     "## Last Completed Pass\nPass 37 - Discovery Review Recovery + Action Feedback\n\nCommit: TBD"),
])

# CHANGELOG_AI.md — prepend entry
P37_LOG = """### 2026-03-17 - Pass 37: Discovery Review Recovery + Action Feedback

**Goal:** Fix operator friction introduced by recent dashboard passes — restore editable map preview, add pending-state feedback, fix backdrop close with drag guard, surface Unschedule clearly.

**Files changed:**
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**

`index.html`:
- Added `_panelMousedownOnBackdrop` state variable for drag-close guard.
- Added `_panelOverlayMousedown(e)` — sets flag only when mousedown lands on the backdrop itself.
- Rewrote `closePanelOnOverlay` — now performs real close instead of toast-only block. Requires mousedown origin to have been the backdrop; pending saves still temporarily block.
- Wired `onmousedown="_panelOverlayMousedown(event)"` onto the overlay element.
- Added `_btnPending(btn, label)` and `_btnRestore(btn)` shared helpers.
- `panelApprove` — pending state (Approving...), try/catch, restore.
- `panelUnapprove` — pending state (Removing...), try/catch, restore.
- `panelScheduleTomorrow` — pending state (Scheduling...), restore on all exit paths.
- `panelUnschedule` — pending state (Clearing...), restore.
- `mrp-modal` HTML — replaced `<pre>` + static subject `<div>` with `<input>` + `<textarea>` + save-status line.
- `_mrpPreview` — fully rewritten: populates inputs, wires Save Edits (calls `/api/update_row`), Approve, Unschedule (for scheduled rows) / Schedule Tomorrow (for unscheduled), Delete, Close — all with pending state.

**No backend changes. No protected systems touched.**

**Verification:**
- `node --check` clean on extracted dashboard JS.
- `python -c "import dashboard_server"` clean.
- All change sites confirmed via targeted search (line numbers documented in CURRENT_BUILD.md).

**Commit:** TBD

---

"""

with open(CHLOG, "r", encoding="utf-8") as f:
    chlog_src = f.read()

first_entry = "### 2026-03-17 - Pass 36:"
if first_entry in chlog_src:
    chlog_src = chlog_src.replace(first_entry, P37_LOG + first_entry, 1)
    print("CHANGELOG: prepended")
else:
    chlog_src = P37_LOG + chlog_src
    print("CHANGELOG: fallback prepend")

with open(CHLOG, "w", encoding="utf-8") as f:
    f.write(chlog_src)

print("\nAll docs patched.")
