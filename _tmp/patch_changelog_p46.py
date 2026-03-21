from pathlib import Path

p = Path(r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CHANGELOG_AI.md')
original = p.read_text(encoding='utf-8')

new_entry = """
### 2026-03-18 - Pass 46: Contacted Memory Seeding + Safer Contact Recording

**Goal:** Backfill lead_memory with existing contacted leads, and ensure all future
contact events are recorded automatically with minimal operator friction.

**Files changed:**
- `lead_engine/scripts/seed_contacted_memory.py` (new)
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/CHANGELOG_AI.md`

**What changed:**

`scripts/seed_contacted_memory.py` (new):
- One-shot idempotent seed script for existing real-sent queue rows.
- Uses `is_real_send()` as gate: 34 rows with confirmed message_id seeded,
  16 logged-only rows (no message_id) intentionally excluded.
- Skips rows already in memory — preserves existing states (do_not_contact, hold, etc.).
- Dry-run by default; `--write` flag to commit to `lead_memory.json`.
- Executed: 34/34 seeded, all with `web:` identity keys, 0 skipped.

`dashboard_server.py`:
- `api_log_contact`: when `result == 'sent'`, calls `_lm.record_suppression(row, 'contacted')`.
  Wrapped in try/except — memory failure never blocks the contact log operation.
  Forward-looking: all future manual contact logs auto-record to memory.

`index.html`:
- 'Mark Contacted' button added to panel footer (`id=panel-mark-contacted-btn`).
  Hidden (`display:none`) for rows where `sent_at` is already set; visible for unsent rows.
- `fillPanel` visibility block updated to toggle the button alongside approve/schedule.
- `panelMarkContacted()` JS function: calls `/api/suppress_lead` with `state='contacted'`.
  Hides itself on success, shows confirmation toast.

**Design decisions:**
- Seed uses `is_real_send()` not just `sent_at`: 16 rows have `sent_at` but no `message_id`
  (logged-only, unconfirmed sends). These are intentionally excluded from the seed.
- `api_log_contact` hook chosen over `api_send_approved`: the log_contact endpoint is the
  correct manual contact surface; the send_approved path is adjacent to protected systems.
- Button hidden for already-sent rows: prevents confusion and double-recording.

**No protected systems touched. No queue schema changes.**

**Verification:**
- `python -c "import dashboard_server"` clean.
- `node --check` on extracted JS clean.
- 6/6 checks passed: is_real_send count, contacted suppression, skip-existing logic,
  api_log_contact hook, panelMarkContacted path, real memory file integrity.

**Commit:** `65d113e`

---

"""

# Insert before the first existing Pass 45 entry
anchor = '### 2026-03-18 - Pass 45:'
idx = original.find(anchor)
if idx == -1:
    # fallback: insert at very start after BOM
    new_content = new_entry.lstrip('\n') + original
else:
    new_content = original[:idx] + new_entry.lstrip('\n') + original[idx:]

p.write_text(new_content, encoding='utf-8')
print(f'Written {len(new_content):,} chars')
