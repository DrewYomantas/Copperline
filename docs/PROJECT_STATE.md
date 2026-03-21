# Copperline Project State

Last Updated: 2026-03-21

## Copperline Version
v0.3

## Current Phase
Lead Acquisition + Outreach Engine

## Current Focus
Discovery command center, automated outreach pipeline, daily workflow efficiency

## Copperline Positioning
Copperline = One-on-one workflow consulting for small service business owners

## Last Completed Pass
Pass 82 -- Command Center unified layout

## Recent Passes
Pass 82 -- Pipeline merged into Command Center: map-dominant layout, right queue rail, bottom command bar, CC default tab
Pass 81 -- Add Obs button now shows for fallback drafts; schedule block shows add obs CTA
Pass 80 -- lead_quality_score added to schema; CARTO voyager tiles; region outline-only w/ hover dash
Pass 76 -- Email search in pipeline + Ctrl+K global lead finder
Pass 75 -- Command Center: map + territory combined split-pane view
Pass 74 -- MX validation before send (prevents scrape-error bounces)
Pass 73 -- Follow-up voice rewrite (Drew tone, industry fallback path)
Pass 72 -- Territory button fix, stale warning suppressed for fallback drafts
Pass 71 -- Industry fallback drafts (17 trades mapped, no obs = no block)
Pass 70 -- Bulk regenerate: /api/bulk_regenerate + Regen Stale button
Pass 69 -- v18 voice: proper grammar, direct consequence, confident close
Pass 68 -- Auto-regen on panel open, panel layout overhaul, 22 industries
Pass 67 -- Region zoom fix, coverage fill clarity, map full-height
Pass 66 -- Command bar, coverage fill layer, 400 fix (tile radius 1000m)
Pass 65 -- US sales regions on map, visual makeover (deep dark theme)
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

1. Open Discovery → ⚡ Command Center
   - Left: map — click county → copper boundary, Search Territory runs tiled discovery
   - Right: territory panel — city cards with per-industry status
   - Map click auto-selects city in territory panel (copper highlight)
   - Territory run auto-refreshes map coverage overlay
   - Ctrl+K find-lead works from any tab

2. Pipeline → Outreach
   - Search by name, email, phone, city in search box
   - Ctrl+K from anywhere for instant lead lookup by email
   - Stale leads auto-regen on panel open (obs → draft silently)
   - No obs available → industry fallback draft (17 trades)
   - Regen Stale button mass-refreshes all stale drafts

3. Review + Send
   - Panel: email body first, details collapsed below
   - Approve / Schedule / Send via Gmail
   - MX check blocks sends to scrape-error domains

4. Follow-Up
   - Touch 1: operational nudge (references specific observation)
   - Touch 2: timeline reframe (acknowledges time passed)
   - Touch 3: low-pressure closeout
   - Industry fallback path: no obs = industry-specific anchor phrase

## DRAFT_VERSION
Current: v18

## Industry List (22 total)
plumbing, hvac, electrical, roofing, construction, landscaping, painting,
tree_service, cleaning, auto, flooring, concrete, towing, appliance_repair,
pressure_washing, moving, drywall, welding, pool_service, pest_control,
locksmith, garage_door

## Territory Industries (15, priority order)
plumbing, hvac, electrical, roofing, construction, landscaping, painting,
tree_service, cleaning, auto, flooring, concrete, towing, appliance_repair,
pressure_washing
