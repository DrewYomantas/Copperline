# AI Development Log

Chronological record of all AI-assisted implementation passes on the Copperline project.
Update this file at the end of every pass.

---

## 2026-03-15

### Runtime Verification Hotfixes

**Diagnosed from live browser session (5 screenshots + console log).**

**Root causes found:**
- `api()` called `r.json()` unconditionally. `/api/mc/clients` (missing backend
  route) returns 404 HTML. Parsing `<!DOCTYPE html>` as JSON throws
  `SyntaxError: Unexpected end of input at (index):1:10`. Fired on every
  health check cycle (30s interval) and every Clients tab open.
- Map `click` event repositioned the active circle on any tile click, wiping
  result markers without warning.
- `Clear Coverage` button was near-invisible (text color `var(--dim)`).

**Fixes:**
- `api()`: added `if (!r.ok)` guard — throws `Error("API /path returned N: ...")`
  on non-OK responses. All callers have `try/catch` so errors surface cleanly.
- `_mapInit` click handler: wraps `_mapDrawCircle` in
  `if (_mapResultItems.length === 0)` guard. Circle repositions freely when
  no results loaded; locked once results are present until `X Clear` used.
- `.btn-coverage`: raised text to `var(--muted)`, border to `var(--border-hi)`,
  hover to `var(--text)` + blue border.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `2b202cd`

**Parse check:** `vm.Script` PARSE OK on served JS post-fix.

---

### Emergency Fix — Duplicate `let _currentPage` SyntaxError

**Root cause:** Stale duplicate `let _currentPage = 'outreach'` declaration
left over from the Step 1 nav restructure (commit `1dc811a`). The duplicate
sat at line 2011, above the real declaration at line 2018. Browsers enforce
strict `let` uniqueness in script scope and threw a fatal parse error:

`Uncaught SyntaxError: Identifier '_currentPage' has already been declared`

This killed the entire script block at parse time — nothing functioned.

**Diagnosis path:** Browser DevTools console showed the exact error at line
2018. Node `vm.Script` parse check on the served JS confirmed the issue and
confirmed the fix.

**Fix:** Removed the 5-line stale block (orphaned comment + duplicate `let`).
Single declaration at line 2013 remains.

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `761faaf`

---

### Step 7 — Human-Readable Discovery Labels

**Goal:** Replace raw coordinates as primary history label with a city name
derived from already-loaded result data.

**Changes:**
- Added `_mapAreaLabel(markers)`: frequency-counts `biz.city` across result
  set, returns most common city name, null if no city data present
- Wired `mapSearch()` `res.ok`: computes label before history unshift,
  stores as `label` field on history entry
- Updated `_mapRenderHistory()`: `entry.label` as primary (fallback to
  `lat/lng` coords); secondary shows `X.X mi — N found`; exact coords
  preserved as `title` attribute for hover

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `3f86767`

---

### Step 6 — Discovery History List

**Goal:** Session-only recent searches list below the map. Click to refocus.

**Changes:**
- Added `_mapSearchHistory[]`, `MAP_HISTORY_MAX = 10`
- Added `_mapRenderHistory()`: builds `.mh-item` rows with `lat/lng`, radius
  in miles, and `found` count; click handler sets `_mapRadiusM`, calls
  `_mapDrawCircle()`, then `setView()` to recenter
- Added `_mapClearHistory()`: resets array, hides `#map-history`
- Added `#map-history` HTML below `#map-status` (hidden until first entry)
- Added CSS: `#map-history`, `.mh-hdr`, `.mh-title`, `.mh-clear`,
  `.mh-list`, `.mh-item`, `.mh-item-label`, `.mh-item-meta`
- Wired `mapSearch()` `res.ok`: `unshift` entry, trim to `MAP_HISTORY_MAX`,
  call `_mapRenderHistory()`
- Coverage, clustering, result markers unchanged

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `6d79c64`

---

### Step 5 — Discovery Coverage Memory

**Goal:** Persist prior search areas as faint map overlays for the current
session so the operator can see where they have already searched.

**Changes:**
- Added `_mapCoverageCircles[]` module variable
- Added `_mapClearCoverage()` — calls `.remove()` on each overlay, resets
  array, hides `btnClearCoverage`
- Added `.btn-coverage` CSS class for the toolbar button
- Added `#btnClearCoverage` button to map toolbar (`display:none` by default)
- Wired `mapSearch()` `res.ok` branch to snapshot `_mapCenter` + `_mapRadiusM`
  as `L.circle` with `interactive:false`, `dashArray:'4 4'`, `fillOpacity:0.04`,
  blue tint — pushed to `_mapCoverageCircles[]`, button revealed
- Active circle, drag handle, clustering, result markers all unchanged

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `f27a472`

---

### Step 4 — Map Result Usability Polish

**Goal:** Add sort and filter controls to the results panel without touching
discovery flow, backend, or clustering.

**Changes:**
- Added CSS: `.mrp-controls`, `.mrp-ctrl-select`, `.mrp-ctrl-chk` classes
- Added HTML controls row (`#mrp-controls`) between header and list:
  sort select (default / Name A–Z / City A–Z) + email-only checkbox
- Refactored `_mapRenderPanel()` to read filter+sort state from DOM controls
  before building list; `_mapResultItems[]` is never mutated
- Count shows `(N of M)` when email filter is active
- Extended `_mapClearResultMarkers()` to reset `mrp-sort` and `mrp-email-only`

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `a19bc16`

---

### Step 3 — Results Side Panel (Discovery Map)

**Goal:** Show a scrollable list of discovered businesses alongside the map
after a discovery search completes.

**Changes:**
- Added CSS: `#map-layout`, `#map-results-panel`, `.mrp-hdr`, `.mrp-list`,
  `.mrp-item`, `.mrp-name`, `.mrp-meta`, `.mrp-dot` classes
- Added `#map-layout` flex wrapper in HTML around `#map-container` and new panel
- Added `#map-results-panel` div with header (`mrp-count`) and scrollable list
- Added `_mapResultItems[]` module variable storing `{biz, marker}` pairs
- Added `_mapRenderPanel()` — renders list items, binds click to
  `zoomToShowLayer()` + `openPopup()` per marker
- Extended `_mapClearResultMarkers()` to reset `_mapResultItems` and hide panel
- Extended `_mapPlaceResultMarkers()` to push to `_mapResultItems` and call render

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `c0caa17`

---

### Step 2 — Marker Clustering (Discovery Map)

**Goal:** Group discovery result markers into cluster bubbles that split on
zoom-in and regroup on zoom-out.

**Changes:**
- Added Leaflet.markercluster v1.5.3 CSS + JS via CDN (`<head>`)
- Added `_mapClusterGroup` module variable
- Initialized `L.markerClusterGroup()` inside `_mapInit()` after tile layer
- Changed result marker creation from `.addTo(_mapInstance)` to `.addTo(_mapClusterGroup)`
- Updated `_mapClearResultMarkers()` to call `_mapClusterGroup.clearLayers()`
- Drag handle and circle markers unchanged

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `38da7c3`

---

## 2026-03-14

### Step 1 — Dashboard Navigation Restructure

**Goal:** Reduce 13-tab flat nav to a structured 5-section nav with sub-tabs.

**Changes:**
- Rebuilt top navigation from 13 flat tabs to 5 parent sections
- Added sub-tab system mapping to original page divs
- Sections: Pipeline | Discovery | Clients | Health | Tools
- All original page divs preserved and intact
- No backend changes

**File changed:** `lead_engine/dashboard_static/index.html`

**Commit:** `1dc811a`

---

### Search History Improvements

**Goal:** Improve usability of the Searches page in the dashboard.

**Changes:**
- Added summary stats to search history view
- Added rerun buttons to past search entries

**Commit:** `bcac905`
