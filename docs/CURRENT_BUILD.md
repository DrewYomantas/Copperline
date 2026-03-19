# Current Build Pass

## Active System
Pass 52 -- Territory Heatmap Overlay

## Status
Pass 52 complete.

---

## Completed: Pass 52 -- Territory Heatmap Overlay -- `6285e65`

Product changes across two code files:
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

Docs updated in:
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/CHANGELOG_AI.md`
- `docs/AI_CONTROL_PANEL.md`

No queue schema reorder/rename changes. No `run_lead_engine.py` changes.
No email sender core changes. No scheduler timing changes. No send-path changes.

### Problem addressed

Discovery already supported map-area search, tiled visible-area search, marker
clustering, persisted search history, and an AREA-aware city planner, but the
map itself still made the operator remember too much manually. Search coverage
was mostly session-only circles, so it was hard to see where effort had already
clustered, where leads were concentrated, and which neighborhoods looked
underworked versus duplicate-heavy.

### What was added

**`lead_engine/dashboard_server.py`**

- Added read-only `GET /api/map_territory_overlay`.
- The route aggregates three verified data sources only:
  - `search_history.json` area-search rows
  - `city_planner.json` AREA planner rows
  - `prospects.csv` rows with stored `lat` / `lng`
- The route returns coarse territory cells, not exact neighborhood boundaries,
  with lead counts, area-search counts, duplicate-heavy search counts,
  planner-check counts, industry breakdowns, and guidance metadata.

**`lead_engine/dashboard_static/index.html`**

- Added a territory overlay toolbar to the existing Map Search page:
  `Territory Overlay`, `Next Areas`, and `Refresh Overlay`.
- Added a coarse territory cell layer on the Leaflet map using persisted search
  and lead data, filtered by the current map industry when selected.
- Added a legend panel that explains:
  underworked next areas, worked cells, and saturation-risk cells.
- Added per-cell popup guidance plus `Use This Cell`, which moves the existing
  search circle to the chosen territory cell without auto-running discovery.
- Overlay refreshes after map discovery runs so the map reflects updated search
  coverage and lead concentration without changing the discovery workflow.

### What remains intentionally out of scope

- Exact neighborhood/zip/polygon territory modeling
- Geospatial analytics or BI dashboarding
- Hidden background search automation
- Queue, sender, scheduler, or send-path changes
- Fake precision beyond stored search centers and stored prospect coordinates

### Verification

- Python imports clean for `lead_engine.dashboard_server`.
- Dashboard JS parses clean via `new vm.Script(...)`.
- Flask test client:
  - `GET /api/map_territory_overlay` -> `200`
  - returned `386` coarse territory cells
  - summary built from `226` area-search rows, `11` AREA planner rows, and
    `613` coordinate-bearing prospects
- Live local app HTML at `http://127.0.0.1:5000/` contains the new map controls:
  `Territory Overlay`, `Next Areas`, `map-territory-legend`,
  and `mapReloadTerritoryOverlay`

---

## Previous Completed: Pass 51 -- Observation Autowrite + Candidate Approval Layer -- `aea9452`

- Added grounded observation candidate generation plus operator review/use/edit/save flow.
