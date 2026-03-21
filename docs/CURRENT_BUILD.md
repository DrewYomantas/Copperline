# Current Build Pass

## Active System
Pass 82 -- Command Center unified layout (map + queue rail + bottom command bar)

## Status
Pass 82 complete.

---

## Completed: Pass 79 -- RTS Coverage Visual Fix

**File:** `lead_engine/dashboard_static/index.html`

### Problem solved
Pass 78 outer glow halos (radius * 1.6) caused opacity stacking when 30+
circles overlapped — turned the searched area into a solid amber wash with
no visual hierarchy. Green leads cells were invisible in the noise.

### Fix
- Removed outer halo entirely — single circle per cell, no layering
- Radius reduced to r * 0.85 so adjacent cells have a visible gap
- Per-status style map:
  searched:  weight 1.2, opacity 0.45, fillOpacity 0.03 (border-only feel)
  leads:     weight 2,   opacity 0.85, fillOpacity 0.22 (clearly visible)
  contacted: weight 2,   opacity 0.85, fillOpacity 0.18
  exhausted: weight 0.8, opacity 0.2,  fillOpacity 0.02, dashed
- Render order: searched at bottom, leads/contacted on top
- mix-blend-mode: screen on rts-core path elements — overlapping circles
  add light instead of mud (RTS-style territory glow)
- Same fix applied to _mapAddRtsSearchGlow live search circles

### Kept from Pass 78
- Floating lead count badges (green number, only when leads > 0)
- Active territory pulse ring (3 copper rings + center dot on county click)
- Tile brightness/contrast filter
- Upgraded tooltips and legend

---

## Pass 78 -- RTS Map Overhaul (radial glows, badges, pulse ring)
## Pass 77 -- Command Center polish (real names, drill-down, map init)
## Pass 76 -- Email/phone search, Ctrl+K global lead finder
## Pass 75 -- Command Center split-pane (map + territory combined)
