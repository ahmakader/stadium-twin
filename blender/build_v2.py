"""Old Trafford (concept) — procedural build v2 for Blender 5.x.

What's new vs v1:
  * Rakes designed row-by-row for sightline C-values (Green Guide method), capped at 34 deg.
  * Per-seat sightline data: C-value, balcony check, overhang cut-off height.
  * Accessibility: wheelchair platforms with companion seats (NW/NE quadrants), easy-access aisle seats, step counts.
  * Seating zones (home end, family, away, safe standing, hospitality, accessible) + club-style block codes.
  * Architecture matched to reference photos: exposed white tubular roof trusses (parallel on the north,
    radial in the quadrants, three box-truss towers with bowed trusses on East Stand / Stretford End),
    curved teal glass East Stand facade, white corner towers, red-brick piers, low south stand,
    railway and terraced houses, east forecourt with the football paving.
  * PBR materials (colour / normal / roughness) and no coplanar overlapping faces.

Coordinates: metres, Blender Z-up. Plan (x, z) -> Blender (X, Y). -Y = North (SAF stand), +X = East.
three.js after glTF export: (x, height, -z_plan).
"""
import bpy, math, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(HERE, "..", "out")
TEX = os.environ.get("TEX_DIR", os.path.join(HERE, "tex"))
os.makedirs(OUT, exist_ok=True)
CLUB_LETTERING = False
INTERIOR = True            # closed-solid interior (floors, cores, rooms) for sections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import interior as INT
PLAN = None   # club-name lettering is a trademark; keep off for public builds

# ---------------------------------------------------------------- layout
A, B, R = 58.5, 40.0, 9.0           # inner rounded rect = lower-tier front line
LS, WS = A - R, B - R
FOCUS = 6.0                        # tier-1 front line to touchline / goal line
EYE, EYE_STAND, EYE_WHEEL = 1.20, 1.65, 1.25

TIER_SPEC = {   # front d, min front height, tread, design C, riser limits, default rows
    1: dict(d0=0.0, y0=0.9, dr=0.80, C=0.060, nmin=0.15, nmax=0.55, rows=32),
    2: dict(d0=23.0, y0=17.0, dr=0.82, C=0.090, nmin=0.25, nmax=0.55, rows=26),
    3: dict(d0=46.0, y0=32.5, dr=0.85, C=0.090, nmin=0.25, nmax=0.57, rows=22),
}
ROOFS = {   # front edge d, front height, back height, back (facade) d.  high: 58.5 m cantilever
    "high": dict(df=8.0, yf=46.0, yb=57.0, db=66.5),
    "mid":  dict(df=2.0, yf=36.5, yb=34.0, db=50.0),
    "low":  dict(df=3.0, yf=24.5, yb=27.5, db=37.0),
}
#        seg   kind        stand                       code tiers      roof   nb rows override        facade style
SEGS = [
    ("N",  "straight", "Sir Alex Ferguson Stand",  "N",  [1, 2, 3], "high", 7, {}, "north"),
    ("NE", "corner",   "North-East Quadrant",      "NE", [1, 2, 3], "high", 6, {}, "quad_glass"),
    ("E",  "straight", "East Stand",               "E",  [1, 2],    "mid",  5, {1: 34, 2: 24}, "east"),
    ("SE", "corner",   "South-East Quadrant",      "SE", [1],       "low",  6, {}, "quad_low"),
    ("S",  "straight", "Sir Bobby Charlton Stand", "S",  [1],       "low",  7, {1: 40}, "south"),
    ("SW", "corner",   "South-West Quadrant",      "SW", [1],       "low",  6, {}, "quad_low"),
    ("W",  "straight", "Stretford End",            "W",  [1, 2],    "mid",  5, {1: 34, 2: 24}, "west"),
    ("NW", "corner",   "North-West Quadrant",      "NW", [1, 2, 3], "high", 6, {}, "quad_glass"),
]
SEG = {s[0]: s for s in SEGS}
CORNER = {"NE": ((LS, -WS), (-90, 0)), "SE": ((LS, WS), (0, 90)), "SW": ((-LS, WS), (90, 180)), "NW": ((-LS, -WS), (180, 270))}
STRAIGHT = {"N": ("x", -1, (-LS, LS)), "E": ("z", +1, (-WS, WS)), "S": ("x", +1, (LS, -LS)), "W": ("z", -1, (WS, -WS))}
PLATFORM_SEGS = {"NE", "NW"}       # accessible platforms at the back of the lower tier
PLATFORM_ROWS = 3                  # rows replaced by the platform deck


def pt(seg, p, d):
    if seg in STRAIGHT:
        ax, sg, _ = STRAIGHT[seg]
        if ax == "x":
            return (p, sg * (B + d)), (0.0, -sg)
        return (sg * (A + d), p), (-sg, 0.0)
    (cx, cz), _ = CORNER[seg]
    t = math.radians(p); r = R + d
    return (cx + r * math.cos(t), cz + r * math.sin(t)), (-math.cos(t), -math.sin(t))


def samples(seg, step_deg=2.5):
    if seg in STRAIGHT:
        return list(STRAIGHT[seg][2])
    a0, a1 = CORNER[seg][1]
    n = int(abs(a1 - a0) / step_deg)
    return list(np.linspace(a0, a1, n + 1))


def seg_len(seg, d):
    if seg in STRAIGHT:
        a, b = STRAIGHT[seg][2]; return abs(b - a)
    return math.radians(90) * (R + d)


def nrows(seg, t):
    return SEG[seg][7].get(t, TIER_SPEC[t]["rows"])


# ---------------------------------------------------------------- rake design (sightlines)
RAKE = {}


def design_rakes():
    """Tread heights row by row so each row sees the focus point C metres over the head in front."""
    for t in (1, 2, 3):
        sp = TIER_SPEC[t]
        y0 = sp["y0"]
        if t > 1:  # sit high enough above the tier below where it overhangs
            maxrows = max(nrows(sg[0], t - 1) for sg in SEGS if (t - 1) in sg[4] and t in sg[4])
            below = RAKE[t - 1][:maxrows]
            for r, yb in enumerate(below):
                d = TIER_SPEC[t - 1]["d0"] + r * TIER_SPEC[t - 1]["dr"]
                if d >= sp["d0"] - 0.5:
                    y0 = max(y0, round(yb + 4.9, 2))
                    break
        ys = [y0]
        for r in range(45):
            D = FOCUS + sp["d0"] + r * sp["dr"] + 0.45
            E = ys[-1] + EYE
            need = (E + sp["C"]) * (D + sp["dr"]) / D - E
            ys.append(round(ys[-1] + min(max(need, sp["nmin"]), sp["nmax"]), 3))
        RAKE[t] = ys
        sp["y0"] = y0


def row_d(t, r):
    return TIER_SPEC[t]["d0"] + r * TIER_SPEC[t]["dr"]


def row_y(t, r):
    return RAKE[t][r]


def treads(seg, t):
    """List of (d_front, d_back, y, kind) for the stepped surface; platforms merge the last rows."""
    sp = TIER_SPEC[t]; n = nrows(seg, t)
    out = []
    plat = (t == 1 and seg in PLATFORM_SEGS)
    last = n - PLATFORM_ROWS if plat else n
    for r in range(last):
        out.append((row_d(t, r), row_d(t, r + 1), row_y(t, r), "row"))
    if plat:
        out.append((row_d(t, last), row_d(t, n), row_y(t, n - 1), "platform"))
    return out


def tier_back(seg, t):
    tr = treads(seg, t)
    return tr[-1][1], tr[-1][2]


def soffit(seg, t):
    """Underside line of tier t (t > 1): from fascia bottom to back underside."""
    sp = TIER_SPEC[t]; dB, hB = tier_back(seg, t)
    return (sp["d0"] - 0.4, sp["y0"] - 2.2), (dB, hB - 2.0)


def soffit_y(seg, t, d):
    (d0, y0), (d1, y1) = soffit(seg, t)
    return y0 + (y1 - y0) * (d - d0) / (d1 - d0)


def roof_y(roof, d):
    r = ROOFS[roof]
    return r["yf"] + (r["yb"] - r["yf"]) * (d - r["df"]) / (r["db"] - r["df"])


def H(x, z, h):
    return (x, z, h)


# ---------------------------------------------------------------- mesh builder
class MB:
    def __init__(self):
        self.v, self.f, self.uv = [], [], []

    def face(self, pts, uvs=None, up=None, scale=4.0):
        pts = [tuple(map(float, p)) for p in pts]
        a, b, c = (np.array(pts[i]) for i in range(3))
        nrm = np.cross(b - a, c - a)
        if np.linalg.norm(nrm) < 1e-9:
            return
        if up is not None and np.dot(nrm, up) < 0:
            pts = pts[::-1]
            if uvs: uvs = uvs[::-1]
        if uvs is None:
            n = np.abs(nrm); ax = int(np.argmax(n)); ij = [k for k in range(3) if k != ax]
            uvs = [(p[ij[0]] / scale, p[ij[1]] / scale) for p in pts]
        i0 = len(self.v)
        self.v += pts; self.uv += [tuple(map(float, u)) for u in uvs]
        self.f.append(tuple(range(i0, i0 + len(pts))))

    def quad(self, a, b, c, d, **k):
        self.face([a, b, c, d], **k)

    def box(self, c, size, rotz=0.0, uv_scale=2.0, faces="all"):
        cx, cy, cz = c; sx, sy, sz = (s / 2 for s in size)
        co, si = math.cos(rotz), math.sin(rotz)
        P = lambda x, y, z: (cx + x * co - y * si, cy + x * si + y * co, cz + z)
        v = [P(x, y, z) for z in (-sz, sz) for y in (-sy, sy) for x in (-sx, sx)]
        quads = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))
        if faces == "nobottom":
            quads = quads[1:]
        for q in quads:
            self.face([v[i] for i in q], scale=uv_scale)

    def tube(self, p0, p1, r=0.2, sides=8):
        p0, p1 = np.array(p0, float), np.array(p1, float)
        ax = p1 - p0; L = np.linalg.norm(ax)
        if L < 1e-6: return
        ax /= L
        up = np.array([0, 0, 1.0]) if abs(ax[2]) < 0.95 else np.array([1.0, 0, 0])
        s = np.cross(ax, up); s /= np.linalg.norm(s); u = np.cross(s, ax)
        ring = [(math.cos(2 * math.pi * k / sides), math.sin(2 * math.pi * k / sides)) for k in range(sides)]
        r0 = [p0 + (s * a + u * b) * r for a, b in ring]; r1 = [p1 + (s * a + u * b) * r for a, b in ring]
        for i in range(sides):
            j = (i + 1) % sides
            self.face([r0[i], r0[j], r1[j], r1[i]], uvs=[(i / sides, 0), ((i + 1) / sides, 0), ((i + 1) / sides, L), (i / sides, L)])

    def beam(self, p0, p1, w=0.4, h=None):
        h = h or w
        p0, p1 = np.array(p0, float), np.array(p1, float)
        ax = p1 - p0; L = np.linalg.norm(ax)
        if L < 1e-6: return
        ax /= L
        up = np.array([0, 0, 1.0]) if abs(ax[2]) < 0.95 else np.array([1.0, 0, 0])
        s = np.cross(ax, up); s /= np.linalg.norm(s); u = np.cross(s, ax)
        cs = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        r0 = [p0 + s * a * w / 2 + u * b * h / 2 for a, b in cs]; r1 = [p1 + s * a * w / 2 + u * b * h / 2 for a, b in cs]
        for i in range(4):
            j = (i + 1) % 4
            self.face([r0[i], r0[j], r1[j], r1[i]], uvs=[(0, 0), (1, 0), (1, L), (0, L)])

    def build(self, name, mat, coll, uv=True):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        if uv:
            uvl = me.uv_layers.new(name="UVMap")
            uvv = np.array(self.uv, dtype=np.float32)
            loops = np.zeros(len(me.loops), dtype=np.int64)
            me.loops.foreach_get("vertex_index", loops)
            uvl.data.foreach_set("uv", uvv[loops].ravel())
        me.validate()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        return ob


# ---------------------------------------------------------------- materials
def img(path, noncolor=False):
    im = bpy.data.images.load(path, check_existing=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
    return im


def mat(name, color=(0.8, 0.8, 0.8), metal=0.0, rough=0.6, tex=None, emit=None, emit_str=0.0,
        alpha=1.0, double=True, normal_strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bs = nt.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Metallic"].default_value = metal
    bs.inputs["Roughness"].default_value = rough
    if tex:
        c = nt.nodes.new("ShaderNodeTexImage"); c.image = img(f"{TEX}/{tex}_c.jpg")
        nt.links.new(c.outputs["Color"], bs.inputs["Base Color"])
        if os.path.exists(f"{TEX}/{tex}_r.jpg"):
            r = nt.nodes.new("ShaderNodeTexImage"); r.image = img(f"{TEX}/{tex}_r.jpg", True)
            nt.links.new(r.outputs["Color"], bs.inputs["Roughness"])
        if os.path.exists(f"{TEX}/{tex}_n.jpg"):
            n = nt.nodes.new("ShaderNodeTexImage"); n.image = img(f"{TEX}/{tex}_n.jpg", True)
            nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = normal_strength
            nt.links.new(n.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], bs.inputs["Normal"])
    if emit:
        bs.inputs["Emission Color"].default_value = (*emit, 1)
        bs.inputs["Emission Strength"].default_value = emit_str
    if alpha < 1:
        bs.inputs["Alpha"].default_value = alpha
        try: m.surface_render_method = "BLENDED"
        except Exception: pass
    m.use_backface_culling = not double
    m["texset"] = tex or ""
    return m


MATS = {}


def make_materials():
    M = MATS
    M.update(
        terrace=mat("Terrace", tex="terrace", rough=0.85),
        concrete=mat("Concrete", tex="concrete", rough=0.85),
        concrete_dark=mat("ConcreteDark", tex="concrete_dark", rough=0.85),
        brick=mat("Brick", tex="brick", rough=0.85),
        panel_grey=mat("PanelGrey", tex="panel_grey", metal=0.35, rough=0.4),
        panel_grey_win=mat("PanelGreyWindows", tex="panel_grey_win", metal=0.3, rough=0.4),
        panel_white=mat("PanelWhite", tex="panel_white", metal=0.2, rough=0.35),
        panel_white_win=mat("PanelWhiteWindows", tex="panel_white_win", metal=0.2, rough=0.35),
        anthracite=mat("Anthracite", tex="anthracite", metal=0.4, rough=0.45),
        panel_red=mat("PanelRed", tex="panel_red", metal=0.3, rough=0.38),
        panel_mid=mat("PanelMid", tex="panel_mid", metal=0.35, rough=0.4),
        panel_red_win=mat("PanelRedWindows", tex="panel_red_win", metal=0.3, rough=0.38),
        water=mat("Water", tex="water", metal=0.0, rough=0.08),
        glass_teal=mat("GlassTeal", tex="glass_teal", metal=0.55, rough=0.06),
        glass_dark=mat("GlassDark", tex="glass_dark", metal=0.5, rough=0.05),
        boxglass=mat("BoxGlass", tex="glass_dark", metal=0.4, rough=0.05, emit=(1.0, 0.78, 0.5), emit_str=0.0),
        roof=mat("RoofSheet", tex="roof", metal=0.6, rough=0.4),
        roof_under=mat("RoofUnder", tex="roof_under", metal=0.3, rough=0.6),
        roof_clear=mat("RoofTranslucent", (0.9, 0.93, 0.95), rough=0.25, alpha=0.4),
        steel_white=mat("SteelWhite", (0.93, 0.94, 0.95), metal=0.15, rough=0.35),
        steel_grey=mat("SteelGrey", (0.42, 0.44, 0.47), metal=0.6, rough=0.4),
        red=mat("RedFascia", (0.62, 0.03, 0.05), rough=0.4),
        ribbon=mat("Ribbon", (0.05, 0.05, 0.05), rough=0.4, emit=(0.8, 0.05, 0.05), emit_str=2.0),
        led=mat("LEDBoards", (0.05, 0.05, 0.05), rough=0.4, emit=(0.9, 0.9, 0.9), emit_str=2.0),
        screen=mat("Screen", (0.02, 0.02, 0.02), rough=0.3, emit=(0.6, 0.7, 0.9), emit_str=3.0),
        lamp=mat("Lamp", (0.9, 0.9, 0.85), rough=0.2, emit=(1, 0.97, 0.9), emit_str=6.0),
        pitch=mat("Pitch", tex="pitch", rough=0.95),
        paving=mat("Paving", tex="paving", rough=0.85),
        paving_red=mat("PavingRed", tex="paving_red", rough=0.85),
        forecourt=mat("Forecourt", tex="forecourt", rough=0.85),
        ground=mat("Ground", tex="ground", rough=0.95),
        asphalt=mat("Asphalt", tex="asphalt", rough=0.95),
        ballast=mat("Ballast", tex="ballast", rough=0.95),
        grass=mat("Grass", (0.13, 0.26, 0.09), rough=0.95),
        tree=mat("Tree", (0.12, 0.24, 0.08), rough=0.9),
        bark=mat("Bark", (0.22, 0.17, 0.12), rough=0.9),
        house_brick=mat("HouseBrick", tex="brick_house", rough=0.85),
        slate=mat("Slate", tex="slate", rough=0.7),
        white=mat("White", (0.95, 0.95, 0.95), rough=0.4),
        net=mat("Net", (0.95, 0.95, 0.95), rough=0.6, alpha=0.3),
        vom=mat("Vomitory", (0.03, 0.03, 0.035), rough=0.9),
        balust=mat("Balustrade", (0.7, 0.8, 0.85), rough=0.05, alpha=0.25),
        dugout=mat("Dugout", (0.7, 0.75, 0.8), rough=0.1, alpha=0.4),
        rail=mat("Rail", (0.2, 0.2, 0.22), metal=0.8, rough=0.4),
        access=mat("AccessBlue", (0.05, 0.25, 0.65), rough=0.6),
        seat=mat("Seat", (0.62, 0.02, 0.03), rough=0.5),
        seat_white=mat("SeatWhite", (0.9, 0.9, 0.9), rough=0.5),
        solid=mat("ConcreteSolid", tex="concrete", rough=0.85),
        roof_solid=mat("RoofSolid", (0.5, 0.52, 0.55), rough=0.6),
        walls=mat("Plaster", (0.86, 0.85, 0.82), rough=0.8),
        stairs=mat("StairConcrete", (0.72, 0.72, 0.7), rough=0.8),
        fit_light=mat("FitoutLight", (0.78, 0.66, 0.5), rough=0.6),
        fit_dark=mat("FitoutDark", (0.16, 0.17, 0.19), rough=0.5),
        lift=mat("LiftCar", (0.55, 0.57, 0.6), metal=0.6, rough=0.35),
    )
    for k, (lbl, col) in INT.KINDS.items():
        M["fin_" + k] = mat("Floor_" + k.capitalize(), col, rough=0.7)


NAMES = dict(terrace="Terraces", under="Structure", concrete_dark="Concrete_Dark", brick="Facade_Brick",
             panel_grey="Facade_PanelGrey", panel_grey_win="Facade_PanelGreyWindows", panel_white="Facade_PanelWhite",
             panel_white_win="Facade_PanelWhiteWindows", anthracite="Facade_Anthracite", panel_red="Facade_PanelRed", panel_mid="Facade_PanelMid", panel_red_win="Facade_PanelRedWindows", water="Canal", glass_teal="Facade_GlassTeal",
             glass_dark="Facade_GlassDark", boxglass="ExecBoxes", roof="Roof", roof_under="Roof_Underside",
             roof_clear="Roof_Translucent", steel_white="Roof_Trusses", steel_grey="Steel_Grey", red="Fascia_Red",
             ribbon="Ribbon_LED", led="LED_Boards", screen="Screens", lamp="Floodlight_Lamps", pitch="Pitch",
             paving="Plaza", paving_red="Plaza_Red", forecourt="Forecourt", ground="Ground", asphalt="Roads",
             ballast="Railway", grass="Embankment", tree="Trees", bark="Tree_Trunks", house_brick="Houses",
             slate="House_Roofs", white="Goals", net="Goal_Nets", vom="Vomitories", balust="Balustrades",
             dugout="Dugouts", rail="Rails", access="Accessible_Platforms",
             solid="Structure_Solid", roof_solid="Roof_Solid", walls="Interior_Walls", stairs="Interior_Stairs", fit_light="Interior_Fitout",
             fit_dark="Interior_Fitout_Dark", lift="Interior_Lifts",
             **{"fin_" + k: "Floor_" + k.capitalize() for k in INT.KINDS})
MATKEY = dict(under="concrete")


def strip(mb, seg, p0, p1, d, h, d2, h2, up=None, sc=4.0, step=2.5):
    if seg in STRAIGHT:
        ps = [p0, p1]
    else:
        n = max(1, int(abs(p1 - p0) / step)); ps = list(np.linspace(p0, p1, n + 1))
    L = 0.0
    for i in range(len(ps) - 1):
        (x0, z0), _ = pt(seg, ps[i], d); (x1, z1), _ = pt(seg, ps[i + 1], d)
        (x2, z2), _ = pt(seg, ps[i + 1], d2); (x3, z3), _ = pt(seg, ps[i], d2)
        sl = math.hypot(x1 - x0, z1 - z0); vl = math.hypot(d2 - d, h2 - h)
        uvs = [(L / sc, 0), ((L + sl) / sc, 0), ((L + sl) / sc, vl / sc), (L / sc, vl / sc)]
        mb.quad(H(x0, z0, h), H(x1, z1, h), H(x2, z2, h2), H(x3, z3, h2), uvs=uvs, up=up)
        L += sl


def strip_full(mb, seg, d, h, d2, h2, up=None, sc=4.0):
    ps = samples(seg)
    strip(mb, seg, ps[0], ps[-1], d, h, d2, h2, up=up, sc=sc)


UP = np.array([0, 0, 1.0])


def block_bounds(seg):
    ps = samples(seg); nb = SEG[seg][6]
    return list(np.linspace(ps[0], ps[-1], nb + 1))


def vom_rows(seg, t):
    """Vomitory rows per tier: about one third up the lower tiers, mid-tier on the upper tiers."""
    n = nrows(seg, t)
    if t == 1:
        r0 = 10 if n <= 32 else int(round(n * 0.4))
    else:
        r0 = int(round(n * 0.42))
    return (r0, r0 + 5)


def vom_list():
    """Vomitories at every interior block boundary of every tier: {(seg, tier): [(u, half_width_in_u)]}."""
    V, VR = {}, {}
    for seg, kind, stand, code, tiers, roof, nb, *_ in SEGS:
        b = block_bounds(seg)
        for t in tiers:
            r0, r1 = vom_rows(seg, t)
            if kind == "straight":
                hw = 1.6
            else:
                hw = math.degrees(1.6 / (R + row_d(t, r0)))
            V[(seg, t)] = [(float(u), hw) for u in b[1:-1]]
            VR[(seg, t)] = (r0, r1)
    return V, VR


VOMS = None
VOMR = {}
VOM_ROWS = (10, 15)
RAIL_BLOCKS = {("W", 1): [2, 3, 4, 5], ("NE", 1): [1, 2, 3, 4, 5, 6]}   # safe-standing rail seating


def cut_ivals(ivals, c0, c1):
    """Remove the u-range [min(c0,c1), max(c0,c1)] from a list of (p0, p1) intervals (any direction)."""
    lo, hi = min(c0, c1), max(c0, c1); out = []
    for p0, p1 in ivals:
        a, b = min(p0, p1), max(p0, p1); sg = 1 if p1 >= p0 else -1
        parts = []
        if lo > a: parts.append((a, min(lo, b)))
        if hi < b: parts.append((max(hi, a), b))
        for x, y in parts:
            if y - x > 1e-6:
                out.append((x, y) if sg > 0 else (y, x))
    return out


def tunnel_row():
    r = 0
    while row_y(1, r) < INT.TUNNEL["ymax"]:
        r += 1
    return r


def build_bowl(mbs):
    tr, un = mbs["terrace"], mbs["under"]
    for seg, kind, stand, code, tiers, roof, nb, _, style in SEGS:
        for t in tiers:
            sp = TIER_SPEC[t]
            T = treads(seg, t)
            tun = INTERIOR and seg == INT.TUNNEL["seg"] and t == 1
            rt = tunnel_row() if tun else -1
            for k, (d0, d1, y, kindr) in enumerate(T):
                ivals = [(samples(seg)[0], samples(seg)[-1])]
                if (seg, t) in VOMS and VOMR[(seg, t)][0] <= k < VOMR[(seg, t)][1]:
                    a, b = ivals[0]; sg = 1 if b > a else -1
                    cuts = sorted(VOMS[(seg, t)], key=lambda c: c[0] * sg); out = []; cur = a
                    for c, hw in cuts:
                        out.append((cur, c - sg * hw)); cur = c + sg * hw
                    out.append((cur, b)); ivals = out
                if tun and k < rt:
                    ivals = cut_ivals(ivals, INT.TUNNEL["u0"], INT.TUNNEL["u1"])
                for p0, p1 in ivals:
                    strip(tr if kindr == "row" else mbs["access"], seg, p0, p1, d0, y, d1, y, up=UP, sc=1.0)
                    if k + 1 < len(T):
                        strip(tr, seg, p0, p1, d1, y, d1, T[k + 1][2], sc=1.0)
                if tun and k == rt - 1:   # riser from the tunnel deck up to the first remaining row
                    strip(tr, seg, INT.TUNNEL["u1"], INT.TUNNEL["u0"], d1, INT.TUNNEL["deck"], d1, T[k + 1][2], sc=1.0)
            if tun:   # deck over the tunnel mouth, balustrade along its front and sides
                dr = row_d(1, rt); dk = INT.TUNNEL["deck"]
                strip(tr, seg, INT.TUNNEL["u1"], INT.TUNNEL["u0"], -0.25, dk, dr, dk, up=UP, sc=1.0)
                strip(un, seg, INT.TUNNEL["u1"], INT.TUNNEL["u0"], -0.25, INT.TUNNEL["soffit"], -0.25, dk)
                strip(mbs["balust"], seg, INT.TUNNEL["u1"], INT.TUNNEL["u0"], -0.2, dk, -0.2, dk + 1.1)
                strip(mbs["rail"], seg, INT.TUNNEL["u1"], INT.TUNNEL["u0"], -0.25, dk + 1.1, -0.15, dk + 1.1)
                for uu in (INT.TUNNEL["u0"], INT.TUNNEL["u1"]):
                    (xa, za), _ = pt(seg, uu, -0.2); (xb, zb), _ = pt(seg, uu, dr)
                    mbs["balust"].quad(H(xa, za, dk), H(xb, zb, dk), H(xb, zb, dk + 1.1), H(xa, za, dk + 1.1))
            dB, hB = tier_back(seg, t)
            if t == 1:
                ps_ = samples(seg); iv = [(ps_[0], ps_[-1])]
                if INTERIOR and seg == INT.TUNNEL["seg"]:
                    iv = cut_ivals(iv, INT.TUNNEL["u0"], INT.TUNNEL["u1"])
                for p0, p1 in iv:
                    strip(un, seg, p0, p1, -0.25, 0.0, -0.25, sp["y0"] + 0.25)
                    strip(un, seg, p0, p1, -0.25, sp["y0"] + 0.25, 0.0, sp["y0"] + 0.25, up=UP)
                    strip(un, seg, p0, p1, 0.0, sp["y0"] + 0.25, 0.0, sp["y0"])
            else:
                (fd, fy), (bd, by) = soffit(seg, t)
                if not INTERIOR:
                    strip_full(un, seg, fd, fy, bd, by, up=-UP)
                strip_full(mbs["red"], seg, fd, fy, fd, sp["y0"] - 1.3)
                strip_full(mbs["ribbon"], seg, fd, sp["y0"] - 1.3, fd, sp["y0"] - 0.1, sc=1000)
                strip_full(un, seg, fd, sp["y0"] - 0.1, sp["d0"], sp["y0"] - 0.1, up=UP)
                strip_full(un, seg, sp["d0"], sp["y0"] - 0.1, sp["d0"], sp["y0"])
                strip_full(mbs["balust"], seg, sp["d0"] - 0.3, sp["y0"], sp["d0"] - 0.3, sp["y0"] + 1.05)
                strip_full(mbs["rail"], seg, sp["d0"] - 0.35, sp["y0"] + 1.05, sp["d0"] - 0.25, sp["y0"] + 1.05)
            # tier back: cap up to the concourse floor (the interior solids provide these faces)
            if not INTERIOR:
                strip_full(un, seg, dB, hB, dB, hB + 0.2)
            nxt = t + 1 if (t + 1) in tiers else None
            if nxt:
                sd, sy = soffit(seg, nxt)[0]
                if dB + 1.5 < sd:   # gap between tiers: concourse floor then wall up to the fascia
                    if not INTERIOR:
                        strip_full(un, seg, dB, hB + 0.2, sd, hB + 0.2, up=UP)
                    strip_full(mbs["boxglass"], seg, sd, hB + 0.2, sd, sy, sc=3.0)
                else:
                    if not INTERIOR:
                        strip_full(un, seg, dB, hB + 0.2, dB + 1.5, hB + 0.2, up=UP)
                    hs = soffit_y(seg, nxt, dB + 1.5)
                    if hs > hB + 0.4:
                        strip_full(mbs["boxglass"], seg, dB + 1.5, hB + 0.2, dB + 1.5, hs, sc=3.0)
            else:
                if not INTERIOR:
                    strip_full(un, seg, dB, hB + 0.2, dB + 1.5, hB + 0.2, up=UP)
                ru = roof_y(roof, dB + 1.5) - 1.4
                if roof == "low":
                    strip_full(mbs["boxglass"], seg, dB + 1.5, hB + 0.2, dB + 1.5, hB + 4.2, sc=3.0)
                    strip_full(mbs["concrete_dark"], seg, dB + 1.5, hB + 4.2, dB + 1.5, ru, sc=4.0)
                else:
                    strip_full(mbs["concrete_dark"], seg, dB + 1.5, hB + 0.2, dB + 1.5, ru, sc=4.0)


def build_junction_caps(mbs):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union, triangulate
    un = mbs["under"]
    order = [s[0] for s in SEGS]
    for i, s in enumerate(order):
        nxt = order[(i + 1) % len(order)]
        p_end = samples(s)[-1]
        a, b = SEG[s], SEG[nxt]
        caps2d = []
        for t in sorted(set(a[4]) | set(b[4])):
            ta = treads(s, t) if t in a[4] else []
            tb = treads(nxt, t) if t in b[4] else []
            if [x[:3] for x in ta] == [x[:3] for x in tb]:
                continue
            big, small = (s, ta, tb) if len(ta) >= len(tb) else (nxt, tb, ta), None
            bseg, btr, str_ = big
            # profile of the larger tier minus the region the smaller tier already closes
            prof = []
            for d0, d1, y, _ in btr:
                prof += [(d0, y), (d1, y)]
            sp = TIER_SPEC[t]
            dB, hB = btr[-1][1], btr[-1][2]
            if str_:
                # cap only the part beyond the smaller tier's back
                sdB = str_[-1][1]
                prof = [(d, y) for d, y in prof if d >= sdB - 1e-6]
                if not prof:
                    continue
                d_start = prof[0][0]
                base = treads(nxt if bseg == s else s, t)[-1][2]
                poly = [(d_start, base + 0.2)] + prof + [(dB, hB + 0.2)]
            else:
                if t > 1:
                    (fd, fy), (bd, by) = soffit(bseg, t)
                    poly = [(fd, fy), (fd, sp["y0"] - 0.1), (sp["d0"], sp["y0"] - 0.1)] + prof + [(dB, hB + 0.2), (bd, by)]
                else:
                    poly = [(0.0, 0.0), (0.0, sp["y0"])] + prof + [(dB, hB + 0.2), (dB, 0.0)]
            pts3 = []
            for d, h in poly:
                (px, pz), _ = pt(s, p_end, d); pts3.append(H(px, pz, h))
            if len(pts3) >= 3 and not INTERIOR:
                un.face(pts3)
                try:
                    caps2d.append(Polygon(poly).buffer(0))
                except Exception:
                    pass
        # roof/facade gable where roof classes change
        ra_, rb_ = ROOFS[a[5]], ROOFS[b[5]]
        if a[5] != b[5]:
            hiname, loname = (a[5], b[5]) if ra_["yb"] > rb_["yb"] else (b[5], a[5])
            hi, lo = ROOFS[hiname], ROOFS[loname]
            ps_ = samples(s)
            tvec = np.array(pt(s, p_end, 0.0)[0]) - np.array(pt(s, ps_[-2] if len(ps_) > 2 else ps_[0], 0.0)[0])
            tvec = tvec / (np.linalg.norm(tvec) + 1e-9)

            def gable(d0g, d1g, bottom_fn, key, cut=True, off=0.0):
                ds = np.linspace(d0g, d1g, 30)
                topl = [(d, roof_y(hiname, d) + 0.05) for d in ds]
                botl = [(d, bottom_fn(d)) for d in ds[::-1]]
                g = Polygon(topl + botl).buffer(0)
                if caps2d and cut:
                    g = g.difference(unary_union(caps2d))
                parts = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
                import shapely
                for part in parts:
                    if part.area < 0.01: continue
                    tris = shapely.constrained_delaunay_triangles(part)
                    for tri in getattr(tris, "geoms", [tris]):
                        if tri.is_empty or tri.area < 1e-4: continue
                        mbs[key].face([H(*(np.array(pt(s, p_end, d)[0]) + tvec * off), h) for d, h in list(tri.exterior.coords)[:3]], scale=4.0)
            lo_back = lo["db"] + 0.6
            lo_under = lambda d: max(0.0, roof_y(loname, d) - 1.4)
            # inside the bowl: translucent infill framed by an open white lattice (as on the real quadrants)
            gsg = 1.0 if hiname == a[5] else -1.0      # offset the gable towards the lower stand, in front of the taller block's end
            gable(hi["df"], lo_back, lo_under, "roof_clear", off=(gsg * 0.08 if INTERIOR else 0.0))
            # outside the lower stand's facade: the quadrant's clad side wall
            gable(lo_back, hi["db"] + 0.6, lambda d: 0.0, "panel_white", cut=False, off=gsg * 0.08)
            dsl = np.linspace(hi["df"], lo_back, 9)
            topc = [H(*pt(s, p_end, d)[0], roof_y(hiname, d) - 0.3) for d in dsl]
            botc = [H(*pt(s, p_end, d)[0], max(lo_under(d) + 1.6, roof_y(hiname, d) - 9.0)) for d in dsl]
            truss(mbs["steel_white"], botc, topc, 0.24, 0.12)
            for k_ in range(0, len(dsl), 2):   # hangers down to the lower roof
                mbs["steel_white"].tube(botc[k_], H(*pt(s, p_end, dsl[k_])[0], lo_under(dsl[k_]) + 1.45), 0.14)


def build_vomitories(mbs):
    un = mbs["under"]
    T1 = TIER_SPEC[1]
    for (seg, t), lst in VOMS.items():
        r0, r1 = VOMR[(seg, t)]
        d0, h0 = row_d(t, r0), row_y(t, r0)
        d1, h1 = row_d(t, r1), row_y(t, r1 - 1)
        for c, hw in lst:
            vp = PLAN["segs"][seg]["vom"][t] if INTERIOR else None
            dfl = min(d1, vp["x0"]) if vp else d1
            (xa, za), _ = pt(seg, c - hw, d0); (xb, zb), _ = pt(seg, c + hw, d0)
            (xc, zc), _ = pt(seg, c + hw, dfl); (xd, zd), _ = pt(seg, c - hw, dfl)
            mbs["vom"].quad(H(xa, za, h0), H(xb, zb, h0), H(xc, zc, h0), H(xd, zd, h0), up=UP)
            htop = row_y(t, r1)
            (xc, zc), _ = pt(seg, c + hw, d1); (xd, zd), _ = pt(seg, c - hw, d1)
            hb_ = vp["open_top"] if vp else h0
            if htop > hb_ + 0.02:
                mbs["vom"].quad(H(xd, zd, hb_), H(xc, zc, hb_), H(xc, zc, htop), H(xd, zd, htop))
            for sg in (-1, 1):
                pp = c + sg * hw
                poly = []
                for r in range(r0, r1):
                    poly += [(row_d(t, r), row_y(t, r)), (row_d(t, r + 1), row_y(t, r))]
                poly += [(d1, htop), (d1, h0)]
                pts3 = [H(*pt(seg, pp, d)[0], h) for d, h in poly]
                un.face(pts3)
                (rx0, rz0), _ = pt(seg, pp, d0); (rx1, rz1), _ = pt(seg, pp, d1)
                mbs["rail"].beam(H(rx0, rz0, h0 + 1.0), H(rx1, rz1, h1 + 1.0), w=0.06)


def build_rails_and_platforms(mbs):
    """Safe-standing rails (one per row) and the accessible platform balustrades + markings."""
    for (seg, t), blocks in RAIL_BLOCKS.items():
        b = block_bounds(seg)
        n = nrows(seg, t)
        for bi in blocks:
            p0, p1 = b[bi - 1], b[bi]
            if seg in STRAIGHT:
                ps = list(np.linspace(p0, p1, 2))
            else:
                ps = list(np.linspace(p0, p1, 7))
            sg = 1 if p1 > p0 else -1
            span = (p0 + sg * 0.6, p1 - sg * 0.6) if seg in STRAIGHT else (p0 + sg * 1.0, p1 - sg * 1.0)
            ps = list(np.linspace(span[0], span[1], len(ps)))
            for r in range(1, n - (PLATFORM_ROWS if seg in PLATFORM_SEGS and t == 1 else 0)):
                d = row_d(t, r) + 0.06; h = row_y(t, r - 1) + 1.05
                for k in range(len(ps) - 1):
                    a_ = pt(seg, ps[k], d)[0]; b_ = pt(seg, ps[k + 1], d)[0]
                    mbs["rail"].tube(H(*a_, h), H(*b_, h), 0.03, 6)
                npost = max(2, int(seg_len(seg, d) * abs(span[1] - span[0]) / (abs(STRAIGHT[seg][2][1] - STRAIGHT[seg][2][0]) if seg in STRAIGHT else 90) / 2.5))
                for q in np.linspace(span[0], span[1], npost):
                    a_ = pt(seg, q, d)[0]
                    mbs["rail"].tube(H(*a_, row_y(t, r - 1) + 0.05), H(*a_, h), 0.025, 5)
    for seg in PLATFORM_SEGS:
        T = treads(seg, 1)
        d0, d1, y, _ = T[-1]
        strip_full(mbs["balust"], seg, d0 + 0.05, y, d0 + 0.05, y + 1.1)
        strip_full(mbs["rail"], seg, d0 + 0.0, y + 1.1, d0 + 0.1, y + 1.1)


def build_facades(mbs):
    for seg, kind, stand, code, tiers, roof, nb, _, style in SEGS:
        Rr = ROOFS[roof]; db = Rr["db"]; top = Rr["yb"]
        def band(h0, h1, key, sc=4.0):
            strip_full(mbs[key], seg, db, h0, db, h1, sc=sc)
        if style == "north":
            band(0, 6, "anthracite"); band(6, 9, "glass_dark", 6.0)
            band(9, 22, "panel_red_win"); band(22, 24, "glass_dark", 6.0)
            band(24, 38, "panel_red"); band(38, 40, "glass_dark", 6.0)
            band(40, top - 5, "panel_red"); band(top - 5, top, "panel_white")
            a, b = STRAIGHT[seg][2]
            for u in np.linspace(a, b, 7)[1:-1]:      # projecting grey stair towers
                (x, z), nrm = pt(seg, u, db + 2.4)
                yaw = math.atan2(nrm[1], nrm[0])
                mbs["panel_mid"].box(H(x, z, (top - 3) / 2), (5.6, 7.0, top - 3), yaw, uv_scale=4.0, faces="nobottom")
                (x2, z2), _ = pt(seg, u, db + 5.25)
                mbs["glass_dark"].box(H(x2, z2, (top - 8) / 2 + 3), (0.06, 1.6, top - 8), yaw, uv_scale=6.0)
        elif style == "west":
            band(0, 7, "brick", 2.0); band(7, 10, "glass_dark", 6.0)
            band(10, 20, "panel_grey_win"); band(20, 23, "glass_dark", 6.0)
            band(23, top - 3.5, "panel_grey"); band(top - 3.5, top, "panel_white")
        elif style == "south":
            band(0, 4.5, "brick", 2.0); band(4.5, 9, "panel_white_win"); band(9, 11, "glass_dark", 6.0)
            band(11, 16, "panel_white_win"); band(16, 18, "glass_dark", 6.0)
            band(18, top - 3, "panel_white"); band(top - 3, top, "red", 4.0)
        elif style == "quad_low":
            band(0, 5, "brick", 2.0); band(5, 10, "panel_white_win"); band(10, 12, "glass_dark", 6.0)
            band(12, top - 3, "panel_white"); band(top - 3, top, "red", 4.0)
        elif style == "quad_glass":
            band(0, 6, "anthracite"); band(6, 6.6, "panel_white"); band(6.6, 9.0, "red", 4.0)
            band(9.0, top - 5, "glass_teal", 6.0); band(top - 5, top, "panel_white")
        elif style == "east":
            # flanks: grey panels with window slots over an anthracite ground floor
            band(0, 5.5, "anthracite"); band(5.5, 6.2, "panel_white")
            band(6.2, top - 4, "panel_grey_win"); band(top - 4, top, "panel_white")
        # brick piers on brick-based styles
        if style in ("west", "south", "quad_low") and kind == "straight":
            a, b = STRAIGHT[seg][2]
            npier = int(abs(b - a) / (12 if style == "south" else 18))
            for u in np.linspace(a, b, npier + 1)[1:-1]:
                (x, z), nrm = pt(seg, u, db + 0.75)
                yaw = math.atan2(nrm[1], nrm[0])
                mbs["brick"].box(H(x, z, (top - 4) / 2), (1.3, 2.4, top - 4), yaw, uv_scale=2.0, faces="nobottom")
    # East Stand: curved teal curtain wall bulging out of the facade, canopy, piers at the ends
    Rr = ROOFS["mid"]; db = Rr["db"]; top = Rr["yb"]
    span = 22.0; bulge = 6.5
    us = np.linspace(-span, span, 33)
    def ept(u, extra=0.0):
        off = bulge * math.cos(math.pi * u / (2 * span)) + extra
        return pt("E", u, db + off)[0]
    h0, h1 = 6.2, 26.0
    for k in range(len(us) - 1):
        a_, b_ = ept(us[k]), ept(us[k + 1])
        L0 = (us[k] + span) / 6.0; L1 = (us[k + 1] + span) / 6.0
        mbs["glass_teal"].quad(H(*a_, h0), H(*b_, h0), H(*b_, h1), H(*a_, h1), uvs=[(L0, 0), (L1, 0), (L1, (h1 - h0) / 6), (L0, (h1 - h0) / 6)])
        a2, b2 = ept(us[k], 0.0), ept(us[k + 1], 0.0)
        # roof of the bulge and its soffit band
        mbs["panel_white"].quad(H(*pt("E", us[k], db)[0], h1), H(*pt("E", us[k + 1], db)[0], h1), H(*b_, h1), H(*a_, h1), up=UP)
        mbs["panel_white"].quad(H(*a_, h1), H(*b_, h1), H(*b_, h1 + 1.6), H(*a_, h1 + 1.6))
        mbs["panel_white"].quad(H(*pt("E", us[k], db)[0], h1 + 1.6), H(*pt("E", us[k + 1], db)[0], h1 + 1.6), H(*b_, h1 + 1.6), H(*a_, h1 + 1.6), up=UP)
        # ground floor under the bulge: dark shopfronts set back
        mbs["anthracite"].quad(H(*a_, 0), H(*b_, 0), H(*b_, h0), H(*a_, h0))
    for sgn in (-1, 1):   # side walls of the bulge (closed by glass edge panels)
        u = sgn * span
        a_ = pt("E", u, db)[0]; b_ = ept(u)
        mbs["glass_teal"].quad(H(*a_, 0), H(*b_, 0), H(*b_, h1 + 1.6), H(*a_, h1 + 1.6))
    # canopy along the whole East Stand at 6 m
    for u0, u1 in ((-WS, WS),):
        a_, b_ = pt("E", u0, db + 0.05)[0], pt("E", u1, db + 0.05)[0]
        c_, d_ = pt("E", u1, db + 10.0)[0], pt("E", u0, db + 10.0)[0]
        mbs["panel_white"].quad(H(*a_, 6.0), H(*b_, 6.0), H(*c_, 6.0), H(*d_, 6.0), up=-UP)
        mbs["panel_white"].quad(H(*a_, 6.5), H(*b_, 6.5), H(*c_, 6.5), H(*d_, 6.5), up=UP)
        mbs["panel_white"].quad(H(*d_, 6.0), H(*c_, 6.0), H(*c_, 6.5), H(*d_, 6.5))
    for u in (-WS + 2.6, WS - 2.6):   # red brick end piers
        (x, z), nrm = pt("E", u, db + 0.6)
        mbs["brick"].box(H(x, z, top / 2), (2.0, 4.0, top), math.atan2(nrm[1], nrm[0]), uv_scale=2.0, faces="nobottom")
    # corner towers: tall white towers at the NE/E and NW/W junctions, brick towers at SE/SW
    hgt = ROOFS["high"]["yb"] + 5.0
    # NE quadrant: twin white sail fins flanking a glazed stair slot, standing proud of the curved glass
    dbh = ROOFS["high"]["db"]
    for side in (-1, 1):
        ang = -45.0 + side * 3.4
        (x, z), nrm = pt("NE", ang, dbh + 3.0)
        yaw = math.atan2(nrm[1], nrm[0]) + side * 0.35
        mbs["panel_white"].box(H(x, z, hgt / 2), (7.0, 6.0, hgt), yaw, uv_scale=4.0, faces="nobottom")
        (x2, z2), _ = pt("NE", ang, dbh + 6.6)
        mbs["panel_grey"].box(H(x2, z2, hgt / 2), (0.12, 4.6, hgt - 2), yaw, uv_scale=4.0)
    (x, z), nrm = pt("NE", -45.0, dbh + 1.5)
    mbs["glass_teal"].box(H(x, z, hgt / 2 - 1), (3.0, 3.2, hgt - 2), math.atan2(nrm[1], nrm[0]), uv_scale=6.0, faces="nobottom")
    # NW corner: tall white fin tower with a grey vertical panel (west end of the Sir Alex Ferguson Stand)
    (x, z), nrm = pt("NW", 186.0, dbh + 4.0)
    yaw = math.atan2(nrm[1], nrm[0])
    mbs["panel_white"].box(H(x, z, hgt / 2), (10.0, 12.0, hgt), yaw, uv_scale=4.0, faces="nobottom")
    (x2, z2), _ = pt("NW", 186.0, dbh + 9.09)
    mbs["panel_grey"].box(H(x2, z2, hgt * 0.5), (0.12, 4.0, hgt * 0.9), yaw, uv_scale=4.0)
    # south corners: red-brick stair blocks
    for seg, ang in (("SE", 60.0), ("SW", 120.0)):
        (x, z), nrm = pt(seg, ang, ROOFS["low"]["db"] + 4.5)
        yaw = math.atan2(nrm[1], nrm[0])
        h2 = ROOFS["low"]["yb"] + 2.0
        mbs["brick"].box(H(x, z, h2 / 2), (9.0, 9.0, h2), yaw, uv_scale=2.0, faces="nobottom")
        mbs["panel_white"].box(H(x, z, h2 + 0.75), (9.6, 9.6, 1.5), yaw, uv_scale=4.0, faces="nobottom")


def roof_surface(mbs):
    for seg, kind, stand, code, tiers, roof, nb, _, style in SEGS:
        Rr = ROOFS[roof]; df, db = Rr["df"], Rr["db"]
        dc = df + 7.0
        ry = lambda d: roof_y(roof, d)
        strip_full(mbs["roof_clear"], seg, df, ry(df), dc, ry(dc), up=UP)
        strip_full(mbs["roof"], seg, dc, ry(dc), db + 0.6, ry(db + 0.6), up=UP, sc=8.0)
        strip_full(mbs["roof_under"], seg, dc, ry(dc) - 1.4, db, ry(db) - 1.4, up=-UP, sc=8.0)
        strip_full(mbs["roof_under"], seg, df, ry(df) - 1.4, dc, ry(dc) - 1.4, up=-UP, sc=8.0) if False else None
        strip_full(mbs["steel_white"], seg, df - 0.3, ry(df) - 1.6, df - 0.3, ry(df) + 0.3)
        strip_full(mbs["roof_under"], seg, db + 0.6, ry(db + 0.6), db + 0.6, ry(db + 0.6) - 1.4)


def truss(mb, bot, top, rc=0.22, rw=0.12, last_vertical=True):
    """Planar Warren truss between two chord polylines (equal-length lists of 3D points)."""
    for i in range(len(bot) - 1):
        mb.tube(bot[i], bot[i + 1], rc); mb.tube(top[i], top[i + 1], rc)
        if i % 2 == 0:
            mb.tube(bot[i], top[i + 1], rw)
        else:
            mb.tube(top[i], bot[i + 1], rw)
    for i in range(len(bot) if last_vertical else len(bot) - 1):
        mb.tube(bot[i], top[i], rw)


def roof_steel(mbs):
    W = mbs["steel_white"]; G = mbs["steel_grey"]
    for seg, kind, stand, code, tiers, roof, nb, _, style in SEGS:
        Rr = ROOFS[roof]; df, db = Rr["df"], Rr["db"]
        ry = lambda d: roof_y(roof, d)
        ps_all = samples(seg, 1.0)
        # front lattice girder (all roofs)
        if kind == "straight":
            n = max(2, int(seg_len(seg, df) / 4.0)); fps = list(np.linspace(ps_all[0], ps_all[-1], n + 1))
        else:
            fps = list(np.linspace(ps_all[0], ps_all[-1], 13))
        topF = [H(*pt(seg, p, df + 1.2)[0], ry(df) + 2.6) for p in fps]
        botF = [H(*pt(seg, p, df - 0.2)[0], ry(df) - 1.5) for p in fps]
        mb = W if roof != "low" else G
        truss(mb, botF[:], topF[:], 0.22, 0.11, last_vertical=False)
        # floodlight rows under the front edge
        L = seg_len(seg, df); n_l = max(2, int(L / 4.5))
        pl = list(np.linspace(ps_all[0], ps_all[-1], n_l + 1))
        for p in pl[:-1]:
            (x, z), nrm = pt(seg, p, df + 0.8); yaw = math.atan2(nrm[1], nrm[0])
            G.box(H(x, z, ry(df) - 2.1), (0.9, 1.6, 0.7), yaw)
            (x2, z2), _ = pt(seg, p, df + 0.16)
            mbs["lamp"].box(H(x2, z2, ry(df) - 2.15), (0.08, 1.4, 0.55), yaw)
        if style in ("east", "west"):
            continue   # handled by tower trusses
        # parallel / radial trusses running front-to-back over the roof
        if kind == "straight":
            n = max(2, int(seg_len(seg, 0) / 9.0)); tps = list(np.linspace(ps_all[0], ps_all[-1], n + 1))[1:-1]
        else:
            tps = list(np.linspace(ps_all[0], ps_all[-1], 7))[1:-1]
        rise = 8.0 if roof == "high" else 4.0
        for p in tps:
            ds = np.linspace(df + 1.2, db + 0.6, 9)
            bot = [H(*pt(seg, p, d)[0], ry(d) + 0.15) for d in ds]
            top = [H(*pt(seg, p, d)[0], ry(d) + 1.5 + rise * ((d - ds[0]) / (ds[-1] - ds[0])) ** 0.7) for d in ds]
            truss(W if roof != "low" else G, bot, top, 0.26, 0.13)
            # back mast down to the facade line

        # longitudinal ties linking the truss tops
        for frac in (0.35, 0.7, 1.0):
            d = df + 1.2 + (db + 0.6 - df - 1.2) * frac
            hh = lambda: None
            pts_ = [H(*pt(seg, p, d)[0], ry(d) + 1.5 + rise * frac ** 0.7) for p in tps]
            for k in range(len(pts_) - 1):
                (W if roof != "low" else G).tube(pts_[k], pts_[k + 1], 0.16)
    # East Stand / Stretford End (matched to the East Stand photos): three box-truss towers standing at the
    # BACK of the roof, each carrying a deep box girder that slopes down to the roof's front edge, with
    # bowed lattice trusses linking the tower tops and stepping down to the stand ends.
    for seg in ("E", "W"):
        Rr = ROOFS["mid"]; df, db = Rr["df"], Rr["db"]
        ry = lambda d: roof_y("mid", d)
        dT = db - 4.5                       # tower centre line, just inside the facade
        TW = 6.0                            # tower plan size
        tops = []
        for u, rise in ((-21.0, 13.0), (0.0, 16.0), (21.0, 13.0)):
            hb = ry(dT + TW / 2) + 0.15
            ht = ry(dT) + rise
            # tapered square tower: 6 m at the roof, 4.4 m at the top
            levels = np.linspace(0, 1, 6)
            rings = []
            for lv in levels:
                half = (TW / 2) * (1 - 0.27 * lv)
                ring = []
                for du, dd in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    q = pt(seg, u + du * half, dT + dd * half)[0]
                    ring.append(H(*q, hb + (ht - hb) * lv))
                rings.append(ring)
            for j in range(len(levels) - 1):
                for k in range(4):
                    W.tube(rings[j][k], rings[j + 1][k], 0.30)
                    W.tube(rings[j][k] if j % 2 == 0 else rings[j][(k + 1) % 4], rings[j + 1][(k + 1) % 4] if j % 2 == 0 else rings[j + 1][k], 0.12)
            for j in range(len(levels)):
                for k in range(4):
                    W.tube(rings[j][k], rings[j][(k + 1) % 4], 0.15)
            tops.append((u, ht))
            # cantilever box girder: from the tower top down to the front edge of the roof
            n = 10
            for i in range(n):
                pass
            ds = np.linspace(dT - TW * 0.36, df + 1.0, n + 1)
            chords = {}
            for k, (su, sv) in enumerate(((-1, 1), (1, 1), (1, -1), (-1, -1))):
                line = []
                for j, d in enumerate(ds):
                    f = j / n
                    half_w = 2.2 * (1 - f) + 0.9 * f
                    depth = 5.0 * (1 - f) + 1.4 * f
                    topz = ht + (ry(df) + 2.4 - ht) * f
                    z = topz - (0 if sv > 0 else depth)
                    line.append(H(*pt(seg, u + su * half_w, d)[0], z))
                chords[k] = line
            for k in range(4):
                for j in range(n):
                    W.tube(chords[k][j], chords[k][j + 1], 0.22)
            for j in range(n + 1):
                for k in range(4):
                    W.tube(chords[k][j], chords[(k + 1) % 4][j], 0.1)
            for j in range(n):
                for k in range(4):
                    a_, b_ = (chords[k][j], chords[(k + 1) % 4][j + 1]) if j % 2 == 0 else (chords[(k + 1) % 4][j], chords[k][j + 1])
                    W.tube(a_, b_, 0.1)
            # hangers from the girder bottom down to the roof plane
            for j in range(2, n, 2):
                for k in (2, 3):
                    p_ = chords[k][j]
                    d_ = ds[j]
                    W.tube(p_, H(p_[0], p_[1], ry(d_) + 0.15), 0.08)
        # bowed trusses along the back linking the tower tops and stepping down to the stand ends
        ends = [STRAIGHT[seg][2][0], STRAIGHT[seg][2][1]]
        lo, hi = min(ends), max(ends)
        chain = [(lo + 0.8, ry(dT) + 1.2)] + [(u, h - 0.5) for u, h in sorted(tops)] + [(hi - 0.8, ry(dT) + 1.2)]
        for k in range(len(chain) - 1):
            (u0, h0_), (u1, h1_) = chain[k], chain[k + 1]
            # start/end at the tower faces, not inside them
            if k > 0: u0 += TW * 0.4
            if k < len(chain) - 2: u1 -= TW * 0.4
            us = np.linspace(u0, u1, 9)
            topc, botc = [], []
            for i_, u in enumerate(us):
                f = i_ / (len(us) - 1)
                hh = h0_ + (h1_ - h0_) * f + math.sin(math.pi * f) * 1.8
                topc.append(H(*pt(seg, u, dT)[0], hh))
                botc.append(H(*pt(seg, u, dT)[0], max(ry(dT) + 0.3, hh - 3.2 + 1.2 * math.sin(math.pi * f))))
            truss(W, botc, topc, 0.22, 0.11, last_vertical=True)


def build_pitch_and_details(mbs):
    pm = mbs["pitch"]
    poly = []
    for seg in [s[0] for s in SEGS]:
        for p in samples(seg, 5.0):
            poly.append(pt(seg, p, -0.25)[0])
    for i in range(len(poly)):
        a_, b_ = poly[i], poly[(i + 1) % len(poly)]
        tri = [(0, 0), a_, b_]
        pm.face([H(x, z, 0.0) for x, z in tri], uvs=[((x + 58.5) / 117.0, 1 - (z + 40) / 80.0) for x, z in tri], up=UP)
    led = mbs["led"]
    rectp = [(-56.0, -37.5), (56.0, -37.5), (56.0, 37.5), (-56.0, 37.5)]
    L = 0.0
    for i in range(4):
        (x0, z0), (x1, z1) = rectp[i], rectp[(i + 1) % 4]
        sl = math.hypot(x1 - x0, z1 - z0); n_ = int(sl / 8)
        for k in range(n_):
            ta, tb = k / n_, (k + 1) / n_ - 0.004
            xa, za = x0 + (x1 - x0) * ta, z0 + (z1 - z0) * ta; xb, zb = x0 + (x1 - x0) * tb, z0 + (z1 - z0) * tb
            if i in (1, 3) and abs(za) < 5 and abs(zb) < 5:
                continue
            if INTERIOR and i == 2 and max(xa, xb) > min(INT.TUNNEL["u0"], INT.TUNNEL["u1"]) - 0.5 and min(xa, xb) < max(INT.TUNNEL["u0"], INT.TUNNEL["u1"]) + 0.5:
                continue
            ua, ub = (L + ta * sl) / 352.0, (L + tb * sl) / 352.0
            led.quad(H(xa, za, 0.05), H(xb, zb, 0.05), H(xb, zb, 1.0), H(xa, za, 1.0), uvs=[(ua, 0), (ub, 0), (ub, 1), (ua, 1)])
            sx, sz = (0, -0.4) if i == 0 else (0.4, 0) if i == 1 else (0, 0.4) if i == 2 else (-0.4, 0)
            mbs["steel_grey"].quad(H(xa + sx, za + sz, 0.0), H(xb + sx, zb + sz, 0.0), H(xb, zb, 0.995), H(xa, za, 0.995))
        L += sl
    wh = mbs["white"]; net = mbs["net"]
    for s in (-1, 1):
        gx = 52.5 * s
        for gz in (-3.66, 3.66):
            wh.tube(H(gx + 0.06 * s, gz, 0), H(gx + 0.06 * s, gz, 2.5), 0.06, 10)
        wh.tube(H(gx + 0.06 * s, -3.72, 2.44), H(gx + 0.06 * s, 3.72, 2.44), 0.06, 10)
        bx = gx + 2.2 * s
        net.quad(H(gx + 0.12 * s, -3.66, 2.44), H(gx + 0.12 * s, 3.66, 2.44), H(bx, 3.66, 1.6), H(bx, -3.66, 1.6))
        net.quad(H(bx, -3.66, 1.6), H(bx, 3.66, 1.6), H(bx, 3.66, 0.01), H(bx, -3.66, 0.01))
        for gz in (-3.68, 3.68):
            net.face([H(gx + 0.12 * s, gz, 0.01), H(gx + 0.12 * s, gz, 2.44), H(bx, gz, 1.6), H(bx, gz, 0.01)])
        for gz in (-34, 34):
            wh.tube(H(gx, gz, 0), H(gx, gz, 1.5), 0.025, 6)
    for cx in (-9.0, 9.0):
        z0 = 34.0 + 3.2
        for k in range(10):
            a0, a1 = math.pi * k / 10, math.pi * (k + 1) / 10
            r = 1.4
            p = lambda a, x: H(cx + x, z0 + 0.6 - r * math.cos(a) * 0.9, r * math.sin(a) * 1.4)
            mbs["dugout"].quad(p(a0, -6), p(a0, 6), p(a1, 6), p(a1, -6))
        mbs["concrete_dark"].box(H(cx, z0 + 1.65, 0.8), (12.0, 0.3, 1.6), faces="nobottom")
        for k in range(12):
            mbs["red"].box(H(cx - 5.5 + k, z0 + 1.1, 0.45), (0.8, 0.5, 0.15))
    mbs["concrete_dark"].box(H(0, 34 + 4.6, 1.4), (4.0, 3.0, 2.8), faces="nobottom")
    mbs["vom"].quad(H(-1.6, 34 + 3.04, 0.01), H(1.6, 34 + 3.04, 0.01), H(1.6, 34 + 3.04, 2.5), H(-1.6, 34 + 3.04, 2.5))
    # big screens in the NE and SW corners
    for seg, h in (("NE", 36.0), ("SW", 16.5)):
        (x, z), nrm = pt(seg, -45 if seg == "NE" else 135, 4.0)
        yaw = math.atan2(nrm[1], nrm[0]); tx, tz = -nrm[1], nrm[0]
        w, hh = 17.0, 7.5; c = np.array([x, z])
        p = [c - np.array([tx, tz]) * w / 2, c + np.array([tx, tz]) * w / 2]
        f = 0.06
        mbs["screen"].quad(H(*(p[0] + np.array(nrm) * f), h - hh / 2), H(*(p[1] + np.array(nrm) * f), h - hh / 2),
                           H(*(p[1] + np.array(nrm) * f), h + hh / 2), H(*(p[0] + np.array(nrm) * f), h + hh / 2),
                           uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        mbs["steel_grey"].box(H(x - nrm[0] * 0.5, z - nrm[1] * 0.5, h), (1.0, w + 0.8, hh + 0.8), yaw)
    (x, z), _ = pt("S", 0.0, ROOFS["low"]["df"] + 1)
    mbs["steel_grey"].box(H(x, z, roof_y("low", 3.0) - 2.9), (18.0, 2.0, 1.2))


def build_surroundings(mbs):
    rng = np.random.default_rng(7)
    # plaza ring around the stadium: wide on the east (forecourt), narrower elsewhere
    outer_in, outer_out = [], []
    for seg in [s[0] for s in SEGS]:
        for p in samples(seg, 5.0)[:-1]:
            (x, z), nrm = pt(seg, p, ROOFS[SEG[seg][5]]["db"] + 0.0)
            outer_in.append((x, z))
    n = len(outer_in)
    for x, z in outer_in:
        ang = math.atan2(z, x)
        w = 18.0
        if x > 50: w = 18 + 60 * max(0, math.cos(ang)) ** 2      # east forecourt
        if z > 60: w = min(w, 6.0)                                  # railway side (south)
        ln = math.hypot(x, z)
        outer_out.append((x + x / ln * w, z + z / ln * w))
    pv = mbs["paving"]
    for i in range(n):
        j = (i + 1) % n
        pv.face([H(*outer_in[i], 0.0), H(*outer_in[j], 0.0), H(*outer_out[j], 0.0), H(*outer_out[i], 0.0)], up=UP, scale=4.0)
    # red paving band ring around the forecourt edge (separate faces, no overlap: an outer strip)
    red_out = []
    for x, z in outer_out:
        ln = math.hypot(x, z); red_out.append((x + x / ln * 3.0, z + z / ln * 3.0))
    for i in range(n):
        j = (i + 1) % n
        mbs["paving_red"].face([H(*outer_out[i], 0.0), H(*outer_out[j], 0.0), H(*red_out[j], 0.0), H(*red_out[i], 0.0)], up=UP, scale=4.0)
    # ground beyond, out to 700 m (ring, so nothing sits underneath the plaza)
    for i in range(n):
        j = (i + 1) % n
        a_, b_ = red_out[i], red_out[j]
        A_ = (a_[0] / math.hypot(*a_) * 700, a_[1] / math.hypot(*a_) * 700)
        B_ = (b_[0] / math.hypot(*b_) * 700, b_[1] / math.hypot(*b_) * 700)
        mbs["ground"].face([H(*a_, -0.02), H(*b_, -0.02), H(*B_, -0.02), H(*A_, -0.02)], up=UP, scale=16.0)
    # forecourt football disc as a raised paving inset (2 cm proud, its own surface)
    cx = A + ROOFS["mid"]["db"] + 34.0
    k = 48
    for i in range(k):
        a0, a1 = 2 * math.pi * i / k, 2 * math.pi * (i + 1) / k
        P = lambda a: (cx + 20 * math.cos(a), 20 * math.sin(a))
        tri = [(cx, 0.0), P(a0), P(a1)]
        mbs["forecourt"].face([H(x, z, 0.08) for x, z in tri], uvs=[((x - cx) / 40 + 0.5, (z) / 40 + 0.5) for x, z in tri], up=UP)
        for (x0_, z0_), (x1_, z1_) in ((P(a0), P(a1)),):
            mbs["forecourt"].quad(H(x0_, z0_, 0.0), H(x1_, z1_, 0.0), H(x1_, z1_, 0.08), H(x0_, z0_, 0.08), uvs=[(0, 0), (1, 0), (1, 0.01), (0, 0.01)])
    # Bridgewater Canal along the north, with towpath and a footbridge
    cz0, cz1 = -(B + ROOFS["high"]["db"] + 34.0), -(B + ROOFS["high"]["db"] + 50.0)
    mbs["water"].quad(H(-700, cz1, -0.6), H(700, cz1, -0.6), H(700, cz0, -0.6), H(-700, cz0, -0.6), up=UP, scale=12.0)
    for zz, sgn in ((cz0, 1), (cz1, -1)):
        mbs["concrete_dark"].quad(H(-700, zz, -0.6), H(700, zz, -0.6), H(700, zz, 0.12), H(-700, zz, 0.12), scale=2.0)
        mbs["paving"].quad(H(-700, zz, 0.12), H(700, zz, 0.12), H(700, zz + sgn * 3.0, 0.12), H(-700, zz + sgn * 3.0, 0.12), up=UP, scale=4.0)
    for x in (-60.0,):
        mbs["steel_grey"].box(H(x, (cz0 + cz1) / 2, 3.2), (3.5, abs(cz1 - cz0) + 8, 0.5))
        for zz in (cz0 + 1, cz1 - 1):
            mbs["steel_grey"].box(H(x, zz, 1.5), (3.5, 0.6, 3.0))
    rng2 = np.random.default_rng(11)
    for k_ in range(90):
        x = rng2.uniform(-320, 320); z = rng2.choice([cz0 + 5.5, cz1 - 5.5]) + rng2.uniform(-1.5, 1.5)
        build_tree(mbs, x, z, rng2.uniform(7, 12), rng2)
    # railway: ballast bed + four running rails directly behind the south stand
    rz0, rz1 = B + ROOFS["low"]["db"] + 9.0, B + ROOFS["low"]["db"] + 27.0
    mbs["ballast"].quad(H(-700, rz0, 0.05), H(700, rz0, 0.05), H(700, rz1, 0.05), H(-700, rz1, 0.05), up=UP, scale=4.0)
    for k_ in range(4):
        zc = rz0 + 3.0 + k_ * 4.2
        for off in (-0.72, 0.72):
            mbs["rail"].beam(H(-700, zc + off, 0.22), H(700, zc + off, 0.22), 0.07, 0.15)
    # catenary masts
    for x in np.arange(-680, 700, 60):
        mbs["steel_grey"].beam(H(x, rz0 - 0.5, 0.05), H(x, rz0 - 0.5, 7.5), 0.25)
        mbs["steel_grey"].beam(H(x, rz0 - 0.5, 7.3), H(x, rz1 - 2, 7.3), 0.2)
    # embankment strip with trees between plaza and railway
    mbs["grass"].quad(H(-700, rz0 - 6.0, 0.0), H(700, rz0 - 6.0, 0.0), H(700, rz0, 0.05), H(-700, rz0, 0.05), up=UP)
    mbs["grass"].quad(H(-700, rz1, 0.05), H(700, rz1, 0.05), H(700, rz1 + 8, 0.0), H(-700, rz1 + 8, 0.0), up=UP)
    # terraced houses south of the railway (Victorian two-up two-down rows)
    rowz = [rz1 + 18 + 26 * i for i in range(6)]
    for i, zr in enumerate(rowz):
        x = -260.0
        while x < 260:
            run = int(rng.integers(8, 18))
            hrun = 5.6 + rng.uniform(-0.1, 0.25)
            for h_ in range(run):
                w = 5.0
                build_house(mbs, x + w / 2, zr, w, 8.5, hrun, i % 2 == 1, (h_ == 0, h_ == run - 1))
                x += w
            x += rng.uniform(8, 14)   # side street
        mbs["asphalt"].quad(H(-280, zr + 9, 0.10), H(280, zr + 9, 0.10), H(280, zr + 17, 0.10), H(-280, zr + 17, 0.10), up=UP, scale=8.0)
    # trees
    for k_ in range(140):
        x = rng.uniform(-300, 300); z = rng.choice([rz0 - 3.0, rz1 + 4.0]) + rng.uniform(-2, 2)
        build_tree(mbs, x, z, rng.uniform(6, 11), rng)
    # industrial sheds to the north and west, car parks east
    for k_ in range(26):
        ang = rng.uniform(0, 2 * math.pi); rad = rng.uniform(190, 420)
        x, z = rad * math.cos(ang), rad * math.sin(ang)
        if z > 120 or (x > 80 and abs(z) < 120 and rad < 230):
            continue
        w, d, h = rng.uniform(30, 80), rng.uniform(25, 60), rng.uniform(8, 16)
        mbs["panel_grey"].box(H(x, z, h / 2), (w, d, h), rng.uniform(0, 0.3), uv_scale=4.0, faces="nobottom")


def build_house(mbs, x, z, w, d, h, flip, gables=(True, True)):
    hb = mbs["house_brick"]; sl = mbs["slate"]
    x0, x1 = x - w / 2, x + w / 2; z0, z1 = z - d / 2, z + d / 2
    ridge = h + 2.6
    for (ax, az), (bx, bz) in (((x0, z0), (x1, z0)), ((x1, z1), (x0, z1))):
        hb.quad(H(ax, az, 0), H(bx, bz, 0), H(bx, bz, h), H(ax, az, h), scale=2.0)
    for xx, g in ((x0, gables[0]), (x1, gables[1])):
        if g:
            hb.face([H(xx, z0, 0), H(xx, z1, 0), H(xx, z1, h), H(xx, z, ridge), H(xx, z0, h)], scale=2.0)
    sl.quad(H(x0, z0 - 0.3, h - 0.15), H(x1, z0 - 0.3, h - 0.15), H(x1, z, ridge), H(x0, z, ridge), up=UP, scale=2.0)
    sl.quad(H(x1, z1 + 0.3, h - 0.15), H(x0, z1 + 0.3, h - 0.15), H(x0, z, ridge), H(x1, z, ridge), up=UP, scale=2.0)
    hb.box(H(x1 - 0.4, z, ridge + 0.6), (0.6, 1.0, 1.4), uv_scale=2.0, faces="nobottom")
    # windows and door as dark glass on the street face (1 cm proud)
    zf = z0 - 0.04
    mbs["glass_dark"].quad(H(x - 1.6, zf, 3.4), H(x - 0.2, zf, 3.4), H(x - 0.2, zf, 4.8), H(x - 1.6, zf, 4.8))
    mbs["glass_dark"].quad(H(x + 0.4, zf, 3.4), H(x + 1.8, zf, 3.4), H(x + 1.8, zf, 4.8), H(x + 0.4, zf, 4.8))
    mbs["glass_dark"].quad(H(x - 1.6, zf, 0.9), H(x + 0.2, zf, 0.9), H(x + 0.2, zf, 2.3), H(x - 1.6, zf, 2.3))
    mbs["anthracite"].quad(H(x + 0.8, zf, 0.0), H(x + 1.8, zf, 0.0), H(x + 1.8, zf, 2.2), H(x + 0.8, zf, 2.2))


def build_tree(mbs, x, z, h, rng):
    mbs["bark"].tube(H(x, z, 0), H(x, z, h * 0.45), 0.18, 6)
    r = h * 0.32; cz = h * 0.62
    ico = [(0, 0, 1), (0.894, 0, 0.447), (0.276, 0.851, 0.447), (-0.724, 0.526, 0.447), (-0.724, -0.526, 0.447), (0.276, -0.851, 0.447),
           (0.724, 0.526, -0.447), (-0.276, 0.851, -0.447), (-0.894, 0, -0.447), (-0.276, -0.851, -0.447), (0.724, -0.526, -0.447), (0, 0, -1)]
    faces = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5), (0, 5, 1), (1, 6, 2), (2, 7, 3), (3, 8, 4), (4, 9, 5), (5, 10, 1),
             (6, 7, 2), (7, 8, 3), (8, 9, 4), (9, 10, 5), (10, 6, 1), (11, 7, 6), (11, 8, 7), (11, 9, 8), (11, 10, 9), (11, 6, 10)]
    jit = [1 + rng.uniform(-0.18, 0.18) for _ in ico]
    P = [H(x + vx * r * j, z + vy * r * j, cz + vz * r * 0.9 * j) for (vx, vy, vz), j in zip(ico, jit)]
    for f in faces:
        mbs["tree"].face([P[i] for i in f], scale=2.0)


# ---------------------------------------------------------------- seats, zones, sightlines, accessibility
def block_code(seg, t, bi):
    if seg == "N": return f"N{t}4{bi:02d}"
    if seg == "NE": return f"NE{t}4{19 + bi}"
    if seg == "NW": return f"NW{t}4{29 + bi}"
    if seg == "E": return f"E{t}{29 + bi}"
    if seg == "W": return f"W{t}{bi:02d}"
    if seg == "S": return f"S{t}{bi:02d}"
    if seg == "SE": return f"SE{t}{39 + bi}"
    if seg == "SW": return f"SW{t}{9 + bi}"


def zones_for(seg, t, bi, row, nrow, platform=False):
    z = []
    if seg == "W": z.append("home")
    if (seg, t) in RAIL_BLOCKS and bi in RAIL_BLOCKS[(seg, t)]: z.append("standing")
    if (seg == "SW" and t == 1) or (seg == "W" and t == 1 and bi == 1) or (seg == "W" and t == 2 and bi in (1, 2, 3)):
        z.append("family")
    if (seg == "SE") or (seg == "E" and t == 1 and bi == 5) or (seg == "S" and bi == 1):
        z.append("away")
    if (seg == "N" and t == 2 and 3 <= bi <= 5) or (seg == "S" and 3 <= bi <= 5 and row >= 31):
        z.append("hospitality")
    if platform:
        z.append("accessible")
    if not z:
        z.append("general")
    return z


ZONE_BITS = {"general": 0, "home": 1, "standing": 2, "family": 3, "away": 4, "hospitality": 5, "accessible": 6}


def focus_distance(x, z):
    """Horizontal distance from a plan point outside the pitch to the nearest point of the touchline/goal-line rectangle."""
    dx = max(abs(x) - 52.5, 0.0); dz = max(abs(z) - 34.0, 0.0)
    return math.hypot(dx, dz)


def gen_seats():
    pos, yaw, meta, extra, blocks = [], [], [], [], []
    AISLE, SWD = 0.6, 0.47
    for seg, kind, stand, code, tiers, roof, nb, _, style in SEGS:
        bounds = block_bounds(seg)
        for t in tiers:
            sp = TIER_SPEC[t]; T = treads(seg, t); n = nrows(seg, t)
            for bi in range(1, nb + 1):
                ba, bb = bounds[bi - 1], bounds[bi]
                bid = block_code(seg, t, bi)
                blk = dict(id=bid, stand=stand, seg=seg, tier=t, index=bi, rows=[], start=len(pos))
                zs = set()
                for k, (d0, d1, y, kindr) in enumerate(T):
                    rownum = k + 1
                    if kindr == "row":
                        d = d0 + 0.42
                        width_seat = SWD
                    else:
                        d = d0 + 0.9
                        width_seat = None
                    sg = 1 if bb > ba else -1; c = (ba + bb) / 2
                    if kind == "straight":
                        avail = abs(bb - ba) - 2 * AISLE
                        if kindr == "row":
                            m = int(avail / SWD); us = [c + sg * (j - (m - 1) / 2) * SWD for j in range(m)]
                            types = [0] * m
                        else:   # platform: [wheelchair 1.0 m][companion 0.55 m] pairs
                            pair = 1.55; m = int(avail / pair)
                            us, types = [], []
                            for j in range(m):
                                u0 = c + sg * ((j - (m - 1) / 2) * pair)
                                us += [u0 - sg * 0.27, u0 + sg * 0.5]; types += [1, 2]
                    else:
                        rr = R + d; arc = math.radians(abs(bb - ba)) * rr; avail = arc - 2 * AISLE
                        if kindr == "row":
                            m = int(avail / SWD); da = math.degrees(SWD / rr)
                            us = [c + sg * (j - (m - 1) / 2) * da for j in range(m)]; types = [0] * m
                        else:
                            pair = 1.55; m = int(avail / pair); dp = math.degrees(pair / rr)
                            us, types = [], []
                            for j in range(m):
                                u0 = c + sg * (j - (m - 1) / 2) * dp
                                us += [u0 - sg * math.degrees(0.27 / rr), u0 + sg * math.degrees(0.5 / rr)]; types += [1, 2]
                    row_start = len(pos); num = 0
                    for idx, (u, ty) in enumerate(zip(us, types)):
                        if (seg, t) in VOMS and VOMR[(seg, t)][0] <= k < VOMR[(seg, t)][1]:
                            if any(abs(u - vc) < hw * 1.06 + (0.1 if kind == "straight" else 0.0) for vc, hw in VOMS[(seg, t)]):
                                continue
                        if INTERIOR and seg == INT.TUNNEL["seg"] and t == 1 and y < INT.TUNNEL["ymax"] and \
                                min(INT.TUNNEL["u0"], INT.TUNNEL["u1"]) - 0.3 < u < max(INT.TUNNEL["u0"], INT.TUNNEL["u1"]) + 0.3:
                            continue
                        num += 1
                        (x, z), nrm = pt(seg, u, d)
                        pos.append((x, z, y)); yaw.append(math.atan2(nrm[1], nrm[0]))
                        covered = 1 if d > ROOFS[roof]["df"] + 2.0 else 0
                        aisle = 1 if (idx == 0 or idx == len(us) - 1) and ty == 0 else 0
                        zl = zones_for(seg, t, bi, rownum, n, kindr == "platform"); zs.update(zl)
                        zmask = sum(1 << ZONE_BITS[q] for q in zl)
                        if ty == 0 and (seg, t) in RAIL_BLOCKS and bi in RAIL_BLOCKS[(seg, t)]:
                            ty = 4
                        # ---- sightline: C-value (mm) against the row in front, focus = nearest touchline/goal line
                        eye_h = y + (EYE_WHEEL if ty == 1 else EYE)
                        fx, fz = x - nrm[0] * 0.05, z - nrm[1] * 0.05
                        D = focus_distance(fx, fz)
                        cval = -32768; balcony = 0
                        if k >= 1:
                            Tr = d - (T[k - 1][0] + 0.42) if kindr == "row" else d - (T[k - 1][0] + 0.42)
                            Df = max(0.5, D - Tr)
                            Rf = T[k - 1][2] + EYE
                            N_ = eye_h - Rf
                            cval = int(round((Df * (Rf + N_) / (Df + Tr) - Rf) * 1000))
                        elif t > 1:
                            Db = max(0.5, D - (d - (sp["d0"] - 0.3)))
                            Hb = sp["y0"] + 1.05
                            cval = int(round((eye_h * Db / D - Hb) * 1000))
                            balcony = 1 if cval < 0 else 0
                        # standing check for wheelchair users: can they see the focus over standing fans in front?
                        stand_ok = 255
                        if ty == 1:
                            Tr = d - (T[k - 1][0] + 0.42); Df = max(0.5, D - Tr)
                            Rs = T[k - 1][2] + EYE_STAND
                            cst = (Df * eye_h / (Df + Tr)) - Rs
                            stand_ok = 1 if cst >= 0 else 0
                        # overhang cut-off: tier above limits the upward view; height above the centre spot
                        ovh = 65535
                        if (t + 1) in tiers:
                            sd, sy_ = soffit(seg, t + 1)[0]
                            if d > sd:
                                slope = (sy_ - eye_h) / (d - sd)
                                dc = math.hypot(fx, fz)
                                hc = eye_h + slope * dc
                                ovh = int(max(0, min(65000, hc * 10)))
                        # step count from the nearest entry (vomitory row 10 on lower straights, front gangway on upper tiers, back concourse otherwise)
                        entries = [len(T)]
                        if (seg, t) in VOMS: entries.append(VOMR[(seg, t)][0])
                        if t > 1: entries.append(0)
                        steps = min(abs(k - e) for e in entries)
                        if ty == 0 and aisle and steps <= 6:
                            ty = 3     # easy-access aisle seat
                        flags = covered | (aisle << 1) | (balcony << 2)
                        meta.append((len(blocks), rownum, num, flags))
                        extra.append((max(-32767, min(32767, cval)), ovh, ty, min(255, steps), zmask, stand_ok))
                    blk["rows"].append([rownum, row_start, len(pos) - row_start, "P" if kindr == "platform" else str(rownum)])
                blk["count"] = len(pos) - blk["start"]
                blk["zones"] = sorted(zs)
                blocks.append(blk)
    return np.array(pos), np.array(yaw), meta, extra, blocks


def seats_mesh(pos, yaw, extra, coll):
    """Low-poly seat geometry for the .blend; wheelchair spaces become blue floor tiles."""
    def template(parts):
        tv, tf = [], []
        for (cx, cy, cz), (sx, sy, sz), tilt in parts:
            base = len(tv); hx, hy, hz = sx / 2, sy / 2, sz / 2
            for z_ in (-hz, hz):
                for y_ in (-hy, hy):
                    for x_ in (-hx, hx):
                        yy = y_ * math.cos(tilt) - z_ * math.sin(tilt); zz = y_ * math.sin(tilt) + z_ * math.cos(tilt)
                        tv.append((cx + x_, cy + yy, cz + zz))
            for q in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
                tf.append(tuple(base + i for i in q))
        return np.array(tv), np.array(tf)
    seat_t = template([((0, -0.02, 0.43), (0.44, 0.42, 0.06), 0.0), ((0, 0.20, 0.70), (0.44, 0.05, 0.48), -0.18), ((0, 0.12, 0.2), (0.06, 0.06, 0.4), 0.0)])
    wc_t = template([((0, 0.0, 0.01), (0.9, 1.3, 0.012), 0.0)])
    for name, tpl, sel, mat_ in (("Seats", seat_t, lambda e: e[2] != 1, MATS["seat"]), ("Wheelchair_Spaces", wc_t, lambda e: e[2] == 1, MATS["access"])):
        idx = np.array([i for i, e in enumerate(extra) if sel(e)])
        if len(idx) == 0: continue
        tv, tf = tpl
        P = pos[idx]; Y = yaw[idx]; Nn = len(idx); nv = len(tv)
        co, si = np.cos(Y), np.sin(Y)
        lx, ly, lz = tv[:, 0], tv[:, 1], tv[:, 2]
        X = P[:, 0:1] + lx[None] * (-si[:, None]) + ly[None] * (-co[:, None])
        Yb = P[:, 1:2] + lx[None] * co[:, None] + ly[None] * (-si[:, None])
        Z = P[:, 2:3] + lz[None]
        verts = np.stack([X, Yb, Z], -1).reshape(-1, 3)
        faces = (tf[None] + (np.arange(Nn) * nv)[:, None, None]).reshape(-1, 4)
        me = bpy.data.meshes.new(name)
        me.vertices.add(len(verts)); me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
        me.loops.add(faces.size); me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
        me.polygons.add(len(faces)); me.polygons.foreach_set("loop_start", (np.arange(len(faces)) * 4).astype(np.int32))
        me.update(calc_edges=True); me.validate(); me.materials.append(mat_)
        ob = bpy.data.objects.new(name, me); coll.objects.link(ob)


def export_egress(pos, yaw, meta, extra, blocks):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from egress_net import build_egress
    G = gdict()
    build_egress(G, pos, yaw, meta, extra, blocks, OUT, PLAN)


def write_seats(pos, yaw, meta, extra, blocks):
    N = len(pos)
    with open(f"{OUT}/seats.bin", "wb") as f:
        arr = np.zeros((N, 4), np.float32)
        arr[:, 0] = -pos[:, 0]; arr[:, 1] = pos[:, 2]; arr[:, 2] = -pos[:, 1]; arr[:, 3] = np.pi - yaw    # mirrored to real handedness
        f.write(arr.tobytes())
        f.write(np.array(meta, np.uint16).tobytes())
        ex = np.array(extra)
        f.write(ex[:, 0].astype(np.int16).tobytes())        # C-value mm
        f.write(ex[:, 1].astype(np.uint16).tobytes())       # overhang cut-off height (dm) or 65535
        f.write(ex[:, 2].astype(np.uint8).tobytes())        # type
        f.write(ex[:, 3].astype(np.uint8).tobytes())        # steps
        f.write(ex[:, 4].astype(np.uint8).tobytes())        # zone bitmask
        f.write(ex[:, 5].astype(np.uint8).tobytes())        # wheelchair standing check (255 n/a)
    meta_json = dict(
        count=int(N), version=2,
        layout_note="float32[x,y,z,yaw]*N | uint16[block,row,seat,flags]*N | int16 C_mm*N | uint16 overhang_dm*N | uint8 type*N | uint8 steps*N | uint8 zones*N | uint8 standOK*N",
        flags="bit0 covered, bit1 aisle, bit2 near touchline hidden by balcony",
        types={"0": "standard", "1": "wheelchair space", "2": "companion seat", "3": "easy-access aisle seat", "4": "rail seat (safe standing)"},
        zones=ZONE_BITS, blocks=blocks, eye=dict(seated=EYE, standing=EYE_STAND, wheelchair=EYE_WHEEL), focus="nearest touchline / goal line",
        tiers={t: dict(TIER_SPEC[t], heights=[round(h, 3) for h in RAKE[t][:45]]) for t in TIER_SPEC},
        roofs=ROOFS, layout=dict(A=A, B=B, R=R),
    )
    with open(f"{OUT}/seats.json", "w") as f:
        json.dump(meta_json, f)


def gdict():
    return dict(pt=pt, SEGS=SEGS, SEG=SEG, STRAIGHT=STRAIGHT, CORNER=CORNER, R=R, A=A, B=B, TIER_SPEC=TIER_SPEC, treads=treads,
                tier_back=tier_back, soffit=soffit, soffit_y=soffit_y, row_d=row_d, row_y=row_y, nrows=nrows, VOMS=VOMS, VOMR=VOMR,
                ROOFS=ROOFS, roof_y=roof_y, block_bounds=block_bounds, samples=samples, PLATFORM_SEGS=PLATFORM_SEGS)


def make_plan(blocks):
    global PLAN
    G = gdict()
    PLAN = INT.plan(G, blocks)
    INT.make_rooms(G, PLAN)
    return PLAN


def main():
    global VOMS, VOMR
    design_rakes()
    VOMS, VOMR = vom_list()
    print("rakes:", {t: (TIER_SPEC[t]["y0"], round(RAKE[t][TIER_SPEC[t]["rows"] - 1], 2)) for t in RAKE})
    if os.environ.get("EGRESS_ONLY"):
        pos, yaw, meta, extra, blocks = gen_seats()
        make_plan(blocks)
        write_seats(pos, yaw, meta, extra, blocks)
        export_egress(pos, yaw, meta, extra, blocks)
        INT.export_json(gdict(), PLAN, OUT)
        return
    if os.environ.get("COUNT_ONLY"):
        pos, yaw, meta, extra, blocks = gen_seats()
        import collections
        c = collections.Counter(); zc = collections.Counter(); tc = collections.Counter()
        for b in blocks: c[b["stand"]] += b["count"]
        for e in extra:
            tc[e[2]] += 1
            for zn, bit in ZONE_BITS.items():
                if e[4] & (1 << bit): zc[zn] += 1
        cv = np.array([e[0] for e in extra if e[0] != -32768])
        print(dict(c), len(pos)); print("types", dict(tc)); print("zones", dict(zc))
        print("C mm p5/p50/p95", np.percentile(cv, [5, 50, 95]))
        print("wheelchair standing ok", sum(1 for e in extra if e[2] == 1 and e[5] == 1), "/", tc[1])
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    root = bpy.data.collections.new("OldTrafford"); scene.collection.children.link(root)
    surr = bpy.data.collections.new("Surroundings"); scene.collection.children.link(surr)
    seats_coll = bpy.data.collections.new("Seats"); scene.collection.children.link(seats_coll)
    int_coll = bpy.data.collections.new("Interior"); scene.collection.children.link(int_coll)
    make_materials()
    keys = list(NAMES.keys())
    mbs = {k: MB() for k in keys}
    pos, yaw, meta, extra, blocks = gen_seats()
    make_plan(blocks)
    build_bowl(mbs); build_junction_caps(mbs); build_vomitories(mbs); build_rails_and_platforms(mbs)
    if INTERIOR:
        INT.build(gdict(), PLAN, mbs)
        INT.export_json(gdict(), PLAN, OUT)
    build_facades(mbs); roof_surface(mbs); roof_steel(mbs); build_pitch_and_details(mbs)
    smb = {k: MB() for k in keys}
    build_surroundings(smb)
    NOUV = {"walls", "stairs", "fit_light", "fit_dark", "lift", "roof_solid"} | {"fin_" + k for k in INT.KINDS}
    INTERIOR_ONLY = {"walls", "stairs", "fit_light", "fit_dark", "lift"} | {"fin_" + k for k in INT.KINDS}
    for k, mb in mbs.items():
        if mb.f: mb.build(NAMES[k], MATS[MATKEY.get(k, k)], int_coll if k in INTERIOR_ONLY else root, uv=k not in NOUV)
    for k, mb in smb.items():
        if mb.f: mb.build("Env_" + NAMES[k], MATS[MATKEY.get(k, k)], surr)
    print("seats:", len(pos), "blocks:", len(blocks))
    seats_mesh(pos, yaw, extra, seats_coll)
    export_egress(pos, yaw, meta, extra, blocks)
    write_seats(pos, yaw, meta, extra, blocks)
    # The plan uses x = east, z = south. Embedded as Blender (X, Y) that is a mirror image of the real stadium
    # (seen from above with north up, east would be on the left), so flip X on everything once, at the end.
    from mathutils import Matrix
    MIR = Matrix.Scale(-1.0, 4, (1.0, 0.0, 0.0))
    for ob in list(bpy.data.objects):
        if ob.type == "MESH":
            ob.data.transform(MIR); ob.data.flip_normals(); ob.data.update()
    # world, sun and camera for renders
    world = bpy.data.worlds.new("World"); scene.world = world; world.use_nodes = True
    wt = world.node_tree; bg = wt.nodes.get("Background")
    try:
        sky = wt.nodes.new("ShaderNodeTexSky")
        sky.sun_elevation = math.radians(26); sky.sun_rotation = math.radians(215)
        wt.links.new(sky.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = 0.35
    except Exception as e:
        print("sky", e)
    sun_d = bpy.data.lights.new("Sun", "SUN"); sun_d.energy = 3.2; sun_d.angle = math.radians(1.2)
    sun = bpy.data.objects.new("Sun", sun_d); sun.rotation_euler = (math.radians(60), 0, math.radians(215)); scene.collection.objects.link(sun)
    cam_d = bpy.data.cameras.new("Camera"); cam_d.lens = 28; cam_d.clip_end = 4000
    cam = bpy.data.objects.new("Camera", cam_d); scene.collection.objects.link(cam); scene.camera = cam
    bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/old_trafford.blend", compress=True)
    for ob in seats_coll.objects:
        ob.select_set(False)
    for ob in int_coll.objects:
        ob.select_set(False)
    for coll_ in (root, surr):
        for ob in coll_.objects:
            ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/old_trafford.glb", export_format="GLB", use_selection=True,
                              export_apply=True, export_image_format="NONE", export_yup=True)
    for ob in bpy.context.scene.objects:
        ob.select_set(False)
    for ob in int_coll.objects:
        ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=f"{OUT}/interior.glb", export_format="GLB", use_selection=True,
                              export_apply=True, export_image_format="NONE", export_yup=True)
    print("done")


main()
