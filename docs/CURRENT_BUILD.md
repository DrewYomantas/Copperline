# Current Build Pass

## Active System
Pass 64 -- Click-to-Boundary, Reverse Geocoding, Zoom Drill-Down

## Status
Pass 64 complete.

---

## Completed: Pass 64 -- Click-to-Boundary, Reverse Geocoding, Zoom Drill-Down

Files changed:
- `lead_engine/dashboard_server.py`
- `lead_engine/dashboard_static/index.html`

### What changed

**`dashboard_server.py`**
- Added `GET /api/reverse_boundary?lat=&lng=&zoom=` — Nominatim reverse proxy.
  Maps Leaflet zoom to Nominatim zoom: 8=county, 10=city, 13=neighborhood.
  Returns same shape as /api/boundary_search plus short_name and zoom_used.

**`index.html`**
- Map click now calls `_mapClickSelectBoundary(lat, lng)` instead of placing a circle.
  Reverse geocodes to appropriate boundary based on current zoom level.
  Renders copper-colored boundary polygon on map, places circle at boundary center,
  auto-activates the territory for Search Territory.
- Shift+click still places a manual circle for override.
- `_mapBoundaryPopulateSidebar()` — finds existing queue leads within boundary bbox,
  updates tile count label with lead count, shows sent/ready breakdown in status bar.
- `_mapUpdateZoomHint()` — shows "Click = county (zoom 9)" in status bar, updates on zoom.
- `_mapUpdateZoomHint` called on init and on every moveend/zoomend.
- `mapClearCircle` override clears click boundary and text-search boundary together.
- Map fix: staggered invalidateSize (50ms/200ms/600ms) + min-height on container.
  `requestAnimationFrame` + double invalidateSize on tab switch.

### Drill-down behavior
- Leaflet zoom =7  ? Nominatim zoom 6  ? state boundary
- Leaflet zoom 8-9 ? Nominatim zoom 8  ? county boundary
- Leaflet zoom 10-12 ? Nominatim zoom 10 ? city boundary
- Leaflet zoom 13+ ? Nominatim zoom 13 ? neighborhood/suburb boundary

Operator zooms in, clicks, gets the relevant boundary highlighted. Zooms further,
clicks again, gets a finer boundary. No manual typing required for known areas.

---

## Previous: Pass 63 -- Boundary Territory Selector + Map Overhaul