# Discovery Map Vision

## Purpose

The discovery map is the primary tool for finding new outreach targets.
The operator now uses coarse territory guidance plus a working search circle
to choose where to look next. Territory cells show where search effort and
lead concentration have already accumulated; the circle remains the actual
search geometry used by the current discovery endpoints.

The map is intentionally manual and operator-driven; it does not run
automatically on zoom or pan. Every search is an explicit action.

---

## Current Behavior: Territory Overlay + Search This Area

The operator can start with the territory overlay, review "Next Areas," and use
`Use Cell` to load a coarse territory cell into the working circle. The
operator can also still click directly on the map to place or move the circle,
set a radius and industry, then click "Search This Area." The backend calls
`/api/discover_area`, which queries Google Places and returns matching
businesses. Discovered businesses are written to `prospects.csv` as new leads,
drafts are generated, and markers are placed on the map at their coordinates.

This model keeps discovery deliberate. Territory cells help choose promising
underworked areas, while the working circle keeps radius-based searches
explicit and operator-controlled. The map can now compare industry saturation
inside the visible territory and the current working area before the operator
chooses which search to run next.

---

## The Radius Problem

Google Places returns results ranked by prominence. When a search radius is
large (for example 15-20 miles), the API surfaces only the most well-known
businesses in that region: franchises, chains, and highly reviewed
establishments with strong Google profiles.

Smaller, independent local service businesses, the primary target for
Copperline, tend to have thin Google profiles and get buried in large-radius
searches. They only appear reliably when the search area is small and focused.

**Implication:** To discover the best outreach targets, the operator needs to
search at the neighborhood or zip-code level, not the metro level.

---

## Marker Clustering

When a discovery run returns 40-80 markers in a dense area, individual pins
overlap and become unreadable. Marker clustering solves this by grouping
nearby markers into cluster bubbles that display a count.

Zooming in splits clusters into smaller groups. Zooming in far enough reveals
individual business markers. Zooming back out regroups them.

Clustering does not trigger new searches; it only reorganizes markers already
loaded from the last discovery run.

---

## Current Behavior: Search Visible Area

A "Search Visible Area" button tiles the current map viewport into a grid
of small-radius cells and runs sequential discovery searches across each cell.
This systematically covers an area at the neighborhood level without requiring
the operator to manually reposition the circle for each block.

The tiled search approach is designed specifically to surface smaller
businesses that large-radius searches miss. Discovery failures should surface
their real API message where available instead of being reduced to a generic
connection label.

---

## Metro To Neighborhood Drilldown Strategy

The operator workflow is designed to work at increasing levels of granularity:

1. **Metro-level pass** - large radius, finds prominent businesses fast
2. **City-level pass** - medium radius, narrower industry focus
3. **Neighborhood-level pass** - small radius (500m-1km), finds independent operators

The neighborhood level is where the most valuable undiscovered prospects live.
Search Visible Area automates the neighborhood-level grid systematically.

---

## Current Behavior: Territory Exploration

Copperline now has a bounded first territory layer built from stored
area-search history, AREA planner rows, and stored prospect coordinates. It is
coarse by design: the overlay shows territory cells, lead concentration, and
worked-vs-underworked guidance, but it does not claim exact neighborhood or
polygon precision.

That territory layer now also drives a bounded industry saturation view. The
operator can compare visible-territory industry coverage, best-next industry
suggestions, and the current working-area industry mix using stored search,
duplicate, planner, and lead counts only.

What remains future-facing is a deeper saturation model, not the presence of
territory guidance itself. The current system already supports truthful
territory-first exploration without auto-searching, auto-selecting, or
inventing finer-grained geography than the repo actually stores.
