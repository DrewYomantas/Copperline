from pathlib import Path

p = Path(r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\docs\CURRENT_BUILD.md')
original = p.read_text(encoding='utf-8')
lines = original.splitlines(keepends=True)

new_header_lines = [
    "# Current Build Pass\n",
    "\n",
    "## Active System\n",
    "Pass 45 -- Durable Memory Coverage Hardening\n",
    "\n",
    "## Status\n",
    "Pass 45 complete.\n",
    "\n",
    "---\n",
    "\n",
    "## Completed: Pass 45 -- Durable Memory Coverage Hardening -- `e7c382c`\n",
    "\n",
    "Product change: `lead_engine/dashboard_server.py` only.\n",
    "No frontend changes. No protected systems touched. No queue schema changes.\n",
    "\n",
    "### Problem addressed\n",
    "\n",
    "Pass 44 introduced suppression filtering in `api_discover_area` (map-area single call),\n",
    "but `api_discover` (city-based) and `api_discover_area_batch` (exhaust mode) had no\n",
    "suppression awareness. A suppressed lead could still be re-drafted via either route.\n",
    "\n",
    "### Changes\n",
    "\n",
    "`api_discover`: reads `include_suppressed` from POST body (default False). Filters rows\n",
    "through `_lm.is_suppressed(r)` before `run_pipeline`. Returns `suppressed_skipped` count.\n",
    "New `all_suppressed` response when every discovered row is suppressed.\n",
    "\n",
    "`api_discover_area_batch`: reads `include_suppressed` from POST body (default False).\n",
    "Per-iteration row-by-row check. Each marker carries `suppressed` flag. Accumulates\n",
    "`total_suppressed_skipped` across all iterations. Returns field in final response.\n",
    "\n",
    "### Suppression coverage -- complete as of Pass 45\n",
    "\n",
    "| Route | Where filtered | Override param |\n",
    "|---|---|---|\n",
    "| POST /api/discover | Before run_pipeline | include_suppressed in body |\n",
    "| POST /api/discover_area | Marker list (Pass 44) | include_suppressed query param |\n",
    "| POST /api/discover_area_batch | Per-iteration markers | include_suppressed in body |\n",
    "\n",
    "### Verification\n",
    "\n",
    "- `python -c \"import dashboard_server\"` import: clean.\n",
    "- 4/4 logic checks passed.\n",
    "\n",
    "---\n",
    "\n",
]

# Find anchor: first line containing '## Completed: Pass 43'
body_start = None
for i, line in enumerate(lines):
    if '## Completed: Pass 43' in line:
        body_start = i
        break

if body_start is None:
    # fallback: find Pass 44 entry
    for i, line in enumerate(lines):
        if '## Completed: Pass 44' in line:
            body_start = i
            break

if body_start is None:
    print("ERROR: could not find anchor line")
else:
    new_content = ''.join(new_header_lines) + ''.join(lines[body_start:])
    p.write_text(new_content, encoding='utf-8')
    print(f"Written {len(new_content):,} chars, {new_content.count(chr(10))} lines")
