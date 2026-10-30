# facts.json

One file and one stadium. Every value is an object `{ "v": …, "source": "<url>" | "estimate", "why": "<one line>" }`, so the report can list the estimates automatically. The values below show the shape; they are illustrative, not checked facts.

```json
{
  "stadium": { "v": "Old Trafford", "source": "https://en.wikipedia.org/wiki/Old_Trafford" },
  "capacity_official": { "v": 74310, "source": "https://www.manutd.com/…" },
  "pitch": { "v": { "length": 105, "width": 68, "long_axis": "east-west" }, "source": "https://www.openstreetmap.org/…" },
  "footprint": { "v": "osm_way_id or a traced polygon in metres", "source": "https://www.openstreetmap.org/…" },
  "lower_tier_front": { "v": { "A": 58.5, "B": 40.0, "R": 9.0, "focus": 6.0 }, "source": "estimate", "why": "satellite image: touchline to first row about 6 m" },
  "stands": [
    {
      "seg": "N", "kind": "straight", "name": { "v": "Sir Alex Ferguson Stand", "source": "…" },
      "tiers": { "v": [1, 2, 3], "source": "…" },
      "rows": { "v": { "1": 32, "2": 26, "3": 22 }, "source": "estimate", "why": "counted on fan photos of blocks N1402 and N3405" },
      "roof": { "v": "high", "source": "…" },
      "blocks": { "v": 7, "source": "club seat map" },
      "facade": { "v": "north", "source": "photos" }
    }
  ],
  "roofs": { "high": { "v": { "front_height": 46.0, "back_height": 57.0 }, "source": "…" } },
  "named_rooms": [
    { "name": "Manchester Suite", "stand": "N", "floor": "concourse tier 2", "area_m2": { "v": 1200, "source": "club hospitality page" } }
  ],
  "players_tunnel": { "v": { "stand": "S", "position": "west end" }, "source": "…" },
  "rules": { "v": "UK Green Guide, 6th edition (2018)", "source": "https://sgsa.org.uk/…" }
}
```

How the build uses it:
- `lower_tier_front`, `stands[*].tiers`, `rows`, `roof` and `blocks` map one-to-one onto `A, B, R, FOCUS`, `TIER_SPEC` and `SEGS` in `build_v2.py`.
- `roofs` sets the `ROOFS` table.
- `named_rooms` replaces `PLAN` in `interior.py`.
- `players_tunnel` sets the tunnel segment and its position along the stand.
