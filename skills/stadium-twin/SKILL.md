---
name: stadium-twin
description: Build an interactive 3D twin of a real stadium from public information. It produces seat booking with sightline scores, crowd egress and fire simulation, and interior sections, as a Blender model plus a three.js web page. Use when someone asks to build, model or "twin" a stadium or arena, or to adapt the Old Trafford example to another venue.
---

# Stadium twin

This skill turns a stadium name into a working twin: a procedurally built Blender model with every seat placed, a three.js page for booking, safety simulation and sections, and a published link. `scripts/` holds the complete Old Trafford implementation, which is the reference for each step. The work is adapting it to a new stadium, not starting from scratch.

Work in a cloud or local workspace with Python 3.11+ and Node 18+. Blender runs headless as the `bpy` module (`pip install bpy shapely numpy pillow`), so nothing needs installing on the user's computer.

## The workflow

Run the steps in order. Keep `facts.json` as the single source of truth: every later step reads from it, and every value in it records where it came from.

1. **Research the stadium.** Look up, and cite:
   - the stand names and the number of tiers per stand;
   - the capacity per stand where it is published;
   - the roof type and heights;
   - the pitch orientation;
   - the footprint (OpenStreetMap or satellite);
   - the block numbering from the club's seat map;
   - named hospitality spaces with their floor areas;
   - the players' tunnel position.

   Use the club site, StadiumDB, Wikipedia, OpenStreetMap and architects' press material. Do not use paid or login-only data, and do not download third-party 3D models into the build.
2. **Write `facts.json`** using `references/facts-schema.md`. Give every number a `source` URL or `"estimate"`, plus a one-line reason. Show the user the estimates before building. They are the most likely thing to be wrong.
3. **Build the bowl.** Copy `scripts/blender/` and edit only the parameter block at the top of `build_v2.py`:
   - `A, B, R`: the lower-tier front line, a rounded rectangle;
   - `FOCUS`: the distance from the front row to the touchline;
   - `TIER_SPEC`: front distance, front height, tread, design C-value and row count per tier;
   - `ROOFS`: front and back heights and depths;
   - `SEGS`: one row per stand or corner, with tiers, roof type, block count, row overrides and facade style.

   Facade styles are functions in `build_v2.py`. Reuse the closest one, or write a new one for a distinctive facade, using simple solids rather than detail you cannot source. Run `python3 blender/textures2.py blender/tex`, then `python3 blender/build_v2.py -- out`.
4. **Derive the interior** with `scripts/blender/interior.py`. Levels come from the bowl: the walkway behind each tier, the concourse under each upper tier (soffit minus 3.0 m), and fill floors so that no storey is over about 7.6 m. Stair cores are sized by the Green Guide: 66 people per metre per minute on stairs, everyone down in 8 minutes, plus a 10 % margin. Replace the Old Trafford named rooms in `PLAN` with the researched ones. Mark every outline as indicative.
5. **Build the escape network and simulate.** `egress_net.py` builds the network during the build. Check it with `node scripts/sim/simtest.js egress` and with a fire run (see the file header). Report the 99 %-outside times. If any stand is far off the 8-minute guide, look for a network bug before believing the number.
6. **Make the web app.** Copy `scripts/web/` and run the `build.sh` steps: gltf-transform `weld` and `meshopt`, then base64 into `web/v2/`. Update the stadium-specific text in `index.html`:
   - the title;
   - the stand names and groups;
   - the block naming;
   - the price bands;
   - the zone rules;
   - the fixture line;
   - the disclaimer.

   Search the file for "Old Trafford", "Sir Alex", "Stretford" and "Trafford" to find them all.
7. **Check your own work.** Do not skip this step. Load the page in a headless browser at 1920×1080 and 390×844, and go through `references/checks.md` screen by screen. Fix what fails, then check again.
8. **Publish and report.** Publish the page as a shareable link: an artifact, GitHub Pages or any static host. Report to the user:
   - what was built;
   - the key numbers (seats, egress times, C-values by tier);
   - every estimate from `facts.json`;
   - what you would improve next.

## Honesty rules
- Call it a concept demo. Do not use crests, kits, club logos or lettering, and state that it is not affiliated with the club.
- The interior is an informed reconstruction unless real drawings were provided. Say so in the page and in the report.
- The simulation is a teaching model, not a certified fire-engineering study. Say so wherever the times appear.
- Never present an estimate as a sourced fact. Seat counts will differ from the official capacity, so report both.

## Files
- `scripts/blender/`: `build_v2.py` (bowl, roofs, facades, seats, sightlines, zones, accessibility), `interior.py`, `egress_net.py`, `textures2.py` (original procedural textures) and `players.py` (optional animated players).
- `scripts/sim/`: `sim.js` (the crowd and fire engine the page runs), `simtest.js` and `curves.js` (headless runs and curves for charts).
- `scripts/web/`: `index.html` and the shared `v2/tex` and `v2/env` assets. The stadium files in `v2/` are regenerated in step 6.
- `references/facts-schema.md`: the facts file format, with a worked example.
- `references/checks.md`: the self-check list for step 7.
