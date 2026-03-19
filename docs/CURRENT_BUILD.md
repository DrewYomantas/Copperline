# Current Build Pass

## Active System
Pass 52a -- Observation Route Recovery + Discovery Connection Hardening + Circle Interaction Review

## Status
Pass 52a complete. Repo is ready for the next product pass.

---

## Completed: Pass 52a -- Observation Route Recovery + Discovery Connection Hardening + Circle Interaction Review -- `PENDING_COMMIT`

Product changes in:
- `lead_engine/dashboard_static/index.html`

Docs updated in:
- `docs/PROJECT_STATE.md`
- `docs/CURRENT_BUILD.md`
- `docs/CHANGELOG_AI.md`
- `docs/AI_CONTROL_PANEL.md`
- `docs/DISCOVERY_MAP_VISION.md`

No queue schema reorder/rename changes. No `run_lead_engine.py` changes.
No email sender core changes. No scheduler timing changes. No send-path changes.
No backend route changes.

### Problem addressed

Two operator-facing regressions showed up after Passes 51 and 52:

- The observation candidate panel could dump raw Flask 404 HTML when the live
  dashboard instance was stale or missing the candidate route.
- Discovery failures coming back from real API endpoints were often surfaced as
  generic "Connection error" states even when the backend had returned a clear
  JSON validation or server error.

At the same time, the map copy still centered the old circle-first workflow
even though territory cells and `Use Cell` had become the better starting point
for choosing the next area.

### What was added

**`lead_engine/dashboard_static/index.html`**

- Hardened `apiJson(...)` and non-JSON error handling so observation-candidate
  actions never surface raw HTML dumps in the panel.
- Added cleaner operator-facing messages for stale-route / stale-server cases,
  including route-unavailable wording for HTML 404 responses.
- Switched discovery requests to structured JSON handling so map discovery now
  surfaces real backend error text from `/api/discover_area` and
  `/api/discover_area_batch`.
- Preserved partial/iterative discovery runs while making request issues visible
  in map status and completion toasts.
- Updated map copy and status messaging so territory cells are the preferred
  starting point, while the circle remains the working geometry used by the
  current discovery endpoints.
- Improved territory overlay failure messaging in the legend instead of a vague
  generic failure note.

### What remains intentionally out of scope

- Exact neighborhood/zip/polygon territory modeling
- Geospatial analytics or BI dashboarding
- Hidden background search automation
- Replacing circle-based discovery with a new spatial backend model
- Queue, sender, scheduler, or send-path changes
- Fake precision beyond stored search centers and stored prospect coordinates

### Verification

- Dashboard JS parses clean via `new vm.Script(...)`.
- Flask test client:
  - `POST /api/generate_observation_candidate` with invalid row -> `400` JSON
    `{'blocked_reason': 'invalid_request', 'error': 'Invalid index', 'ok': False}`
  - `POST /api/discover_area` without coords -> `400` JSON
    `{'error': "lat/lng required and must be numeric: 'lat'", 'ok': False}`
  - `POST /api/discover_area_batch` without coords -> `400` JSON
    `{'error': "lat/lng required and must be numeric: 'lat'", 'ok': False}`
  - `GET /api/map_territory_overlay` -> `200`
  - current summary still built from `226` area-search rows, `11` AREA planner
    rows, and `613` coordinate-bearing prospects
- Live local app check on the already-running dashboard instance still showed a
  stale-server mismatch for `/api/map_territory_overlay` (`404` on
  `http://127.0.0.1:5000`), which matches the route-recovery bug this pass now
  hardens in the UI instead of dumping raw HTML.

---

## Previous Completed: Pass 52 -- Territory Heatmap Overlay -- `6285e65`

- Added grounded territory cells and `Use Cell` on the discovery map using real
  persisted search and lead data.
