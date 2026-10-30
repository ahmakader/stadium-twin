"""Indicative interior for the Old Trafford model (imported by build_v2.py).

Everything structural is built as CLOSED solids so a clipping plane in the web viewer can show a section with
solid fill (poche): tier slabs, floor slabs, facade inner leaf, roof, stair cores, partition walls, stairs.

Coordinates follow build_v2: each stand is described in (d, h) = (distance from the lower-tier front line, height)
and swept along the stand with pt(seg, u, d).  Levels are derived from the bowl itself:
  * ground floor (0.0),
  * the floor behind each tier (back of the tier + 0.2: executive boxes behind tier 1, as on the real stands),
  * the concourse each upper-tier vomitory leads down to (3.0 m clear under the tier above the vom exit),
  * intermediate floors so no storey is taller than about 7.5 m.
Room names and positions come from the club's published hospitality spaces; layouts are indicative.
"""
import math, json
import numpy as np
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.ops import unary_union
from shapely.geometry.polygon import orient

STEP_RISE, STEP_GO = 0.17, 0.28
CLEAR = 2.6            # clear height for a usable floor
SLAB = 0.3
LEAF_IN, LEAF_OUT = 0.35, 0.05
CORE_WALL = 0.25
TUNNEL = dict(seg="S", u0=-48.25, u1=-43.75, ymax=3.9, deck=3.4, soffit=3.1, d1=14.0)

# ---------------------------------------------------------------------------------------------- room kinds
KINDS = {   # name, floor colour (also used by the web legend)
    "concourse": ("Concourse & circulation", (0.55, 0.57, 0.6)),
    "hospitality": ("Hospitality", (0.62, 0.48, 0.85)),
    "boxes": ("Executive boxes", (0.52, 0.36, 0.78)),
    "dining": ("Restaurant & bar", (0.78, 0.45, 0.62)),
    "players": ("Players & officials", (0.30, 0.70, 0.52)),
    "media": ("Media & broadcast", (0.33, 0.58, 0.85)),
    "visitor": ("Museum & retail", (0.90, 0.68, 0.22)),
    "services": ("Kiosks & toilets", (0.88, 0.50, 0.25)),
    "boh": ("Back of house & plant", (0.36, 0.38, 0.42)),
    "core": ("Escape stairs & lifts", (0.80, 0.22, 0.20)),
}

# named spaces (club "Spaces" listing: names, stands, areas; level/position indicative)
NAMED = [
    # seg, level role, band, f0, f1, name, kind, note
    ("N", "ground", "back2", 0.52, 0.95, "Museum & stadium tour entrance", "visitor", "Manchester United Museum, Sir Alex Ferguson Stand"),
    ("N", "fill1", "all", 0.50, 0.95, "Museum galleries", "visitor", "Manchester United Museum"),
    ("N", "fill1", "all", 0.06, 0.44, "Red Café", "dining", "Restaurant in the Sir Alex Ferguson Stand"),
    ("N", "rear1", "back", 0.55, 0.80, "Salford Bar & Kitchen", "dining", "514 m², one floor below the Manchester Suite"),
    ("N", "conc2", "back", 0.20, 0.80, "Manchester Suite", "hospitality", "1,390 m², up to 1,100 guests"),
    ("N", "fill2", "all", 0.38, 0.62, "Salford Grill", "dining", "433 m², syndicate room for the Manchester Suite"),
    ("NE", "rear1", "back", 0.28, 0.72, "500 Club", "hospitality", "Floor-to-ceiling windows"),
    ("NE", "conc2", "back", 0.12, 0.48, "Evolution Suite", "hospitality", "477 m², pitch on one side, Salford Quays on the other"),
    ("NE", "conc2", "back", 0.54, 0.90, "Knight's Lounge", "hospitality", "327 m²"),
    ("NE", "fill2", "all", 0.30, 0.62, "1999 Suite", "hospitality", "201 m²"),
    ("NE", "rear2", "all", 0.40, 0.62, "The Academy", "hospitality", "138 m², 5th floor"),
    ("NW", "rear1", "back", 0.20, 0.70, "United Road / Devils Bar", "dining", "502 m² sports bar"),
    ("NW", "conc2", "back", 0.30, 0.62, "Captains' Lounge", "hospitality", "214 m²"),
    ("NW", "rear2", "all", 0.15, 0.85, "100 Club", "hospitality", "5th floor, floor-to-ceiling windows"),
    ("E", "ground", "back2", 0.22, 0.78, "Megastore", "visitor", "Club shop behind the curved glass of the East Stand"),
    ("E", "ground", "back", 0.80, 0.95, "Ticket office", "visitor", ""),
    ("W", "ground", "back2", 0.28, 0.72, "International Suite", "hospitality", "780 m², ground floor with vehicle access"),
    ("S", "ground", "front", 0.70, 0.79, "Away dressing room", "players", ""),
    ("S", "ground", "front", 0.79, 0.90, "Home dressing room", "players", ""),
    ("S", "ground", "mid", 0.70, 0.78, "Match officials", "players", ""),
    ("S", "ground", "mid", 0.78, 0.86, "Warm-up area", "players", ""),
    ("S", "ground", "mid", 0.86, 0.93, "Medical & physio", "players", ""),
    ("S", "ground", "front", 0.55, 0.68, "Press conference room", "media", ""),
    ("S", "ground", "mid", 0.55, 0.68, "Mixed zone", "media", ""),
    ("S", "ground", "front", 0.47, 0.53, "Original 1910 players' tunnel (preserved)", "players", "Used until 1993; between the dugouts"),
    ("S", "fill1", "all", 0.08, 0.30, "Treble Suite", "hospitality", "Sir Bobby Charlton Stand"),
    ("S", "fill1", "all", 0.36, 0.64, "Media centre", "media", ""),
    ("S", "rear1", "boxes", 0.19, 0.31, "Stretford Suite", "hospitality", "297 m², window onto the pitch"),
    ("S", "rear1", "boxes", 0.43, 0.57, "Directors' box & lounge", "hospitality", "Centre of the Sir Bobby Charlton Stand"),
    ("S", "rear1", "boxes", 0.69, 0.81, "Trafford Suite", "hospitality", "382 m², long window onto the pitch"),
    ("S", "fill2", "all", 0.30, 0.70, "Press & broadcast", "media", "Media seats sit in the centre of the stand"),
]


def frac_u(G, seg, f):
    ps = G["samples"](seg)
    return ps[0] + (ps[-1] - ps[0]) * f


def u_per_m(G, seg, d):
    """u units per metre along the stand at distance d."""
    if seg in G["STRAIGHT"]:
        return 1.0
    return math.degrees(1.0 / (G["R"] + d))


def tangent(G, seg, u, d):
    e = 1e-3 if seg in G["STRAIGHT"] else 1e-3
    (x0, z0), _ = G["pt"](seg, u - e, d); (x1, z1), _ = G["pt"](seg, u + e, d)
    v = np.array([x1 - x0, z1 - z0]); return v / np.linalg.norm(v)


def outward(G, seg, u):
    _, nrm = G["pt"](seg, u, 0.0)
    return -np.array(nrm, float)


# ---------------------------------------------------------------------------------------------- 2D profiles
def tier_poly(G, seg, t):
    """Tier slab: stepped top just under the terrace surface (offset o; larger in the corners where the solid is swept in
    coarser steps than the terrace chords), raking soffit below."""
    treads, TS = G["treads"], G["TIER_SPEC"]
    o = 0.06 if seg in G["STRAIGHT"] else 0.10
    T = treads(seg, t); sp = TS[t]
    dB, hB = G["tier_back"](seg, t)
    top = []
    for k, (d0, d1, y, _) in enumerate(T):
        top += [(d0 + o, y - o), (d1 + o, y - o)]
    y0 = sp["y0"]
    if t == 1:
        front = [(-0.19, -0.4), (-0.19, y0 + 0.19), (-0.06, y0 + 0.19), (-0.06, y0 - o)]
        sof = [(G["row_d"](t, r), G["row_y"](t, r) - 0.75) for r in range(len(T))]
        sof.append((dB + o, hB - 0.75))
        poly = front + top + [(dB + o, hB - 0.75)] + sof[::-1][1:] + [(-0.19, -0.4)]
        P = Polygon(poly).buffer(0)
        return P.intersection(box(-1, 0.0, 500, 500))
    (fd, fy), (bd, by) = G["soffit"](seg, t)
    sy = lambda d: G["soffit_y"](seg, t, d)
    front = [(fd + 0.06, sy(fd + 0.06)), (fd + 0.06, y0 - 0.16), (sp["d0"] + o, y0 - 0.16)]
    poly = front + top + [(dB + o, sy(dB + o))]
    return Polygon(poly).buffer(0)


def roof_poly(G, seg, inset=False):
    roof = G["SEG"][seg][5]; Rr = G["ROOFS"][roof]; ry = lambda d: G["roof_y"](roof, d)
    dc = Rr["df"] + 7.0; db = Rr["db"]
    pts = [(dc + 0.02, ry(dc + 0.02) - 0.02), (db + 0.58, ry(db + 0.58) - 0.02), (db + 0.58, ry(db + 0.58) - 1.38), (dc + 0.02, ry(dc + 0.02) - 1.38)]
    return Polygon(pts)


def leaf_poly(G, seg):
    roof = G["SEG"][seg][5]; Rr = G["ROOFS"][roof]; ry = lambda d: G["roof_y"](roof, d)
    db = Rr["db"]
    a, b = db - LEAF_IN, db - LEAF_OUT
    return Polygon([(a, -0.4), (b, -0.4), (b, ry(b) - 1.38), (a, ry(a) - 1.38)])


def clearance_ok(U, d, F, need=CLEAR, below=SLAB):
    return not U.intersects(LineString([(d, F - below + 0.001), (d, F + need)]))


def valid_interval(U, F, d_lo, d_hi, need=CLEAR, step=0.1):
    """Largest run of d where a slab at F (and the clear height above it) is free of U, touching d_hi."""
    ds = np.arange(d_hi - 0.05, d_lo, -step)
    run_end = None; run_start = None
    for d in ds:
        if clearance_ok(U, d, F, need):
            if run_end is None:
                run_end = d_hi
            run_start = d
        else:
            if run_end is not None:
                break
            else:
                return None
    if run_end is None:
        return None
    return (round(run_start - step / 2, 2), d_hi)


def ceiling_at(U, d, F):
    """Lowest underside of the structure above F at d (or None)."""
    g = U.intersection(LineString([(d, F + 0.05), (d, 400)]))
    if g.is_empty:
        return None
    ys = []
    for geom in getattr(g, "geoms", [g]):
        ys += [c[1] for c in geom.coords]
    return min(ys) if ys else None


# ---------------------------------------------------------------------------------------------- planning
def plan(G, blocks):
    SEGS, SEG, ROOFS, VOMR, VOMS = G["SEGS"], G["SEG"], G["ROOFS"], G["VOMR"], G["VOMS"]
    row_d, row_y, tier_back, soffit, soffit_y, roof_y = G["row_d"], G["row_y"], G["tier_back"], G["soffit"], G["soffit_y"], G["roof_y"]
    seats_tier, seats_seg = {}, {}
    for b in blocks:
        seats_tier[(b["seg"], b["tier"])] = seats_tier.get((b["seg"], b["tier"]), 0) + b["count"]
        seats_seg[b["seg"]] = seats_seg.get(b["seg"], 0) + b["count"]
    PL = dict(segs={}, rooms=[], kinds={k: dict(label=v[0], color=[round(c, 3) for c in v[1]]) for k, v in KINDS.items()})
    for seg, kind, stand, code, tiers, roof, nb, _, style in SEGS:
        Rr = ROOFS[roof]; db = Rr["db"]; dbi = db - LEAF_IN
        ry = lambda d, roof=roof: roof_y(roof, d)
        S = dict(seg=seg, stand=stand, kind=kind, roof=roof, db=db, dbi=dbi, tiers=list(tiers))
        TP = {t: tier_poly(G, seg, t) for t in tiers}
        tiersU = unary_union(list(TP.values()))
        S["_tiers"] = TP; S["_tiersU"] = tiersU
        # vomitories -> where they land
        vom = {}
        for t in tiers:
            r0, r1 = VOMR[(seg, t)]
            d0v, d1v, h0 = row_d(t, r0), row_d(t, r1), row_y(t, r0)
            if t == 1:
                F = 0.0
            else:
                F = min(h0, math.floor((soffit_y(seg, t, d1v) - 3.0) * 20) / 20)
            run = (h0 - F) / (STEP_RISE / STEP_GO)
            htop = row_y(t, r1)
            if htop - h0 - 0.35 >= 2.3:
                x0 = d1v + 1.0; open_top = h0 + 2.3
            else:      # low vomitory: the steps start inside the recess so the tunnel clears the rows behind
                x0 = d1v - 2.0; open_top = h0 - 2.0 * STEP_RISE / STEP_GO + 2.3
            vom[t] = dict(r0=r0, r1=r1, d0v=d0v, d1v=d1v, h0=h0, F=F, run=run, d_land=x0 + run, x0=x0, open_top=open_top, htop=htop,
                          us=[(float(c), float(hw)) for c, hw in VOMS[(seg, t)]])
        S["vom"] = vom
        # behind each tier: walkway + what closes it (glass boxes / wall)
        rear = {}
        for t in tiers:
            dB, hB = tier_back(seg, t)
            top = t == max(tiers)
            glass = None; wall = None
            if not top:
                sd, sy = soffit(seg, t + 1)[0]
                if dB + 1.5 < sd:
                    glass = (sd, hB + 0.2, sy)
                else:
                    hs = soffit_y(seg, t + 1, dB + 1.5)
                    if hs > hB + 0.4:
                        glass = (dB + 1.5, hB + 0.2, hs)
            else:
                if roof == "low":
                    glass = (dB + 1.5, hB + 0.2, hB + 4.2)
                    wall = (dB + 1.5, hB + 4.2, ry(dB + 1.5) - 1.4)
                else:
                    wall = (dB + 1.5, hB + 0.2, ry(dB + 1.5) - 1.4)
            rear[t] = dict(dB=dB, hB=hB, h=round(hB + 0.2, 3), glass=glass, wall=wall, top=top)
        S["rear"] = rear
        # structure for clearance checks: tiers + roof + rear walls (+ leaf)
        solids = [tiersU, roof_poly(G, seg)]
        for t, r in rear.items():
            if r["wall"]:
                d_, h0_, h1_ = r["wall"]
                if r["top"] and roof != "low":
                    solids.append(box(d_ + 0.02, h0_, min(d_ + 0.30, dbi), h1_ + 0.05))
                else:
                    solids.append(box(d_ + 0.02, h0_ - 0.05, min(d_ + 0.30, dbi), h1_ + 0.05))
        struct0 = unary_union(solids)
        # levels
        cands = [(0.0, "ground", 0)]
        for t in tiers:
            cands.append((rear[t]["h"], "rear", t))
            if t > 1:
                cands.append((vom[t]["F"], "conc", t))
        cands.sort()
        merged = []
        for c in cands:
            if merged and abs(c[0] - merged[-1][0]) < 2.9:
                prio = {"conc": 3, "rear": 2, "ground": 1, "fill": 0}
                if prio[c[1]] > prio[merged[-1][1]] and merged[-1][1] != "ground":
                    merged[-1] = c
                continue
            merged.append(c)
        # cap: highest usable floor under the roof at the facade
        top_ok = ry(dbi) - 1.4 - CLEAR - 0.3
        levels = []
        for i, c in enumerate(merged):
            levels.append(c)
            if i + 1 < len(merged):
                gap = merged[i + 1][0] - c[0]
                if gap > 7.6:
                    k = int(math.ceil(gap / 7.6)) - 1
                    for j in range(1, k + 1):
                        levels.append((round(c[0] + gap * j / (k + 1), 2), "fill", 0))
        # extra plant floor in the low stands above the boxes
        last = max(l[0] for l in levels)
        if roof == "low" and top_ok - last > 3.6:
            levels.append((round(last + 4.2, 2), "fill", 0))
        levels.sort()
        LV = []
        fills = 0
        for ffl, role, t in levels:
            if ffl > top_ok + 0.01 and role != "rear":
                continue
            if role == "ground":
                iv = valid_interval(struct0, 0.0, -0.23, dbi)
                iv = iv or (dbi - 8, dbi)
            else:
                iv = valid_interval(struct0, ffl, -0.23, dbi)
            if iv is None or iv[1] - iv[0] < 3.5:
                continue
            if role == "fill":
                fills += 1
            LV.append(dict(ffl=round(ffl, 3), role=role, tier=t, d0=iv[0], d1=iv[1], tag=(role + str(t)) if role in ("rear", "conc") else ("fill" + str(fills) if role == "fill" else "ground")))
        LV.sort(key=lambda l: l["ffl"])
        for i, l in enumerate(LV):
            l["index"] = i
            l["name"] = "Level %d" % i if i else "Ground floor"
        S["levels"] = LV
        S["_struct0"] = struct0
        # rear walkway usable for egress if the floor behind starts at the walkway
        for t, r in rear.items():
            lv = next((l for l in LV if l["role"] == "rear" and l["tier"] == t), None)
            r["level"] = lv["index"] if lv else None
            r["egress"] = bool(lv and lv["d0"] <= r["dB"] + 1.6 and r["glass"] is not None and t == 1)
        # gates (Green Guide capacity method, as the egress network)
        w_req = seats_seg[seg] / (8.0 * 82.0) * 1.10
        ng = max(1, int(math.ceil(w_req / 5.0)))
        if kind == "straight":
            ng = max(ng, 3)
        w_g = max(3.0, w_req / ng)
        S["gates"] = [dict(f=(j + 0.5) / ng, u=frac_u(G, seg, (j + 0.5) / ng), w=round(w_g, 1), code=f"Gate {code}{j + 1}") for j in range(ng)]
        # stair cores: sized by the Green Guide capacity method (8 min, 66 p/m/min on stairs, 10 % margin)
        req = []
        for t in tiers:
            if t > 1:
                lvv = next((l for l in LV if l["role"] == "conc" and l["tier"] == t), None)
                if lvv: req.append(lvv)
            elif rear[t]["egress"]:
                lvv = next((l for l in LV if l["index"] == rear[t]["level"]), None)
                if lvv: req.append(lvv)
        d_front_min = max([l["d0"] for l in req] + [0.0])
        for t in tiers:
            if t == 1 and rear[t]["egress"] and rear[t]["glass"]:
                d_front_min = max(d_front_min, rear[t]["glass"][0] + 0.05)
        Dp_max = (db - 0.4) - d_front_min
        wf_max = max(1.0, min(4.2, (Dp_max - 0.2 - 2 * CORE_WALL) / 2))
        load = 0.0
        for t in tiers:
            if t > 1:
                load += seats_tier[(seg, t)]
            elif rear[t]["egress"]:
                load += 0.35 * seats_tier[(seg, t)]
        need_total = load / (8.0 * 66.0) * 1.10
        base_n = 3 if kind == "straight" else 2
        nC = max(base_n, int(math.ceil(need_total / wf_max)))
        wf = round(max(min(wf_max, 1.8), min(wf_max, need_total / nC)), 2)
        wf = max(1.0, wf)
        depth = 2 * wf + 0.2 + 2 * CORE_WALL
        fr = [(j + 1) / (nC + 1) for j in range(nC)]
        if seg == "S":     # shallow stand: four cores, leaving the centre and the suites either side free
            fr = [0.14, 0.36, 0.64, 0.86]; nC = 4
            wf = round(max(1.0, min(wf_max, need_total / nC)), 2)
            depth = 2 * wf + 0.2 + 2 * CORE_WALL
        storeys = [LV[i + 1]["ffl"] - LV[i]["ffl"] for i in range(len(LV) - 1)]
        nrise = int(math.ceil(max(storeys) / 2 / 0.18))
        L_core = round(2.3 + 2.3 + nrise * STEP_GO + 2.0 + 2 * CORE_WALL, 2)
        cores = []
        for j, f in enumerate(fr):
            u = frac_u(G, seg, f)
            d_back = db - 0.4
            d_front = d_back - depth
            served = [l for l in LV if l["d0"] <= d_front + 0.01]
            if not served:
                continue
            topF = served[-1]["ffl"]
            lim = 400.0
            for dd in np.linspace(d_front, d_back, 6):
                c_ = ceiling_at(tiersU, dd, topF)
                if c_ is not None:
                    lim = min(lim, c_)
            top = min(topF + 3.2, lim - 0.05, ry(d_back) - 1.45)
            dc = (d_front + d_back) / 2
            L = L_core
            cores.append(dict(id=f"{seg}-{j + 1}", f=f, u=u, half=L / 2 * u_per_m(G, seg, dc), L=L, d0=d_front, d1=d_back, dc=dc, wf=wf,
                              levels=[l["index"] for l in served], top=round(top, 2), need=round(need_total, 2)))
        S["cores"] = cores
        PL["segs"][seg] = S
    return PL


# ---------------------------------------------------------------------------------------------- rooms
def make_rooms(G, PL):
    rooms = []
    for seg, S in PL["segs"].items():
        LV = S["levels"]; dbi = S["dbi"]
        ps = G["samples"](seg); ua, ub = ps[0], ps[-1]
        sg = 1 if ub > ua else -1
        ftou = lambda f: ua + (ub - ua) * f
        utof = lambda u: (u - ua) / (ub - ua)
        cores = S["cores"]
        for lv in LV:
            ffl, role, t = lv["ffl"], lv["role"], lv["tier"]
            d0, d1 = lv["d0"], dbi
            bands = []  # (name, d0, d1, default kind, label)
            corridors = []   # (f0, f1, d_from) radial corridors cutting back bands
            if role == "ground":
                vl = S["vom"][1]["d_land"]
                sp0 = max(d0 + 3.0, vl - 2.0) if vl - 2.0 > d0 + 3.0 else d0
                sp1 = min(sp0 + 12.0, d1 - 8.0)
                if sp0 > d0:
                    bands.append(("front", d0, sp0, "boh", "Under-stand stores"))
                bands.append(("spine", sp0, sp1, "concourse", "Ground-floor concourse"))
                if d1 - sp1 > 18:
                    bands.append(("back", sp1, sp1 + 8.0, "services", None))
                    bands.append(("back2", sp1 + 8.0, d1, "boh", "Back of house"))
                else:
                    bands.append(("back", sp1, d1, "services", None))
                if seg == "S":   # players' areas under the west part of the stand
                    bands = [("front", d0, d0 + 9.0, "boh", "Under-stand stores"), ("mid", d0 + 9.0, d0 + 17.0, "boh", "Stores"),
                             ("spine", d0 + 17.0, min(d0 + 25.0, d1 - 4.5), "concourse", "Ground-floor concourse"), ("back", min(d0 + 25.0, d1 - 4.5), d1, "services", None)]
                for g in S["gates"]:
                    hw = (g["w"] / 2 + 0.5) * u_per_m(G, seg, d1)
                    corridors.append((utof(g["u"] - sg * hw), utof(g["u"] + sg * hw), "gate", g["code"]))
            elif role == "rear":
                r = S["rear"][t]
                if r["glass"]:
                    gd = r["glass"][0]
                    gdi = max(gd, d0)
                    if d1 - gdi > 14:
                        bands.append(("boxes", gdi, gdi + 5.5, "boxes", "Executive boxes"))
                        bands.append(("corr", gdi + 5.5, gdi + 8.0, "concourse", "Box corridor"))
                        bands.append(("spine", gdi + 8.0, min(gdi + 15.0, d1), "concourse", "Tier %d rear concourse" % t))
                        if d1 - (gdi + 15.0) > 3.0:
                            bands.append(("back", gdi + 15.0, d1, "hospitality", "Hospitality lounge"))
                    elif d1 - gdi > 7:
                        bands.append(("boxes", gdi, gdi + 5.5, "boxes", "Executive boxes"))
                        bands.append(("corr", gdi + 5.5, d1, "concourse", "Box corridor"))
                    else:
                        bands.append(("boxes", gdi, d1, "boxes", "Executive boxes"))
                else:
                    if d1 - d0 > 8:
                        bands.append(("all", d0, d1, "hospitality" if not r["top"] else "boh", "Hospitality lounge" if not r["top"] else "Plant & roof void"))
                    else:
                        bands.append(("all", d0, d1, "boh", "Plant"))
            elif role == "conc":
                vl = S["vom"][t]["d_land"]
                sp0 = max(d0, min(vl, d1 - 3.0))
                sp1 = min(sp0 + 7.0, d1)
                if sp0 - d0 > 1.0:
                    bands.append(("front", d0, sp0, "services", None))
                bands.append(("spine", sp0, sp1, "concourse", "Tier %d concourse" % t))
                if d1 - sp1 > 3.0:
                    bands.append(("back", sp1, d1, "hospitality", "Hospitality lounge"))
            else:
                if d1 - d0 > 12:
                    bands.append(("all", d0, d1, "hospitality", "Lounges & offices"))
                else:
                    bands.append(("all", d0, d1, "boh", "Offices & plant"))
            for bname, b0, b1, kd, label in bands:
                if bname == "spine":
                    S.setdefault("spine", {})[lv["index"]] = (b0, b1)
                if role == "rear" and bname in ("corr", "spine"):
                    S.setdefault("rearc", {})[t] = ((b0 + b1) / 2)
            # vomitory stairs come down through the front band of this level
            vt = 1 if role == "ground" else (t if role == "conc" else None)
            if vt:
                for c_, hw_ in S["vom"][vt]["us"]:
                    hwm = hw_ * 1.0
                    corridors.append((utof(c_ - hwm), utof(c_ + hwm), "vom", vt))
            # core corridors through the back bands (aligned with the floor landing at the core's lower-u end)
            core_cuts = []
            for c in cores:
                if lv["index"] not in c["levels"]:
                    continue
                um = c["u"] - sg * (c["L"] / 2 - 3.7) * u_per_m(G, seg, c["dc"])
                hw = 1.3 * u_per_m(G, seg, c["dc"])
                core_cuts.append((utof(c["u"] - sg * c["half"]), utof(c["u"] + sg * c["half"]), c))
                corridors.append((utof(um - sg * hw), utof(um + sg * hw), "core", c["id"]))
            # bands reaching back past the cores are split at the cores' front line
            cd0 = min([c["d0"] for f0_, f1_, c in core_cuts], default=None)
            if cd0 is not None:
                nb_ = []
                for bname, b0, b1, kd, label in bands:
                    if b0 < cd0 - 2.0 and b1 > cd0 + 0.5:
                        nb_.append((bname, b0, cd0, kd, label)); nb_.append((bname + "_r", cd0, b1, kd, label))
                    elif b1 > cd0 + 0.5 and b0 >= cd0 - 2.0:
                        nb_.append((bname + "_r", b0, b1, kd, label))
                    else:
                        nb_.append((bname, b0, b1, kd, label))
                bands = nb_
            # build rooms band by band
            for bname, b0, b1, kd, label in bands:
                if b1 - b0 < 0.8:
                    continue
                cuts = []
                base_b = bname[:-2] if bname.endswith("_r") else bname
                if base_b in ("back", "back2", "all", "corr", "front", "mid", "spine", "boxes"):
                    for f0, f1, why, ref in corridors:
                        if why == "core" and (bname.endswith("_r") or base_b in ("spine", "boxes") or cd0 is None or b1 > cd0 + 0.5):
                            continue
                        if why == "core" and abs(b1 - cd0) > 0.5:
                            continue
                        if base_b in ("spine", "boxes") and why != "core":
                            continue
                        if why == "gate" and base_b not in ("back", "back2", "all"):
                            continue
                        if why == "vom" and base_b not in ("front", "mid"):
                            continue
                        cuts.append((min(f0, f1), max(f0, f1), "corridor", why, ref))
                if bname == "boxes":
                    # passages through the box row at block boundaries (fans from the walkway to the corridor)
                    bb = G["block_bounds"](seg)
                    for j, u in enumerate(bb):
                        hw = 1.2 * u_per_m(G, seg, b0)
                        if j == 0:
                            u = u + sg * hw
                        elif j == len(bb) - 1:
                            u = u - sg * hw
                        cuts.append((min(utof(u - hw), utof(u + hw)), max(utof(u - hw), utof(u + hw)), "corridor", "box", None))
                # cores occupy the very back
                for f0, f1, c in core_cuts:
                    if bname.endswith("_r") or (b0 >= c["d0"] - 0.01):
                        cuts.append((min(f0, f1), max(f0, f1), "core", "core", c["id"]))
                cuts.sort()
                # merge overlapping cuts (core wins)
                pieces = []
                cur = 0.0
                for f0, f1, ck, why, ref in cuts:
                    f0 = max(f0, 0.0); f1 = min(f1, 1.0)
                    if f1 <= cur + 1e-4:
                        continue
                    if f0 > cur:
                        pieces.append((cur, f0, "room", None, None))
                    pieces.append((max(f0, cur), f1, ck, why, ref))
                    cur = f1
                if cur < 1.0:
                    pieces.append((cur, 1.0, "room", None, None))
                for f0, f1, ck, why, ref in pieces:
                    if f1 - f0 < 1e-3:
                        continue
                    if ck == "room" and abs(ftou(f1) - ftou(f0)) / u_per_m(G, seg, (b0 + b1) / 2) < 1.5:
                        continue
                    if ck == "core":
                        rooms.append(dict(seg=seg, level=lv["index"], f0=f0, f1=f1, d0=b0, d1=b1, kind="core", name="Stair core " + ref, band=bname, core=ref))
                        continue
                    if ck == "corridor":
                        nm = {"gate": "Exit to " + str(ref or "gate"), "core": "Corridor to stair core", "box": "Passage", "vom": "Vomitory stair"}[why]
                        rooms.append(dict(seg=seg, level=lv["index"], f0=f0, f1=f1, d0=b0, d1=b1, kind="concourse", name=nm, band=bname))
                        continue
                    # plain room run: split into modules
                    if kd == "boxes":
                        span_m = abs(ftou(f1) - ftou(f0)) / u_per_m(G, seg, b0)
                        n = max(1, int(span_m / 4.6))
                        for k in range(n):
                            a_ = f0 + (f1 - f0) * k / n; b_ = f0 + (f1 - f0) * (k + 1) / n
                            rooms.append(dict(seg=seg, level=lv["index"], f0=a_, f1=b_, d0=b0, d1=b1, kind="boxes", name="Executive box", band=bname))
                    elif kd == "services":
                        span_m = abs(ftou(f1) - ftou(f0)) / u_per_m(G, seg, b0)
                        n = max(1, int(round(span_m / 11.0)))
                        for k in range(n):
                            a_ = f0 + (f1 - f0) * k / n; b_ = f0 + (f1 - f0) * (k + 1) / n
                            nm = ("Kiosk & bar", "Toilets")[(k + int(f0 * 97)) % 2]
                            rooms.append(dict(seg=seg, level=lv["index"], f0=a_, f1=b_, d0=b0, d1=b1, kind="services", name=nm, band=bname))
                    else:
                        rooms.append(dict(seg=seg, level=lv["index"], f0=f0, f1=f1, d0=b0, d1=b1, kind=kd, name=label, band=bname))
        # named overrides
        for nseg, ltag, band, f0, f1, name, kd, note in NAMED:
            if nseg != seg:
                continue
            lv = next((l for l in LV if l["tag"] == ltag), None)
            if lv is None:
                continue
            for r in rooms:
                if r["seg"] != seg or r["level"] != lv["index"]:
                    continue
                if band != "all" and r["band"].replace("_r", "") != band:
                    continue
                if r["kind"] in ("core",) or r["name"].startswith(("Corridor", "Exit", "Lobby", "Passage")):
                    continue
                if r["band"].startswith("spine"):
                    continue
                if r["f1"] <= f0 or r["f0"] >= f1:
                    continue
                # split the room at f0/f1 and rename the overlap
                if r["f0"] < f0 - 1e-4:
                    rooms.append(dict(r, f1=f0)); r["f0"] = f0
                if r["f1"] > f1 + 1e-4:
                    rooms.append(dict(r, f0=f1)); r["f1"] = f1
                r["name"] = name; r["kind"] = kd; r["note"] = note; r["named"] = True
    # merge adjacent identical named rooms (boxes stay separate)
    rooms.sort(key=lambda r: (r["seg"], r["level"], r["band"], r["d0"], r["f0"]))
    out = []
    for r in rooms:
        if out and r.get("named") and out[-1].get("named") and out[-1]["name"] == r["name"] and out[-1]["seg"] == r["seg"] and out[-1]["level"] == r["level"] \
                and abs(out[-1]["d0"] - r["d0"]) < 1e-3 and abs(out[-1]["d1"] - r["d1"]) < 1e-3 and abs(out[-1]["f1"] - r["f0"]) < 1e-4:
            out[-1]["f1"] = r["f1"]
            continue
        out.append(r)
    PL["rooms"] = out
    return out


# ---------------------------------------------------------------------------------------------- geometry
class Ex:
    """Extrusion helpers bound to the build_v2 geometry functions."""

    def __init__(self, G):
        self.G = G

    def P(self, seg, u, d, h):
        (x, z), _ = self.G["pt"](seg, u, d)
        return (x, z, h)

    def path(self, seg, u0, u1, step=5.0):
        if seg in self.G["STRAIGHT"]:
            return [u0, u1]
        n = max(1, int(math.ceil(abs(u1 - u0) / step)))
        return list(np.linspace(u0, u1, n + 1))

    def sweep(self, mb, seg, u0, u1, geom, caps=True, cap0="full", cap1="full", sides=True):
        """Sweep (d, h) polygons from u0 to u1 as solids. cap0/cap1: 'full' (whole profile), None, or a geometry."""
        if geom is None or geom.is_empty:
            return
        polys = [geom] if geom.geom_type == "Polygon" else [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
        us = self.path(seg, u0, u1)
        for poly in (polys if sides else []):
            if poly.area < 1e-4:
                continue
            poly = orient(poly, 1.0)
            rings = [list(poly.exterior.coords)[:-1]] + [list(r.coords)[:-1] for r in poly.interiors]
            for ring in rings:
                n = len(ring)
                for i in range(n):
                    a, b = ring[i], ring[(i + 1) % n]
                    nd, nh = (b[1] - a[1]), -(b[0] - a[0])
                    ln = math.hypot(nd, nh)
                    if ln < 1e-6:
                        continue
                    for k in range(len(us) - 1):
                        ua_, ub_ = us[k], us[k + 1]
                        out_h = outward(self.G, seg, (ua_ + ub_) / 2)
                        want = np.array([out_h[0] * nd, out_h[1] * nd, nh])
                        mb.face([self.P(seg, ua_, a[0], a[1]), self.P(seg, ua_, b[0], b[1]), self.P(seg, ub_, b[0], b[1]), self.P(seg, ub_, a[0], a[1])], up=want)
        if not caps:
            return
        for cg, uu, sgn in ((cap0, u0, -1), (cap1, u1, 1)):
            if cg is None:
                continue
            if isinstance(cg, str):
                cg = geom
            cps = [cg] if cg.geom_type == "Polygon" else [g for g in getattr(cg, "geoms", []) if g.geom_type == "Polygon"]
            tv = tangent(self.G, seg, uu, 10.0) * (1 if u1 > u0 else -1) * sgn
            for cp in cps:
                if cp.area < 1e-4:
                    continue
                tris = shapely.constrained_delaunay_triangles(orient(cp, 1.0))
                for tri in getattr(tris, "geoms", [tris]):
                    if tri.is_empty or tri.area < 1e-6:
                        continue
                    cs = list(tri.exterior.coords)[:3]
                    mb.face([self.P(seg, uu, c[0], c[1]) for c in cs], up=np.array([tv[0], tv[1], 0.0]))

    def sweep_runs(self, mb, seg, pieces, caps):
        """Sweep consecutive pieces [(u0, u1, geom)] sharing one side face per profile edge over its whole run."""
        runs = {}
        for i, (u0, u1, geom) in enumerate(pieces):
            polys = [geom] if geom.geom_type == "Polygon" else [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
            for poly in polys:
                if poly.area < 1e-4:
                    continue
                poly = orient(poly, 1.0)
                for ring in [poly.exterior] + list(poly.interiors):
                    cs = list(ring.coords)[:-1]
                    n = len(cs)
                    for k in range(n):
                        a = (round(cs[k][0], 3), round(cs[k][1], 3)); b = (round(cs[(k + 1) % n][0], 3), round(cs[(k + 1) % n][1], 3))
                        if a == b:
                            continue
                        runs.setdefault((a, b), []).append(i)
        for (a, b), idx in runs.items():
            idx.sort()
            start = idx[0]; prev = idx[0]
            groups = []
            for j in idx[1:]:
                if j == prev + 1 and abs(pieces[j][0] - pieces[prev][1]) < 1e-9:
                    prev = j
                    continue
                groups.append((start, prev)); start = j; prev = j
            groups.append((start, prev))
            nd, nh = (b[1] - a[1]), -(b[0] - a[0])
            for g0, g1 in groups:
                us = self.path(seg, pieces[g0][0], pieces[g1][1])
                for k in range(len(us) - 1):
                    ua_, ub_ = us[k], us[k + 1]
                    out_h = outward(self.G, seg, (ua_ + ub_) / 2)
                    want = np.array([out_h[0] * nd, out_h[1] * nd, nh])
                    mb.face([self.P(seg, ua_, a[0], a[1]), self.P(seg, ua_, b[0], b[1]), self.P(seg, ub_, b[0], b[1]), self.P(seg, ub_, a[0], a[1])], up=want)
        for (u0, u1, geom), (c0, c1) in zip(pieces, caps):
            self.sweep(mb, seg, u0, u1, geom, sides=False, cap0=c0, cap1=c1)

    def prism(self, mb, poly2d, O, A, N, thick):
        """Planar polygon in (a, h) on the plane through O spanned by A (horizontal unit) and Z, extruded by thick along N."""
        if poly2d is None or poly2d.is_empty:
            return
        polys = [poly2d] if poly2d.geom_type == "Polygon" else [g for g in getattr(poly2d, "geoms", []) if g.geom_type == "Polygon"]
        O = np.array(O, float); A = np.array(A, float); N = np.array(N, float)
        Z = np.array([0, 0, 1.0])
        V = lambda a, h, s: tuple(O + A * a + Z * h + N * s)
        for poly in polys:
            if poly.area < 1e-5:
                continue
            poly = orient(poly, 1.0)
            rings = [list(poly.exterior.coords)[:-1]] + [list(r.coords)[:-1] for r in poly.interiors]
            for ring in rings:
                n = len(ring)
                for i in range(n):
                    a, b = ring[i], ring[(i + 1) % n]
                    na, nh = (b[1] - a[1]), -(b[0] - a[0])
                    if math.hypot(na, nh) < 1e-7:
                        continue
                    want = A * na + Z * nh
                    mb.face([V(a[0], a[1], 0), V(b[0], b[1], 0), V(b[0], b[1], thick), V(a[0], a[1], thick)], up=want)
            tris = shapely.constrained_delaunay_triangles(poly)
            for tri in getattr(tris, "geoms", [tris]):
                if tri.is_empty or tri.area < 1e-7:
                    continue
                cs = list(tri.exterior.coords)[:3]
                mb.face([V(c[0], c[1], 0) for c in cs], up=-N)
                mb.face([V(c[0], c[1], thick) for c in cs], up=N)

    def lbox(self, mb, seg, u, d, h0, h1, du, dd, rot=0.0):
        """Box centred at (u, d) in the stand's local frame: du metres along the stand, dd metres in depth."""
        (x, z), nrm = self.G["pt"](seg, u, d)
        yaw = math.atan2(nrm[1], nrm[0]) + rot
        mb.box((x, z, (h0 + h1) / 2), (dd, du, h1 - h0), yaw, uv_scale=2.0)

    def lcyl(self, mb, seg, u, d, h0, h1, r, sides=8):
        (x, z), _ = self.G["pt"](seg, u, d)
        ring = [(x + r * math.cos(2 * math.pi * k / sides), z + r * math.sin(2 * math.pi * k / sides)) for k in range(sides)]
        for k in range(sides):
            a_, b_ = ring[k], ring[(k + 1) % sides]
            mb.face([(a_[0], a_[1], h0), (b_[0], b_[1], h0), (b_[0], b_[1], h1), (a_[0], a_[1], h1)], up=np.array([(a_[0] + b_[0]) / 2 - x, (a_[1] + b_[1]) / 2 - z, 0]))
        mb.face([(p[0], p[1], h1) for p in ring], up=np.array([0, 0, 1.0]))
        mb.face([(p[0], p[1], h0) for p in ring], up=np.array([0, 0, -1.0]))


def build(G, PL, mbs):
    """Emit the interior geometry into the mesh builders (keys: solid, walls, stairs, fin_<kind>, fit_light, fit_dark, lift)."""
    EX = Ex(G)
    stats = dict(pieces=0)
    for seg, S in PL["segs"].items():
        _build_seg(G, EX, PL, seg, S, mbs, stats)
    _build_tunnel_extras(G, EX, PL, mbs)
    _tunnel_housing(G, EX, mbs)
    print("interior pieces", stats["pieces"])


def _base_profile(G, PL, seg, S):
    """Union of the structural profile common to the whole stand (before local cuts)."""
    tiersU = S["_tiersU"]; dbi = S["dbi"]
    parts = [tiersU]
    parts.append(box(-0.23, -0.5, dbi, 0.0))                       # ground slab
    for lv in S["levels"]:
        if lv["role"] == "ground":
            continue
        parts.append(box(lv["d0"], lv["ffl"] - SLAB, dbi, lv["ffl"]))
    for t, r in S["rear"].items():
        parts.append(box(r["dB"], r["hB"] - 0.1, min(r["dB"] + 1.5, dbi), r["h"]))
        if r["wall"]:
            d_, h0_, h1_ = r["wall"]
            if r["top"] and S["roof"] != "low":
                parts.append(box(d_ + 0.06, h0_ - 0.1, min(d_ + 0.34, dbi), h1_ + 0.05))
            else:
                parts.append(box(d_ + 0.06, h0_ - 0.05, min(d_ + 0.34, dbi), h1_ + 0.05))
    return unary_union(parts)


def _vom_cut(G, S, t):
    v = S["vom"][t]
    d0v, d1v, h0, F, dl = v["d0v"], v["d1v"], v["h0"], v["F"], v["d_land"]
    recess = box(d0v + 0.06, h0 - 0.06, d1v + 0.06, 400)
    x0 = v["x0"]
    n = max(1, int(round((h0 - F) / STEP_RISE)))
    rise = (h0 - F) / n; go = (dl - x0) / n
    saw = [(min(d1v, x0) - 0.02, h0 - 0.06), (x0, h0 - 0.06)]
    for i in range(1, n + 1):
        saw += [(x0 + (i - 1) * go, h0 - i * rise), (x0 + i * go, h0 - i * rise)]
    saw[-1] = (dl, F)
    stair = Polygon(saw + [(dl, F - 0.3), (x0 + 0.3, h0 - 0.45), (min(d1v, x0) - 0.02, h0 - 0.45)]).buffer(0)
    parts = [Polygon([(x0, h0), (dl, F), (dl, F + 2.3), (x0, h0 + 2.3)]), box(dl - 0.01, F, dl + 1.6, F + 2.3)]
    if x0 > d1v:
        parts.append(box(d1v - 0.1, h0, x0, h0 + 2.3))
    clear = unary_union(parts)
    return recess, stair, clear


def _snap(g):
    return shapely.set_precision(g, 0.002)


def _clean(g):
    if g is None or g.is_empty:
        return None
    g = g.buffer(-0.004, join_style=2).buffer(0.004, join_style=2)
    polys = [p for p in ([g] if g.geom_type == "Polygon" else getattr(g, "geoms", [])) if p.geom_type == "Polygon" and p.area > 0.003]
    if not polys:
        return None
    return MultiPolygon(polys) if len(polys) > 1 else polys[0]


def _full_base(G, PL, seg, S):
    if "_full" not in S:
        S["_full"] = _snap(unary_union([_base_profile(G, PL, seg, S), leaf_poly(G, seg)]))
    return S["_full"]


def _piece_profile(G, S, act, full, tiersU):
    dbi, db = S["dbi"], S["db"]
    prof = full
    rec_list, stair_list, clear_list, other = [], [], [], []
    for kind, ref in act:
        if kind == "vom":
            rec, st, cl = _vom_cut(G, S, int(ref))
            rec_list.append(rec); stair_list.append(st); clear_list.append(cl)
        elif kind == "core":
            c = next(c for c in S["cores"] if c["id"] == ref)
            other.append(box(c["d0"] - 0.01, 0.0, dbi + 0.01, c["top"] + 0.3).difference(tiersU))
        elif kind == "tunnel":
            rt = TUNNEL
            other.append(box(-0.3, rt["deck"] - 0.06, G["row_d"](1, _tunnel_row(G)) + 0.06, 400))
            other.append(box(-0.3, 0.0, rt["d1"], rt["soffit"]))
        elif kind == "gate":
            other.append(box(db - 0.5, -0.5, db + 0.1, 3.6))
        elif kind == "bulge":
            other.append(box(db - 0.5, -0.5, db + 0.1, 27.8))
    if rec_list:
        prof = prof.difference(unary_union(rec_list))
    if stair_list:
        prof = unary_union([prof] + stair_list)
    if clear_list:
        prof = prof.difference(unary_union(clear_list))
    if other:
        prof = prof.difference(unary_union(other))
    return _snap(prof)


def _build_seg(G, EX, PL, seg, S, mbs, stats):
    ps = G["samples"](seg); ua, ub = ps[0], ps[-1]
    dbi, db = S["dbi"], S["db"]
    tiersU = S["_tiersU"]
    full = _full_base(G, PL, seg, S)
    feats = []
    for t, v in S["vom"].items():
        for c, hw in v["us"]:
            feats.append((min(c - hw, c + hw), max(c - hw, c + hw), "vom", t))
    for c in S["cores"]:
        feats.append((min(c["u"] - c["half"], c["u"] + c["half"]), max(c["u"] - c["half"], c["u"] + c["half"]), "core", c["id"]))
    for g in S["gates"]:
        hw = (g["w"] / 2) * u_per_m(G, seg, db)
        feats.append((min(g["u"] - hw, g["u"] + hw), max(g["u"] - hw, g["u"] + hw), "gate", g["code"]))
    if seg == TUNNEL["seg"]:
        feats.append((min(TUNNEL["u0"], TUNNEL["u1"]), max(TUNNEL["u0"], TUNNEL["u1"]), "tunnel", None))
    if seg == "E":
        feats.append((-22.0, 22.0, "bulge", None))
    lo, hi = min(ua, ub), max(ua, ub)
    bps = {lo, hi}
    for a, b, *_ in feats:
        for x in (a, b):
            if lo + 1e-6 < x < hi - 1e-6:
                bps.add(round(x, 6))
    bps = sorted(bps)
    pieces = []
    for i in range(len(bps) - 1):
        a, b = bps[i], bps[i + 1]
        if b - a < 1e-6:
            continue
        m = (a + b) / 2
        act = tuple(sorted((f[2], str(f[3])) for f in feats if f[0] <= m <= f[1]))
        if pieces and pieces[-1][2] == act:
            pieces[-1][1] = b
        else:
            pieces.append([a, b, act])
    cache = {}
    profs = []
    for a, b, act in pieces:
        if act not in cache:
            cache[act] = _piece_profile(G, S, act, full, tiersU)
        profs.append(cache[act])
    # neighbouring stands at the two ends (in u order lo..hi)
    order = [s_[0] for s_ in G["SEGS"]]
    i0 = order.index(seg)
    prev_s, next_s = order[i0 - 1], order[(i0 + 1) % len(order)]
    nb_lo, nb_hi = (prev_s, next_s) if ub > ua else (next_s, prev_s)
    end_lo = _full_base(G, PL, nb_lo, PL["segs"][nb_lo])
    end_hi = _full_base(G, PL, nb_hi, PL["segs"][nb_hi])
    caps = []
    for i, (a, b, act) in enumerate(pieces):
        P = profs[i]
        left = profs[i - 1] if i > 0 else end_lo
        right = profs[i + 1] if i + 1 < len(profs) else end_hi
        cap0 = _clean(P.difference(left)) if left is not P else None
        cap1 = _clean(P.difference(right)) if right is not P else None
        caps.append((cap0, cap1))
        stats["pieces"] += 1
    EX.sweep_runs(mbs["solid"], seg, [(a, b, profs[i]) for i, (a, b, act) in enumerate(pieces)], caps)
    # roof slab as its own solid (so the viewer can hide the roof); caps only where the neighbouring roof differs
    rp = _snap(roof_poly(G, seg))
    rl = _snap(roof_poly(G, nb_lo)); rh = _snap(roof_poly(G, nb_hi))
    EX.sweep(mbs["roof_solid"], seg, lo, hi, rp, cap0=_clean(rp.difference(rl)), cap1=_clean(rp.difference(rh)))
    base = _base_profile(G, PL, seg, S)
    _build_rooms(G, EX, PL, seg, S, mbs, unary_union([base, roof_poly(G, seg), leaf_poly(G, seg)]))
    for c in S["cores"]:
        _build_core(G, EX, seg, S, c, mbs)


def _tunnel_row(G):
    r = 0
    while G["row_y"](1, r) < TUNNEL["ymax"]:
        r += 1
    return r


def _room_ceiling(base, d, ffl):
    c = ceiling_at(base, d, ffl)
    return c if c is not None else ffl + 3.5


def _build_rooms(G, EX, PL, seg, S, mbs, base):
    ps = G["samples"](seg); ua, ub = ps[0], ps[-1]
    ftou = lambda f: ua + (ub - ua) * f
    LV = {l["index"]: l for l in S["levels"]}
    rooms = [r for r in PL["rooms"] if r["seg"] == seg]
    wall_mb = mbs["walls"]
    # finishes
    for r in rooms:
        lv = LV[r["level"]]; ffl = lv["ffl"]
        if r["kind"] == "core":
            continue
        u0, u1 = ftou(r["f0"]), ftou(r["f1"])
        mb = mbs["fin_" + r["kind"]]
        us = EX.path(seg, min(u0, u1), max(u0, u1))
        for k in range(len(us) - 1):
            mb.quad(EX.P(seg, us[k], r["d0"], ffl + 0.03), EX.P(seg, us[k + 1], r["d0"], ffl + 0.03),
                    EX.P(seg, us[k + 1], r["d1"], ffl + 0.03), EX.P(seg, us[k], r["d1"], ffl + 0.03), up=np.array([0, 0, 1.0]), scale=2.0)
    # walls: along constant d between bands and constant u between rooms
    by_level = {}
    for r in rooms:
        by_level.setdefault(r["level"], []).append(r)
    circ = lambda r: r["kind"] == "concourse"
    for li, rs in by_level.items():
        ffl = LV[li]["ffl"]
        # radial walls (constant f) between neighbouring rooms in the same band
        for r in rs:
            for r2 in rs:
                if r2 is r or abs(r2["f0"] - r["f1"]) > 1e-4 or abs(r2["d0"] - r["d0"]) > 1e-3 or abs(r2["d1"] - r["d1"]) > 1e-3:
                    continue
                if circ(r) and circ(r2):
                    continue
                if r["kind"] == "core" or r2["kind"] == "core":
                    continue
                _radial_wall(G, EX, seg, ftou(r["f1"]), r["d0"], r["d1"], ffl, base, wall_mb, door=not (r["kind"] == "boxes" and r2["kind"] == "boxes"))
        # along walls (constant d) at band boundaries: between rooms in different bands that touch
        bands = sorted({(round(r["d0"], 3), round(r["d1"], 3)) for r in rs})
        edges = sorted({round(r["d0"], 3) for r in rs} | {round(r["d1"], 3) for r in rs})
        for dE in edges:
            if dE >= S["dbi"] - 0.01:
                continue
            front_rooms = [r for r in rs if abs(r["d1"] - dE) < 1e-3]
            back_rooms = [r for r in rs if abs(r["d0"] - dE) < 1e-3]
            # walk the f-axis and put wall segments where the two sides are not both circulation
            fs = sorted({0.0, 1.0} | {r["f0"] for r in front_rooms + back_rooms} | {r["f1"] for r in front_rooms + back_rooms})
            for k in range(len(fs) - 1):
                fa, fb = fs[k], fs[k + 1]
                fm = (fa + fb) / 2
                A_ = next((r for r in front_rooms if r["f0"] <= fm <= r["f1"]), None)
                B_ = next((r for r in back_rooms if r["f0"] <= fm <= r["f1"]), None)
                if A_ is None and B_ is None:
                    continue
                if A_ is not None and B_ is not None and circ(A_) and circ(B_):
                    continue
                if (A_ and A_["kind"] == "core") or (B_ and B_["kind"] == "core"):
                    continue
                if A_ is None and B_ is not None and dE <= LV[li]["d0"] + 0.01 and LV[li]["role"] == "conc":
                    pass
                if A_ is None and B_ is not None and B_["kind"] == "boxes":
                    continue
                door = not ((A_ and A_["kind"] == "boxes") and B_ is None)
                kiosk = (A_ and A_["name"] == "Kiosk & bar") or (B_ and B_["name"] == "Kiosk & bar")
                _along_wall(G, EX, seg, ftou(fa), ftou(fb), dE, ffl, base, wall_mb, door=door, wide=kiosk)
    # fit-out
    for r in rooms:
        _fitout(G, EX, seg, S, r, LV[r["level"]], ftou, mbs, base)


def _radial_wall(G, EX, seg, u, d0, d1, ffl, base, mb, door=True):
    ds = np.linspace(d0, d1, max(2, int((d1 - d0) / 1.0) + 1))
    top = [(d, _room_ceiling(base, d, ffl)) for d in ds]
    poly = Polygon([(d0, ffl)] + top + [(d1, ffl)]).buffer(0)
    if door and d1 - d0 > 3.0:
        dm = (d0 + d1) / 2
        poly = poly.difference(box(dm - 0.9, ffl - 0.1, dm + 0.9, ffl + 2.3))
    if poly.is_empty:
        return
    t = 0.1 * u_per_m(G, seg, (d0 + d1) / 2)
    EX.sweep(mb, seg, u - t, u + t, poly)


def _along_wall(G, EX, seg, u0, u1, d, ffl, base, mb, door=True, wide=False):
    lo, hi = min(u0, u1), max(u0, u1)
    L = (hi - lo) / u_per_m(G, seg, d)
    if L < 0.3:
        return
    c = _room_ceiling(base, d, ffl)
    hc = c
    if hc - ffl < 0.5:
        return
    upm = u_per_m(G, seg, d)
    segs_ = [(lo, hi)]
    if door and L > 3.0:
        n = max(1, int(L / 12.0))
        gaps = []
        for k in range(n):
            m = lo + (hi - lo) * (k + 0.5) / n
            gw = (3.0 if wide else 0.9) * upm
            gaps.append((m - gw, m + gw))
        cur = lo; segs_ = []
        for g0, g1 in gaps:
            segs_.append((cur, g0)); cur = g1
        segs_.append((cur, hi))
        # lintels over the doors
        for g0, g1 in gaps:
            if hc - (ffl + 2.3) > 0.05:
                EX.sweep(mb, seg, g0, g1, box(d - 0.1, ffl + 2.3, d + 0.1, hc))
    for a, b in segs_:
        if b - a > 1e-4:
            EX.sweep(mb, seg, a, b, box(d - 0.1, ffl, d + 0.1, hc))


def _grid(G, seg, f0, f1, d0, d1, ftou, sp_u, sp_d, margin=1.2):
    u0, u1 = ftou(f0), ftou(f1)
    dm = (d0 + d1) / 2
    L = abs(u1 - u0) / u_per_m(G, seg, dm)
    nu = int((L - 2 * margin) / sp_u); nd = int((d1 - d0 - 2 * margin) / sp_d)
    out = []
    for i in range(max(0, nu)):
        for j in range(max(0, nd)):
            fu = (margin + sp_u * (i + 0.5) + (L - 2 * margin - nu * sp_u) / 2) / L
            d = d0 + margin + sp_d * (j + 0.5) + (d1 - d0 - 2 * margin - nd * sp_d) / 2
            out.append((u0 + (u1 - u0) * fu, d))
    return out


def _fitout(G, EX, seg, S, r, lv, ftou, mbs, base):
    ffl = lv["ffl"]; k = r["kind"]; nm = r["name"]
    L_ = mbs["fit_light"]; D_ = mbs["fit_dark"]
    d0, d1 = r["d0"], r["d1"]
    if d1 - d0 < 1.5:
        return
    if k in ("hospitality", "dining") and not nm.startswith("Plant"):
        sp = 3.4 if k == "hospitality" else 2.6
        for u, d in _grid(G, seg, r["f0"], r["f1"], d0, d1, ftou, sp, sp):
            if _room_ceiling(base, d, ffl) - ffl < 2.4:
                continue
            if k == "hospitality":
                EX.lcyl(L_, seg, u, d, ffl, ffl + 0.74, 0.8)
            else:
                EX.lbox(L_, seg, u, d, ffl, ffl + 0.74, 1.0, 1.0)
        # bar counter along the back
        um = ftou((r["f0"] + r["f1"]) / 2); Lm = abs(ftou(r["f1"]) - ftou(r["f0"])) / u_per_m(G, seg, d1)
        if Lm > 8 and d1 - d0 > 6:
            EX.lbox(D_, seg, um, d1 - 1.4, ffl, ffl + 1.1, min(10.0, Lm * 0.4), 0.8)
    elif k == "boxes":
        um = ftou((r["f0"] + r["f1"]) / 2)
        EX.lbox(L_, seg, um, d0 + 2.6, ffl, ffl + 0.74, 2.2, 1.0)
        EX.lbox(D_, seg, um, d1 - 0.6, ffl, ffl + 0.9, 2.4, 0.5)
    elif k == "services" and nm == "Kiosk & bar":
        um = ftou((r["f0"] + r["f1"]) / 2); Lm = abs(ftou(r["f1"]) - ftou(r["f0"])) / u_per_m(G, seg, d0)
        # counter facing the concourse (the concourse is on the d0 side for back bands, d1 side for front bands)
        dd = d0 + 0.9 if r["band"] != "front" else d1 - 0.9
        EX.lbox(D_, seg, um, dd, ffl, ffl + 1.05, max(2.0, Lm - 2.0), 0.7)
        EX.lbox(L_, seg, um, (d0 + d1) / 2 if r["band"] != "front" else (d0 + d1) / 2, ffl, ffl + 1.9, max(1.5, Lm - 3.0), 0.6)
    elif k == "services" and nm == "Toilets":
        um0, um1 = ftou(r["f0"]), ftou(r["f1"]); Lm = abs(um1 - um0) / u_per_m(G, seg, d0)
        n = max(1, int((Lm - 2.0) / 1.0))
        dd = d1 - 0.8 if r["band"] != "front" else d0 + 0.8
        for i in range(n):
            u = um0 + (um1 - um0) * (i + 1) / (n + 1)
            EX.lbox(L_, seg, u, dd, ffl, ffl + 2.0, 0.06, 1.5)
    elif k == "visitor":
        sp = 4.0
        for u, d in _grid(G, seg, r["f0"], r["f1"], d0, d1, ftou, sp, 3.2, 1.6):
            if _room_ceiling(base, d, ffl) - ffl < 2.4:
                continue
            if nm == "Megastore":
                EX.lbox(D_, seg, u, d, ffl, ffl + 1.8, 3.0, 0.6)
            else:
                EX.lbox(L_, seg, u, d, ffl, ffl + 1.2, 1.8, 0.9)
    elif k == "players" and "tunnel" not in nm:
        um0, um1 = ftou(r["f0"]), ftou(r["f1"])
        Lm = abs(um1 - um0) / u_per_m(G, seg, d0)
        um = (um0 + um1) / 2
        if "dressing" in nm:
            EX.lbox(L_, seg, um, d0 + 0.35, ffl, ffl + 0.45, Lm - 0.8, 0.45)
            EX.lbox(L_, seg, um, d1 - 0.35, ffl, ffl + 0.45, Lm - 0.8, 0.45)
            EX.lbox(D_, seg, um, (d0 + d1) / 2, ffl, ffl + 0.9, min(4.0, Lm - 3.0), 1.4)
        elif "Medical" in nm:
            for i in range(3):
                EX.lbox(L_, seg, um0 + (um1 - um0) * (i + 1) / 4, (d0 + d1) / 2, ffl, ffl + 0.75, 0.8, 2.0)
    elif k == "media":
        for u, d in _grid(G, seg, r["f0"], r["f1"], d0, d1, ftou, 2.0, 1.8, 1.0):
            if _room_ceiling(base, d, ffl) - ffl < 2.4:
                continue
            EX.lbox(D_, seg, u, d, ffl, ffl + 0.74, 1.6, 0.7)
    elif k == "boh" and ("Plant" in nm or "plant" in nm):
        for u, d in _grid(G, seg, r["f0"], r["f1"], d0, d1, ftou, 7.0, 4.0, 1.5):
            c_ = _room_ceiling(base, d, ffl)
            if c_ - ffl < 2.8:
                continue
            EX.lbox(D_, seg, u, d, ffl, ffl + min(2.4, c_ - ffl - 0.3), 4.0, 2.0)


def _core_frame(G, seg, c):
    u = c["u"]; dc = c["dc"]
    (x, z), nrm = G["pt"](seg, u, dc)
    T = tangent(G, seg, u, dc)
    ps = G["samples"](seg); sg = 1 if ps[-1] > ps[0] else -1
    T3 = np.array([T[0], T[1], 0.0]) * sg      # +t towards increasing u
    Nin = np.array([nrm[0], nrm[1], 0.0])       # towards the pitch
    return np.array([x, z, 0.0]), T3, Nin


def core_points(G, seg, c, ffl_list):
    """Landing and half-landing positions (plan x, z, h) used by the egress network."""
    O, T3, Nin = _core_frame(G, seg, c)
    L = c["L"] - 2 * CORE_WALL
    t0 = -L / 2
    land_t = t0 + 2.3 + 1.15
    half_t = t0 + L - 1.0
    out = []
    for i, f in enumerate(ffl_list):
        p = O + T3 * land_t
        out.append(("land", (p[0], p[1], f)))
        if i + 1 < len(ffl_list):
            q = O + T3 * half_t
            out.append(("half", (q[0], q[1], (f + ffl_list[i + 1]) / 2)))
    return out


def _build_core(G, EX, seg, S, c, mbs):
    O, T3, Nin = _core_frame(G, seg, c)
    LVmap = {l["index"]: l for l in S["levels"]}
    ffls = [LVmap[i]["ffl"] for i in c["levels"]]
    wf = c["wf"]; L = c["L"]; Dp = 2 * wf + 0.2 + 2 * CORE_WALL
    top = c["top"]
    W = mbs["walls"]; ST = mbs["stairs"]
    Z = np.array([0, 0, 1.0])
    half_L = L / 2; half_D = Dp / 2
    # outer walls: back (facade side), front (pitch side, with doors), two ends
    # local coordinates: t along T3, n along Nin (n>0 towards the pitch)
    def wall_tn(t0, t1, n0, n1, holes=()):
        # a wall slab spanning t in [t0,t1] at n in [n0,n1], from 0 to top
        if abs(t1 - t0) >= abs(n1 - n0):
            poly = box(t0, 0.0, t1, top)
            for (a, b, h0, h1) in holes:
                poly = poly.difference(box(a, h0, b, h1))
            EX.prism(W, poly, O + Nin * n0, T3, Nin, n1 - n0)
        else:
            poly = box(n0, 0.0, n1, top)
            for (a, b, h0, h1) in holes:
                poly = poly.difference(box(a, h0, b, h1))
            EX.prism(W, poly, O + T3 * t0, Nin, T3, t1 - t0)
    cw = CORE_WALL
    t_in0, t_in1 = -half_L + cw, half_L - cw
    n_in0, n_in1 = -half_D + cw, half_D - cw
    land0 = t_in0 + 2.3                    # lift | landing boundary
    land1 = land0 + 2.3                    # landing | flights
    half0 = t_in1 - 2.0                    # flights | half landing
    doors = [(land0 + 0.25, land1 - 0.25, f, f + 2.3) for f in ffls]
    wall_tn(-half_L, half_L, -half_D, -half_D + cw)                 # back
    wall_tn(-half_L, half_L, half_D - cw, half_D, holes=doors)      # front with doors
    wall_tn(-half_L, -half_L + cw, -half_D + cw, half_D - cw)       # end
    wall_tn(half_L - cw, half_L, -half_D + cw, half_D - cw)         # end
    # lift shaft wall with doors onto the landing
    lift_doors = [(-0.6, 0.6, f, f + 2.2) for f in ffls]
    poly = box(n_in0, 0.0, n_in1, top)
    for a, b, h0, h1 in lift_doors:
        poly = poly.difference(box(a, h0, b, h1))
    EX.prism(W, poly, O + T3 * land0, Nin, T3, 0.2)
    # lift car at the ground
    car = box(t_in0 + 0.3, 0.05, land0 - 0.3, 2.4)
    EX.prism(mbs["lift"], car, O + Nin * -0.8, T3, Nin, 1.6)
    # roof slab of the core
    EX.prism(ST, box(-half_L, top, half_L, top + 0.25), O + Nin * -half_D, T3, Nin, Dp)
    # landings and flights
    for i, f in enumerate(ffls):
        EX.prism(ST, box(land0 + 0.2, f - 0.25, land1, f), O + Nin * n_in0, T3, Nin, n_in1 - n_in0)
        if i + 1 >= len(ffls):
            continue
        f2 = ffls[i + 1]
        hm = (f + f2) / 2
        EX.prism(ST, box(half0, hm - 0.25, t_in1, hm), O + Nin * n_in0, T3, Nin, n_in1 - n_in0)
        for (ta, ha, tb, hb, n0, n1) in ((land1, f, half0, hm, n_in0, -0.1), (half0, hm, land1, f2, 0.1, n_in1)):
            rise = hb - ha
            n = max(1, int(round(abs(rise) / STEP_RISE)))
            run_avail = abs(tb - ta)
            go = min(0.30, run_avail / n)
            dirn = 1 if tb > ta else -1
            # flight starts at ta; steps rise towards tb; if the flight is shorter than the gap, extend the upper landing
            pts = []
            t_cur = ta
            h_cur = ha
            pts.append((t_cur, h_cur))
            for k in range(n):
                h_cur = ha + rise * (k + 1) / n
                pts.append((t_cur, h_cur))
                t_cur = t_cur + dirn * go
                pts.append((t_cur, h_cur))
            # extend top tread to the landing
            pts[-1] = (tb, hb)
            waist = [(tb, hb - 0.3), (ta + dirn * 0.3, ha - 0.25), (ta, ha - 0.25)]
            prof = Polygon(pts + waist).buffer(0)
            if prof.is_empty:
                continue
            EX.prism(ST, prof, O + Nin * n0, T3, Nin, n1 - n0)


def _build_tunnel_extras(G, EX, PL, mbs):
    """Players' tunnel housing in front of the Sir Bobby Charlton Stand (west end) and its side walls."""
    seg = TUNNEL["seg"]
    u0, u1 = TUNNEL["u0"], TUNNEL["u1"]
    um = (u0 + u1) / 2
    W = mbs["walls"]
    # side walls of the passage under the stand (beyond the deck) up to the tier soffit
    S = PL["segs"][seg]
    base = _base_profile(G, PL, seg, S)
    rt = _tunnel_row(G)
    for uu in (u0, u1):
        d0 = G["row_d"](1, rt)
        ds = np.linspace(d0, TUNNEL["d1"], 8)
        top = [(d, min(_room_ceiling(base, d, 0.0), 6.0)) for d in ds]
        poly = Polygon([(d0, 0.0)] + top + [(TUNNEL["d1"], 0.0)]).buffer(0)
        EX.sweep(W, seg, uu - 0.12, uu + 0.12, poly)


# ---------------------------------------------------------------------------------------------- export
def export_json(G, PL, out_dir):
    """interior.json for the web viewer: levels per stand, rooms (plan polygons, areas), cores, facade lines."""
    pt = G["pt"]
    rooms_out = []
    segs_out = {}
    for seg, S in PL["segs"].items():
        ps = G["samples"](seg); ua, ub = ps[0], ps[-1]
        ftou = lambda f: ua + (ub - ua) * f
        LV = {l["index"]: l for l in S["levels"]}
        ceilU = unary_union([_base_profile(G, PL, seg, S), roof_poly(G, seg), leaf_poly(G, seg)])
        fac = []
        for p in G["samples"](seg, 2.5) if seg not in G["STRAIGHT"] else list(np.linspace(ua, ub, 9)):
            (x, z), _ = pt(seg, p, S["db"]); fac.append([round(-x, 2), round(-z, 2)])
        segs_out[seg] = dict(stand=S["stand"], db=S["db"], facade=fac,
                             levels=[dict(i=l["index"], name=l["name"], ffl=round(l["ffl"], 2), role=l["role"], tier=l["tier"], d0=round(l["d0"], 2)) for l in S["levels"]],
                             cores=[dict(id=c["id"], wf=c["wf"], levels=c["levels"], c=[round(v, 2) for v in _xyz(pt, seg, c["u"], c["dc"], 0.0)]) for c in S["cores"]],
                             vom={str(t): dict(F=round(v["F"], 2), h0=round(v["h0"], 2)) for t, v in S["vom"].items()})
    for r in PL["rooms"]:
        seg = r["seg"]; S = PL["segs"][seg]
        ps = G["samples"](seg); ua, ub = ps[0], ps[-1]
        u0, u1 = ua + (ub - ua) * r["f0"], ua + (ub - ua) * r["f1"]
        n = 2 if seg in G["STRAIGHT"] else max(2, int(abs(u1 - u0) / 3) + 2)
        us = list(np.linspace(u0, u1, n))
        poly = [pt(seg, u, r["d0"])[0] for u in us] + [pt(seg, u, r["d1"])[0] for u in us[::-1]]
        P = Polygon(poly)
        lv = next(l for l in S["levels"] if l["index"] == r["level"])
        um, dm = (u0 + u1) / 2, (r["d0"] + r["d1"]) / 2
        cU = ceiling_at(unary_union([_base_profile(G, PL, seg, S), roof_poly(G, seg)]), dm, lv["ffl"]) if False else None
        c = pt(seg, um, dm)[0]
        rooms_out.append(dict(seg=seg, lv=r["level"], ffl=round(lv["ffl"], 2), name=r["name"], kind=r["kind"], note=r.get("note", ""),
                              named=bool(r.get("named")), area=round(P.area, 1),
                              poly=[[round(-x, 2), round(-z, 2)] for x, z in poly], c=[round(-c[0], 2), round(lv["ffl"], 2), round(-c[1], 2)]))
    out = dict(version=1, note="Indicative interior generated with the model: levels follow the bowl geometry, room names and areas from the club's published event spaces, layouts are not survey data.",
               kinds=PL["kinds"], segs=segs_out, rooms=rooms_out, tunnel=dict(seg=TUNNEL["seg"], u0=TUNNEL["u0"], u1=TUNNEL["u1"]),
               poche=["Structure_Solid", "Roof_Solid", "Interior_Walls", "Interior_Stairs"])
    with open(f"{out_dir}/interior.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print("interior.json rooms", len(rooms_out))


def _xyz(pt, seg, u, d, h):
    (x, z), _ = pt(seg, u, d)
    return (-x, h, -z)


def _tunnel_housing(G, EX, mbs):
    seg = TUNNEL["seg"]
    u0, u1 = min(TUNNEL["u0"], TUNNEL["u1"]), max(TUNNEL["u0"], TUNNEL["u1"])
    um = (u0 + u1) / 2; w = u1 - u0
    cd = mbs["concrete_dark"]
    # side walls and roof of the tunnel mouth, standing on the pitch surround in front of the stand
    for uu in (u0 - 0.15, u1 + 0.15):
        EX.lbox(cd, seg, uu, -1.3, 0.0, TUNNEL["deck"], 0.3, 2.1)
    EX.lbox(cd, seg, um, -1.3, TUNNEL["soffit"], TUNNEL["deck"], w + 0.6, 2.1)
    # retractable tunnel canopy out towards the touchline
    pt = G["pt"]
    r = w / 2 + 0.1
    n = 10
    for k in range(n):
        a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
        def P(a, d):
            (x, z), _ = pt(seg, um + r * math.cos(a), d)
            return (x, z, r * math.sin(a) * 1.25)
        mbs["dugout"].quad(P(a0, -2.4), P(a1, -2.4), P(a1, -5.4), P(a0, -5.4))
    for d in (-2.4, -3.9, -5.4):
        for k in range(n):
            a0, a1 = math.pi * k / n, math.pi * (k + 1) / n
            (x0, z0), _ = pt(seg, um + r * math.cos(a0), d); (x1, z1), _ = pt(seg, um + r * math.cos(a1), d)
            mbs["steel_grey"].tube((x0, z0, r * math.sin(a0) * 1.25), (x1, z1, r * math.sin(a1) * 1.25), 0.05, 6)
