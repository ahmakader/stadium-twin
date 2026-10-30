"""Egress network for the Old Trafford model, v3 (matches the modelled interior).

Nodes: aisle (stepped gangway points), vom (vomitory and the foot of its stair), conc (concourses, rear concourses),
rear (walkway behind the top row of a tier), ground (ground-floor concourse), land / half (stair-core landings),
out (place of safety beyond a gate), pitch (pitch as a place of reasonable safety).
Edges: 0 level, 1 stepped (gangways, vomitory stairs, core flights), 2 exit gate, 3 evacuation lift, 4 pitch gate.
Widths: radial gangways 1.2 m, vomitories 3.2 m, core flights and gates sized by the Green Guide capacity method
(8 min at 66 / 82 persons per metre per minute, 10 % margin)."""
import math, json
import numpy as np


def build_egress(G, pos, yaw, meta, extra, blocks, out_dir, PL):
    import interior as INT
    pt, SEGS, SEG, STRAIGHT, CORNER = G["pt"], G["SEGS"], G["SEG"], G["STRAIGHT"], G["CORNER"]
    treads, tier_back, roof_y, ROOFS, VOMS, VOMR = G["treads"], G["tier_back"], G["roof_y"], G["ROOFS"], G["VOMS"], G["VOMR"]
    block_bounds, samples, R = G["block_bounds"], G["samples"], G["R"]
    nodes, edges = [], []

    def node(x, z, h, kind, seg, tier, label=""):
        nodes.append([float(x), float(z), float(h), kind, seg, tier, label])
        return len(nodes) - 1

    def nodeP(seg, u, d, h, kind, tier, label=""):
        (x, z), _ = pt(seg, u, d)
        return node(x, z, h, kind, seg, tier, label)

    def edge(a, b, kind, width, length=None):
        if length is None:
            A_, B_ = nodes[a], nodes[b]
            length = math.dist(A_[:3], B_[:3])
        edges.append([a, b, kind, round(width, 2), round(max(length, 0.5), 2)])

    def nearest(lst, n):
        x, z, h = nodes[n][:3]
        return min(lst, key=lambda m: (nodes[m][0] - x) ** 2 + (nodes[m][1] - z) ** 2 + 4 * (nodes[m][2] - h) ** 2)

    order = [s_[0] for s_ in SEGS]
    tiers_of = {s_[0]: s_[4] for s_ in SEGS}
    aisles, lateral, conc, ground, walk, rconc = {}, {}, {}, {}, {}, {}
    for seg, kind, stand, code, tiers, roof, nb, _, style in SEGS:
        S = PL["segs"][seg]
        bounds = block_bounds(seg)
        db = S["db"]
        LV = {l["index"]: l for l in S["levels"]}
        # ground-floor concourse
        g_sp = S["spine"][0]
        gd = (g_sp[0] + g_sp[1]) / 2
        gl = [nodeP(seg, u, gd, 0.0, "ground", 0) for u in bounds]
        for i in range(len(gl) - 1):
            edge(gl[i], gl[i + 1], 0, 8.0)
        ground[seg] = gl
        for g in S["gates"]:
            gi = min(range(len(bounds)), key=lambda i: abs(bounds[i] - g["u"]))
            on = nodeP(seg, g["u"], db + 10.0, 0.0, "out", 0, g["code"])
            sn = nodeP(seg, g["u"], gd, 0.0, "ground", 0)
            edge(gl[gi], sn, 0, 8.0)
            edge(sn, on, 2, g["w"], length=(db - gd) + 10.0)
        i0 = order.index(seg)
        prev_s, next_s = order[i0 - 1], order[(i0 + 1) % len(order)]
        for t in tiers:
            T = treads(seg, t)
            rows = [k for k, tr in enumerate(T) if tr[3] == "row"]
            last = rows[-1]
            idxs = list(range(0, last + 1, 2))
            if idxs[-1] != last:
                idxs.append(last)
            v = S["vom"][t]
            r0v = v["r0"]
            if r0v not in idxs:
                idxs = sorted(set(idxs + [r0v]))
            dB, hB = tier_back(seg, t)
            rr = S["rear"][t]
            # concourse this tier's vomitories lead to (upper tiers)
            if t > 1:
                li = next(l["index"] for l in S["levels"] if l["role"] == "conc" and l["tier"] == t)
                sp = S["spine"][li]
                cd = (sp[0] + sp[1]) / 2
                cl = [nodeP(seg, u, cd, v["F"], "conc", t) for u in bounds]
                for i in range(len(cl) - 1):
                    edge(cl[i], cl[i + 1], 0, 6.0)
                conc[(seg, t)] = cl
            # walkway behind the top row and the corridor / rear concourse behind the boxes
            if rr["egress"]:
                wl = [nodeP(seg, u, dB + 0.75, rr["h"], "rear", t) for u in bounds]
                for i in range(len(wl) - 1):
                    edge(wl[i], wl[i + 1], 0, 1.5)
                walk[(seg, t)] = wl
                if t in S.get("rearc", {}):
                    rd = S["rearc"][t]
                    rl = [nodeP(seg, u, rd, rr["h"], "conc", t) for u in bounds]
                    for i in range(len(rl) - 1):
                        edge(rl[i], rl[i + 1], 0, 4.0)
                    rconc[(seg, t)] = rl
                    for k in range(len(bounds)):      # passages through the box row at the block boundaries (and the stand ends)
                        edge(wl[k], rl[k], 0, 2.4)
            for k, u in enumerate(bounds):
                if 0 < k < len(bounds) - 1:
                    w = 1.2
                else:
                    nb_s = prev_s if k == 0 else next_s
                    w = 0.6 if t in tiers_of[nb_s] else 1.2
                an = {}
                for r in idxs:
                    d0, d1, y, _ = T[r]
                    an[r] = nodeP(seg, u, d0 + 0.4, y, "aisle", t)
                for i in range(len(idxs) - 1):
                    edge(an[idxs[i]], an[idxs[i + 1]], 1, w)
                if rr["egress"]:
                    edge(an[last], walk[(seg, t)][k], 0, w)
                aisles[(seg, t, k)] = an
                if 0 < k < len(bounds) - 1:
                    vn = nodeP(seg, u, min(v["d1v"], v["x0"]) - 0.4, v["h0"], "vom", t)
                    edge(an[r0v], vn, 0, 3.2)
                    ln = nodeP(seg, u, v["d_land"] + 0.8, v["F"], "vom", t)
                    edge(vn, ln, 1, 3.2, length=math.hypot(v["run"], v["h0"] - v["F"]) + 1.0)
                    if t == 1:
                        edge(ln, gl[k], 0, 3.2)
                    else:
                        edge(ln, conc[(seg, t)][k], 0, 3.2)
                if t == 1 and kind == "straight" and 0 < k < len(bounds) - 1:
                    pn = nodeP(seg, u, -5.0, 0.0, "pitch", 0)
                    edge(an[0], pn, 4, 1.2, length=6.0)
            if t > 1:
                fronts = [aisles[(seg, t, k)][0] for k in range(len(bounds))]
                for i in range(len(fronts) - 1):
                    edge(fronts[i], fronts[i + 1], 0, 1.5)
                lateral[(seg, t)] = fronts
        # stair cores
        for c in S["cores"]:
            ffls = [LV[i]["ffl"] for i in c["levels"]]
            pts_ = INT.core_points(G, seg, c, ffls)
            lands, halfs = [], []
            for kind_, (x, z, h) in pts_:
                if kind_ == "land":
                    lands.append(node(x, z, h, "land", seg, 0, c["id"]))
                else:
                    halfs.append(node(x, z, h, "half", seg, 0, c["id"]))
            for i in range(len(lands) - 1):
                edge(lands[i], halfs[i], 1, c["wf"], length=math.dist(nodes[lands[i]][:3], nodes[halfs[i]][:3]) * 1.1)
                edge(halfs[i], lands[i + 1], 1, c["wf"], length=math.dist(nodes[halfs[i]][:3], nodes[lands[i + 1]][:3]) * 1.1)
            for i in range(1, len(lands)):
                edge(lands[i], lands[0], 3, 1.1, length=ffls[i] + 4.0)
            for i, li in enumerate(c["levels"]):
                lv = LV[li]
                tgt = None
                if lv["role"] == "ground":
                    tgt = nearest(gl, lands[i])
                elif lv["role"] == "conc" and (seg, lv["tier"]) in conc:
                    tgt = nearest(conc[(seg, lv["tier"])], lands[i])
                elif lv["role"] == "rear" and (seg, lv["tier"]) in walk:
                    tgt = nearest(rconc.get((seg, lv["tier"]), walk[(seg, lv["tier"])]), lands[i])
                if tgt is not None:
                    edge(tgt, lands[i], 0, 2.4)
    # links between neighbouring stands
    for i, s in enumerate(order):
        n2 = order[(i + 1) % len(order)]
        edge(ground[s][-1], ground[n2][0], 0, 6.0)
        for t in (1, 2, 3):
            for D, w in ((conc, 4.0), (rconc, 3.0)):
                if (s, t) in D and (n2, t) in D and abs(nodes[D[(s, t)][-1]][2] - nodes[D[(n2, t)][0]][2]) <= 1.2:
                    edge(D[(s, t)][-1], D[(n2, t)][0], 0, w)
            if (s, t) in lateral and (n2, t) in lateral:
                edge(lateral[(s, t)][-1], lateral[(n2, t)][0], 0, 1.5)
    # ceiling above each node (roof or soffit for the seating; interior storey height inside)
    roof_under = []
    for n_ in nodes:
        x, z, h, kind, seg, tier, _ = n_
        Rr = ROOFS[SEG[seg][5]]
        if kind in ("aisle", "rear"):
            d = plan_d(G, seg, x, z)
            ceil = roof_y(SEG[seg][5], d) - 1.4 if Rr["df"] <= d <= Rr["db"] else -1.0
            if (tier + 1) in SEG[seg][4]:
                (sd, sy), _ = G["soffit"](seg, tier + 1)
                if d >= sd:
                    ceil = G["soffit_y"](seg, tier + 1, d)
            roof_under.append(round(ceil, 2))
        elif kind in ("conc", "vom", "ground", "land", "half"):
            roof_under.append(round(h + 4.5, 2))
        else:
            roof_under.append(-1.0)
    # seat -> entry node
    N = len(pos)
    entry = np.zeros(N, np.uint16); rdist = np.zeros(N, np.uint8)
    for i in range(N):
        b = blocks[meta[i][0]]
        seg, t, bi = b["seg"], b["tier"], b["index"]
        row = meta[i][1] - 1
        x, z = pos[i][0], pos[i][1]
        ty = extra[i][2]
        if ty in (1, 2):
            lst = walk.get((seg, t)) or conc.get((seg, t))
            if lst:
                best = min(lst, key=lambda m: (nodes[m][0] - x) ** 2 + (nodes[m][1] - z) ** 2)
                entry[i] = best
                rdist[i] = min(255, int(math.hypot(nodes[best][0] - x, nodes[best][1] - z) * 10))
                continue
        bounds = block_bounds(seg)
        u = seat_u(G, seg, x, z)
        kL, kR = bi - 1, bi
        dL, dR = abs(u - bounds[kL]), abs(u - bounds[kR])
        k = kL if dL <= dR else kR
        an = aisles[(seg, t, k)]
        rk = min(an.keys(), key=lambda r: abs(r - row))
        entry[i] = an[rk]
        dist_m = min(dL, dR) * (1.0 if seg in STRAIGHT else math.radians(1) * (R + math.hypot(*np.subtract((x, z), CORNER[seg][0])) - R))
        rdist[i] = min(255, int(max(0.3, dist_m) * 10))
    roofs = {}
    for seg, kind, stand, code, tiers, roof, nb, _, style in SEGS:
        Rr = ROOFS[roof]
        ps = samples(seg, 5.0)
        if seg in STRAIGHT:
            ps = list(np.linspace(ps[0], ps[-1], 7))
        front, back = [], []
        for p in ps:
            (x, z), _ = pt(seg, p, Rr["df"] + 7.0); front.append([round(-x, 2), round(roof_y(roof, Rr["df"] + 7.0) - 1.4, 2), round(-z, 2)])
            (x, z), _ = pt(seg, p, Rr["db"]); back.append([round(-x, 2), round(roof_y(roof, Rr["db"]) - 1.4, 2), round(-z, 2)])
        L_front = sum(math.dist(front[i], front[i + 1]) for i in range(len(front) - 1))
        L_back = sum(math.dist(back[i], back[i + 1]) for i in range(len(back) - 1))
        area = 0.5 * (L_front + L_back) * (Rr["db"] - Rr["df"] - 7.0)
        roofs[seg] = dict(front=front, back=back, front_len=round(L_front, 1), area=round(area, 1), stand=SEG[seg][2])
    out = dict(
        version=3,
        note="Egress network generated with the model and its interior. Coordinates in three.js metres (x, height, z). Edge kinds: 0 level, 1 stepped, 2 exit gate, 3 evacuation lift, 4 pitch gate.",
        nodes=[[round(-n_[0], 2), round(n_[2], 2), round(-n_[1], 2), n_[3], n_[4], n_[5], n_[6]] for n_ in nodes],
        roofUnder=roof_under, edges=edges, roofs=roofs, segOrder=order, stands={s[0]: s[2] for s in SEGS},
    )
    with open(f"{out_dir}/egress.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    with open(f"{out_dir}/egress.bin", "wb") as f:
        f.write(entry.tobytes()); f.write(rdist.tobytes())
    kinds = {}
    for e in edges: kinds[e[2]] = kinds.get(e[2], 0) + 1
    gate_w = sum(e[3] for e in edges if e[2] == 2)
    print("egress nodes", len(nodes), "edges", len(edges), kinds, "total gate width", round(gate_w, 1), "m")


def plan_d(G, seg, x, z):
    A, B, R, STRAIGHT, CORNER = G["A"], G["B"], G["R"], G["STRAIGHT"], G["CORNER"]
    if seg in STRAIGHT:
        ax, sg, _ = STRAIGHT[seg]
        return (z * sg - B) if ax == "x" else (x * sg - A)
    (cx, cz), _ = CORNER[seg]
    return math.hypot(x - cx, z - cz) - R


def seat_u(G, seg, x, z):
    STRAIGHT, CORNER = G["STRAIGHT"], G["CORNER"]
    if seg in STRAIGHT:
        return x if STRAIGHT[seg][0] == "x" else z
    (cx, cz), (a0, a1) = CORNER[seg]
    a = math.degrees(math.atan2(z - cz, x - cx))
    while a < min(a0, a1) - 1: a += 360
    while a > max(a0, a1) + 1: a -= 360
    return a
