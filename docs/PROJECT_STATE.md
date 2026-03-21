# Copperline Project State

Last Updated: 2026-03-21

## Copperline Version
v0.3

## Current Phase
Lead Acquisition + Outreach Engine

## Current Focus
Discovery command center (map + territory), automated outreach pipeline

## Copperline Positioning
Copperline = One-on-one workflow consulting for small service business owners

## Last Completed Pass
Pass 72 -- Territory Tab Fixes, Stale Warning Fix, Docs Cleanup

## Previous Completed Passes (recent)
Pass 71 -- Industry fallback drafts (17 trades, no obs = no problem)
Pass 70 -- Bulk regenerate endpoint + Regen Stale toolbar button
Pass 69 -- v18 voice rewrite (grammar, confident consequence + close)
Pass 68 -- Auto-regen on panel open, panel layout overhaul, 22 industries
Pass 67 -- Region zoom fix, coverage fill, map full-height, territory display
Pass 66 -- Command bar, coverage fill layer, hover tooltips, 400 fix
Pass 65 -- US sales regions on map, visual makeover (deeper dark theme)
Pass 64 -- Click-to-boundary, reverse geocoding, zoom drill-down
Pass 63 -- Boundary territory selector, simplified map toolbar
Pass 62 -- Voice rewrite v17, consultation positioning

## Protected Systems
- `run_lead_engine.py`
- Queue schema (column order and naming)
- `pending_emails.csv` pipeline
- Email sender
- Follow-up scheduler timing/core
- `safe_autopilot_eligible` logic

## Core Operator Workflow

1. Open Discovery → Map Search
   - US view shows 6 sales regions
   - Click region → zooms to state level
   - Click county/city → copper boundary highlights, circle placed at center
   - Pick industry → Search Territory tiles entire area automatically
   - Coverage fill shows searched/leads/contacted/exhausted cells

2. OR: Discovery → Territory tab
   - Add city + state manually (or via autocomplete)
   - City card shows all 15 industries with status
   - Run Next / Run Remaining / Run individual industry per city
   - Faster workflow for known target cities

3. Pipeline → Outreach
   - Opens stale leads → auto-regen fires silently on panel open
   - Observation agent generates candidate → applies → regenerates draft
   - If no obs evidence → industry fallback draft (17 trades mapped)
   - Panel shows email body first, details collapsed below
   - Regen Stale button mass-refreshes all stale drafts

4. Approve / Schedule / Send
   - Approve individual or bulk-approve
   - Schedule for tomorrow morning
   - Send via Gmail

## DRAFT_VERSION
Current: v18

## Industry List (22 total)
plumbing, hvac, electrical, roofing, construction, landscaping, painting,
tree_service, cleaning, auto, flooring, concrete, towing, appliance_repair,
pressure_washing, moving, drywall, welding, pool_service, pest_control,
locksmith, garage_door

## Territory Industries (15, in priority order)
plumbing, hvac, electrical, roofing, construction, landscaping, painting,
tree_service, cleaning, auto, flooring, concrete, towing, appliance_repair,
pressure_washing
