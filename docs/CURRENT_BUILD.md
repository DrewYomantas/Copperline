# Current Build Pass

## Active System
Pass 72 -- Territory Tab Fixes, Stale Warning Fix, Docs Cleanup

## Status
Pass 72 complete.

---

## Completed: Pass 72 -- Territory Tab Fixes + Stale Warning Fix

Files: `lead_engine/dashboard_static/index.html`

### Territory Tab — buttons now work
Root cause: `JSON.stringify(city)` inside onclick HTML attributes produced
`"Rockford"` with double quotes that broke the HTML attribute parser, silently
preventing all button clicks. Fixed in four places:
- `_tpCityCard`: cj/sj now use `'"' + escHtml(value) + '"'`
- `_tpIndRow`: same fix for cj/sj/ij
- `tpToggle` inject section: same fix
- Card header toggle: now uses `data-tp-key` attribute + `this.dataset.tpKey`
  instead of inline JSON string argument

### Stale warning suppressed for fallback drafts
`_leadNeedsDraftRefresh` now checks `record._qrow.draft_type === 'industry_fallback'`
and returns false — fallback drafts are intentionally observation-free and
should not trigger the "Refresh before send" warning.

---

## Recent passes (66–71):

**Pass 71** — Industry fallback drafts (17 trades mapped, no obs = no problem)
**Pass 70** — Bulk regenerate: `/api/bulk_regenerate` + "Regen Stale" button
**Pass 69** — v18 voice: proper grammar, direct consequence, confident close,
              auto-regen row-key fix (object ref → key comparison)
**Pass 68** — Auto-regen on panel open, panel layout overhaul (body first),
              22 industries, 404 scan warnings suppressed
**Pass 67** — Region zoom fix, coverage fill clarity, map full-height,
              territory display "Map Area", dropdown fix
**Pass 66** — Command bar, coverage fill layer, hover tooltips, 400 fix
              (tile radius 800→1000m)

---

## Previous major passes:
**Pass 65** — US Sales Regions + Visual Makeover
**Pass 64** — Click-to-boundary, reverse geocoding, zoom drill-down
**Pass 63** — Boundary territory selector, simplified toolbar
