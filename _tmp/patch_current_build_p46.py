from pathlib import Path

p = Path(r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CURRENT_BUILD.md')
original = p.read_text(encoding='utf-8')

new_header = """# Current Build Pass

## Active System
Pass 46 -- Contacted Memory Seeding + Safer Contact Recording

## Status
Pass 46 complete.

---

## Completed: Pass 46 -- Contacted Memory Seeding + Safer Contact Recording -- `65d113e`

Product changes across three files:
- `lead_engine/scripts/seed_contacted_memory.py` (new)
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

No protected systems touched. No queue schema changes.

### Problem addressed

34 businesses had been genuinely contacted via outreach but were absent from
lead_memory.json. They could resurface in discovery, be re-drafted, and be
re-contacted. There was also no automatic path to record future contact events
in memory, and no easy way for an operator to manually mark an unsent row as
contacted without going through the full send flow.

### seed_contacted_memory.py (new)

Read-only against the queue CSV. Writes only to lead_memory.json.

- Uses `is_real_send()` as the authoritative gate: 34 rows with confirmed
  message_id are seeded; 16 rows with sent_at but no message_id (logged-only,
  unconfirmed sends) are intentionally excluded.
- Records each as `contacted` with note including sent_at and message_id prefix.
- Idempotent: skips any row already in memory (preserves do_not_contact, hold, etc.).
- Dry-run by default; `--write` to commit.
- Executed: 34/34 seeded, all with `web:` identity keys, 0 skipped.

### dashboard_server.py

`api_log_contact` -- one additive block:
- When `result == 'sent'`, calls `_lm.record_suppression(row, 'contacted')`.
- Wrapped in try/except -- memory failure never blocks the contact log operation.
- This is the correct forward-looking hook: the log_contact endpoint is the
  manual contact surface; send_approved is adjacent to protected systems.

### index.html

- 'Mark Contacted' button added to panel footer (`id=panel-mark-contacted-btn`).
  Starts hidden (`display:none`). Hidden when `row.sent_at` is already set.
  Shown for unsent rows where the operator wants to record off-queue contact.
- `fillPanel` visibility block updated to toggle it alongside approve/schedule buttons.
- `panelMarkContacted()` function: calls `/api/suppress_lead` with `state='contacted'`.
  Hides the button on success. Toasts confirmation.

### What this achieves

| Path | When | State recorded |
|---|---|---|
| Seed script | One-shot backfill | `contacted` x34 |
| `api_log_contact` result=sent | Every future manual contact log | `contacted` |
| Panel 'Mark Contacted' | Manual marking for unsent rows | `contacted` |

### Verification

- `python -c "import dashboard_server"` import: clean.
- `node --check` on extracted JS: clean.
- 6/6 checks passed: is_real_send count correct, seeded row suppressed,
  skip-existing logic, log_contact hook, panelMarkContacted path,
  real memory file has 34 contacted records all web: keyed.

---

"""

# Find anchor for the existing Pass 45 entry
anchor = '## Completed: Pass 45'
idx = original.find(anchor)
if idx == -1:
    print('ERROR: could not find Pass 45 anchor')
else:
    new_content = new_header + original[idx:]
    p.write_text(new_content, encoding='utf-8')
    print(f'Written {len(new_content):,} chars, {new_content.count(chr(10))} lines')
