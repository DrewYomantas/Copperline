# Current Build Pass

## Active System
Pass 63 -- Boundary Territory Selector + Map Overhaul

## Status
Pass 63 complete.

---

## Completed: Pass 63 -- Boundary Territory Selector + Map Overhaul

Files changed:
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

### What changed

**`dashboard_server.py`**
- Added `GET /api/boundary_search` — proxies Nominatim, returns GeoJSON polygon + bbox +
  center + estimated tile count for any US city or county. No API key. CORS-safe.

**`index.html`**
- Added boundary selector bar (`bnd-bar`) above the map with a search input that
  queries `/api/boundary_search`, renders the polygon on the Leaflet map as a blue
  dashed boundary layer, and shows active territory name + tile estimate.
- `bndSearchTerritory()` — tiles the boundary bbox into 800m circles and runs
  `/api/discover_area` sequentially across each tile (max 60). Progress shown inline.
  Cancel button stops after current tile.
- Simplified toolbar — removed dense multi-button layout, replaced with two clean rows.
  All existing functionality preserved (Search Here, Search Visible Area, Exhaust Circle,
  Reset, Clear Coverage).
- Grid bar hidden until a circle is placed (`_mapDrawCircle` / `mapClearCircle`).
- Map instructions updated to lead with the boundary workflow.
- Results panel: `weak` / `needs-contact` / `closed` groups now collapsed by default
  in workflow view with click-to-expand. `ready` and `maybe` groups highlighted.

### What is unchanged
- Queue schema, run_lead_engine.py, sender/scheduler, follow-up system.
- All existing discover_area / discover_area_batch / territory overlay logic.

---

## Previous: Pass 62 -- Voice Rewrite, Consultation Positioning