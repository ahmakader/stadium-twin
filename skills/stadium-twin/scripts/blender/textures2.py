"""High-quality procedural PBR texture sets (albedo / normal / roughness) for the Old Trafford build.
Every map is generated here from noise and geometry, so the whole set is original (no third-party images).
Output: <out>/<name>_c.jpg (colour, sRGB), <name>_n.jpg (tangent-space normal, OpenGL +Y), <name>_r.jpg (roughness)."""
import sys, os, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "tex2"
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(1234)
S = 1024


def blur_noise(h, w, sigma, wrap=True):
    p = int(sigma * 3) + 2
    a = rng.random((h, w))
    if wrap:
        a = np.pad(a, ((p, p), (p, p)), mode="wrap")
    im = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(sigma))
    a = np.asarray(im, float)
    if wrap:
        a = a[p:p + h, p:p + w]
    a = (a - a.mean()) / (a.std() + 1e-6)
    return a


def fbm(h, w, base=64, octaves=5, gain=0.5):
    out = np.zeros((h, w)); amp = 1.0
    for o in range(octaves):
        out += amp * blur_noise(h, w, max(0.6, base / 2 ** o) / 2)
        amp *= gain
    out -= out.min(); out /= out.max()
    return out


def normal_from_height(hgt, strength):
    gy, gx = np.gradient(hgt)
    # wrap-aware gradient at edges
    gx[:, 0] = hgt[:, 1] - hgt[:, -1]; gx[:, -1] = hgt[:, 0] - hgt[:, -2]
    gy[0, :] = hgt[1, :] - hgt[-1, :]; gy[-1, :] = hgt[0, :] - hgt[-2, :]
    nx, ny, nz = -gx * strength, gy * strength, np.ones_like(hgt)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / l, ny / l, nz / l], -1)
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def save_set(name, col, hgt, rough, nstrength=3.0, q=90):
    Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).save(f"{OUT}/{name}_c.jpg", quality=q)
    Image.fromarray(normal_from_height(hgt, nstrength)).save(f"{OUT}/{name}_n.jpg", quality=q)
    Image.fromarray(np.clip(rough * 255, 0, 255).astype(np.uint8)).save(f"{OUT}/{name}_r.jpg", quality=q)
    print("set", name)


Y, X = np.mgrid[0:S, 0:S]


def concrete(name="concrete", tint=(172, 170, 164), stains=True):
    n1 = fbm(S, S, 128); n2 = fbm(S, S, 12, 3); n3 = blur_noise(S, S, 0.7)
    pores = (blur_noise(S, S, 1.2) > 2.3).astype(float)
    v = 0.78 + 0.16 * n1 + 0.06 * n2 + 0.015 * n3 - 0.12 * pores
    if stains:
        drip = fbm(S, S, 200, 3)
        streak = blur_noise(S, 1, 4)[:, :1] * 0 + 0
        v *= 1 - 0.10 * np.clip(drip - 0.55, 0, 1) * 3
    # formwork joints every 256 px (tile = 4 m -> joints every 1 m)
    joint = ((X % 256) < 2) | ((Y % 256) < 2)
    v[joint] *= 0.82
    col = np.array(tint)[None, None] * v[..., None]
    hgt = 0.5 * n2 + 0.2 * n3 - 1.2 * pores - 0.8 * joint
    rough = 0.82 + 0.1 * n1 - 0.15 * pores
    save_set(name, col, hgt, rough, 2.0)


def terrace():
    """Terrace concrete with a darker painted nosing band (tile = 1 m x 1 m, nosing along v=0)."""
    n1 = fbm(S, S, 96); n2 = fbm(S, S, 10, 3); n3 = blur_noise(S, S, 0.7)
    v = 0.74 + 0.18 * n1 + 0.06 * n2 + 0.02 * n3
    col = np.array([160, 158, 154])[None, None] * v[..., None]
    gum = (blur_noise(S, S, 1.5) > 2.6)
    col[gum] *= 0.6
    hgt = 0.4 * n2 + 0.2 * n3 - 0.6 * gum
    rough = 0.86 + 0.08 * n1
    save_set("terrace", col, hgt, rough, 2.0)


def brick(name="brick", base=(118, 44, 34), bw=128, bh=42, mortar=6, var=0.22):
    """English stretcher bond; tile = 2 m wide, so a brick = 0.25 m x 0.08 m at bw=128/bh=42 on 1024."""
    row = Y // bh
    off = (row % 2) * (bw // 2)
    Xo = (X + off) % bw
    bid = (row * 7919 + ((X + off) // bw) * 104729) % 9973
    rnd = (np.sin(bid * 12.9898) * 43758.5453) % 1.0
    n = fbm(S, S, 24, 4); n2 = blur_noise(S, S, 0.8)
    m = ((Y % bh) < mortar) | (Xo < mortar)
    tone = 1 + var * (rnd - 0.5) * 2
    col = np.array(base)[None, None] * (tone * (0.86 + 0.18 * n + 0.04 * n2))[..., None]
    # occasional darker 'burnt' headers
    burnt = rnd > 0.92
    col[burnt] *= 0.7
    col[m] = (np.array([150, 144, 134])[None, :] * (0.9 + 0.1 * n[m][:, None]))
    edge = np.minimum(np.minimum((Y % bh) - mortar, bh - (Y % bh)), np.minimum(Xo - mortar, bw - Xo)).astype(float)
    hgt = np.clip(edge / 4.0, 0, 1) * 1.0 + 0.15 * n2 + 0.2 * n
    hgt[m] = -0.3 + 0.1 * n2[m]
    rough = 0.85 + 0.1 * n
    rough[m] = 0.95
    save_set(name, col, hgt, rough, 4.0)


def panels(name, tint, pw=256, ph=512, windows=False, joint=4, gloss=0.38):
    """Composite metal cladding panels: tile 4 m wide x 4 m high, panels 1 m x 2 m (pw/ph px)."""
    n = fbm(S, S, 160, 3); n2 = blur_noise(S, S, 0.8)
    pid = ((X // pw) * 31 + (Y // ph) * 17) % 13
    tone = 1 + 0.035 * (pid / 13.0 - 0.5)
    col = np.array(tint)[None, None] * (tone * (0.93 + 0.07 * n))[..., None]
    jx = (X % pw) < joint; jy = (Y % ph) < joint
    j = jx | jy
    col[j] *= 0.45
    hgt = 0.05 * n2 - 1.0 * j
    rough = gloss + 0.08 * n
    rough[j] = 0.7
    if windows:
        # horizontal strip windows in the middle third of every panel row
        win = ((Y % ph) > ph * 0.38) & ((Y % ph) < ph * 0.62) & ((X % pw) > 18) & ((X % pw) < pw - 18)
        refl = 0.5 + 0.5 * np.clip(1 - (Y % ph - ph * 0.38) / (ph * 0.24), 0, 1)
        col[win] = np.array([32, 44, 52])[None, :] * (0.8 + 0.5 * refl[win][:, None])
        rough[win] = 0.08
        hgt[win] -= 0.4
        fr = win ^ (((Y % ph) > ph * 0.38 + 6) & ((Y % ph) < ph * 0.62 - 6) & ((X % pw) > 24) & ((X % pw) < pw - 24))
        col[fr] = np.array([70, 74, 78])
    save_set(name, col, hgt, rough, 3.0)


def curtain_glass(name="glass_teal", tint=(64, 140, 132), cw=170, ch=340):
    """Teal structural glazing, tile = 6 m x 6 m: mullions every 1 m, transoms every 2 m, sky reflection gradient."""
    n = fbm(S, S, 220, 3)
    gy = 1 - Y / S
    base = np.array(tint)[None, None] * (0.55 + 0.35 * gy[..., None] + 0.12 * n[..., None])
    cid = ((X // cw) * 13 + (Y // ch) * 7) % 11
    base *= (1 + 0.06 * (cid / 11 - 0.5))[..., None]
    mul = ((X % cw) < 7) | ((Y % ch) < 7)
    base[mul] = np.array([196, 204, 206])
    hgt = -1.0 * (~mul) * 0.2 + 0.0
    rough = np.where(mul, 0.35, 0.05) + 0.02 * n
    save_set(name, base, hgt.astype(float), rough, 3.0)


def dark_glass():
    n = fbm(S, S, 200, 3)
    col = np.array([30, 40, 48])[None, None] * (0.8 + 0.4 * n)[..., None]
    mul = ((X % 256) < 6) | ((Y % 512) < 6)
    col[mul] = np.array([80, 84, 88])
    hgt = mul.astype(float) * 0.5
    rough = np.where(mul, 0.4, 0.04)
    save_set("glass_dark", col, hgt, rough, 2.0)


def roofsheet():
    """Long-run aluminium trough sheeting: ribs every 0.25 m (tile 4 m), profile in the normal map."""
    n = fbm(S, S, 200, 3); n2 = blur_noise(S, S, 1.0)
    period = 64
    ph = (X % period) / period
    prof = np.clip(np.abs(ph - 0.5) * 4 - 1.2, -0.6, 0.8)
    hgt = prof * 2.0 + 0.04 * n2
    col = np.array([186, 190, 194])[None, None] * (0.9 + 0.1 * n + 0.03 * prof)[..., None]
    dirt = fbm(S, S, 300, 3)
    col *= (1 - 0.12 * np.clip(dirt - 0.5, 0, 1) * 2)[..., None]
    lap = (Y % 512) < 5
    col[lap] *= 0.8; hgt[lap] -= 0.4
    rough = 0.42 + 0.12 * n
    save_set("roof", col, hgt, rough, 1.4)


def roof_under():
    n = fbm(S, S, 200, 3)
    period = 64
    ph = (X % period) / period
    prof = np.clip(np.abs(ph - 0.5) * 4 - 1.2, -0.6, 0.8)
    col = np.array([150, 154, 160])[None, None] * (0.85 + 0.12 * n - 0.05 * prof)[..., None]
    purlin = (Y % 256) < 10
    col[purlin] = np.array([210, 212, 214])
    hgt = prof * 2.0 + purlin * 1.5
    rough = 0.6 + 0.1 * n
    save_set("roof_under", col, hgt, rough, 1.4)


def paving():
    """Block pavers in herringbone-free stretcher pattern, buff with red-brown accents (tile 4 m)."""
    bw, bh = 52, 26
    row = Y // bh; off = (row % 2) * (bw // 2)
    Xo = (X + off) % bw
    bid = (row * 7919 + ((X + off) // bw) * 104729) % 9973
    rnd = (np.sin(bid * 78.233) * 43758.5453) % 1.0
    n = fbm(S, S, 32, 4)
    j = ((Y % bh) < 2) | (Xo < 2)
    base = np.array([186, 172, 150])
    col = base[None, None] * ((0.86 + 0.14 * rnd) * (0.9 + 0.12 * n))[..., None]
    col[j] = np.array([110, 104, 96])
    hgt = 0.2 * n - 1.0 * j
    rough = 0.82 + 0.1 * n
    save_set("paving", col, hgt, rough, 2.5)


def paving_red():
    bw, bh = 52, 26
    row = Y // bh; off = (row % 2) * (bw // 2)
    Xo = (X + off) % bw
    bid = (row * 7919 + ((X + off) // bw) * 104729) % 9973
    rnd = (np.sin(bid * 78.233) * 43758.5453) % 1.0
    n = fbm(S, S, 32, 4)
    j = ((Y % bh) < 2) | (Xo < 2)
    col = np.array([150, 78, 60])[None, None] * ((0.84 + 0.18 * rnd) * (0.9 + 0.12 * n))[..., None]
    col[j] = np.array([90, 70, 62])
    hgt = 0.2 * n - 1.0 * j
    save_set("paving_red", col, hgt, 0.85 + 0.08 * n, 2.5)


def asphalt():
    n = fbm(S, S, 8, 3); n2 = fbm(S, S, 300, 3); g = blur_noise(S, S, 0.6)
    col = np.array([66, 68, 70])[None, None] * (0.75 + 0.25 * n + 0.12 * n2 + 0.05 * g)[..., None]
    stones = g > 2.2
    col[stones] *= 1.5
    hgt = 0.6 * n + 0.4 * g
    save_set("asphalt", col, hgt, 0.9 - 0.08 * stones, 3.0)


def ballast():
    n = fbm(S, S, 6, 3); g = blur_noise(S, S, 1.6)
    col = np.array([120, 112, 104])[None, None] * (0.6 + 0.5 * n + 0.08 * g)[..., None]
    # sleepers across the track every 0.65 m (tile 4 m): 6 sleepers per tile across Y
    sl = ((Y % 160) < 40) & (np.abs(X - S / 2) < 380)
    col[sl] = np.array([92, 84, 76])[None, :] * (0.85 + 0.2 * n[sl][:, None])
    hgt = 1.0 * n + 0.6 * sl
    save_set("ballast", col, hgt, 0.95 * np.ones_like(n), 4.0)


def slate():
    """Grey-blue slate roof tiles, tile 2 m."""
    th, tw = 64, 96
    row = Y // th; off = (row % 2) * (tw // 2)
    Xo = (X + off) % tw
    bid = (row * 131 + ((X + off) // tw) * 977) % 997
    rnd = (np.sin(bid * 3.1) * 43758.5453) % 1.0
    n = fbm(S, S, 20, 3)
    col = np.array([72, 78, 86])[None, None] * ((0.82 + 0.25 * rnd) * (0.9 + 0.12 * n))[..., None]
    edge = (Y % th) < 4
    col[edge | (Xo < 3)] *= 0.55
    hgt = (Y % th) / th - 1.2 * edge
    save_set("slate", col, hgt, 0.7 + 0.1 * n, 3.0)


def grass_detail():
    """Tiling grass blade detail (normal + roughness) layered over the pitch colour map. tile = 2 m."""
    n1 = blur_noise(S, S, 0.6); n2 = blur_noise(S, S, 2.5)
    blades = np.asarray(Image.fromarray(((rng.random((S, S)) * 255)).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)).resize((S, S)), float)
    # stretch along y to suggest blades
    bl = np.asarray(Image.fromarray(((rng.random((S // 6, S)) * 255)).astype(np.uint8)).resize((S, S), Image.BILINEAR).filter(ImageFilter.GaussianBlur(0.7)), float) / 255
    hgt = 0.7 * bl + 0.3 * (n1 * 0.1) + 0.2 * n2 * 0.1
    col = np.array([70, 128, 58])[None, None] * (0.8 + 0.35 * bl)[..., None]
    save_set("grass", col, hgt, 0.95 - 0.1 * bl, 6.0)


def pitch_colour(ppm=24):
    """Pitch colour map with mowing stripes, line markings and wear; covers x in [-58.5,58.5], z in [-40,40]."""
    W, H = int(117 * ppm), int(80 * ppm)
    xs = (np.arange(W) / ppm) - 58.5; zs = (np.arange(H) / ppm) - 40
    Xm, Zm = np.meshgrid(xs, zs)
    n = fbm(H, W, 60, 4) if False else None
    nn = blur_noise(H, W, 18, wrap=False); nn2 = blur_noise(H, W, 3, wrap=False)
    stripe = (np.floor((Xm + 52.5) / (105 / 18)) % 2)
    g1 = np.array([46, 112, 42]); g2 = np.array([64, 136, 54])
    col = g1 * (1 - stripe[..., None]) + g2 * stripe[..., None]
    col = col * (0.97 + 0.04 * (np.floor((Zm + 34) / (68 / 9)) % 2))[..., None]
    col *= (0.92 + 0.05 * nn + 0.02 * nn2)[..., None]
    inside = (np.abs(Xm) <= 55.5) & (np.abs(Zm) <= 37)
    col[~inside] = np.array([40, 84, 40]) * (0.95 + 0.05 * nn[~inside])[:, None]
    for gx in (-52.5, 52.5):
        d = np.hypot((Xm - gx) * 0.8, Zm)
        wear = np.exp(-(d / 7.0) ** 2) * 0.28
        col = col * (1 - wear[..., None]) + np.array([126, 116, 76]) * wear[..., None]
    for gx in (-52.5, 52.5):  # linesman runs
        for side in (-34.6, 34.6):
            d = np.abs(Zm - side) + np.maximum(0, np.abs(Xm) - 52.5) * 9
            pass
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(img)
    lw = max(2, int(0.12 * ppm))
    LC = (238, 242, 232)
    P = lambda x, z: ((x + 58.5) * ppm, (z + 40) * ppm)
    def line(a, b): dr.line([P(*a), P(*b)], fill=LC, width=lw)
    def rect(x0, z0, x1, z1):
        line((x0, z0), (x1, z0)); line((x1, z0), (x1, z1)); line((x1, z1), (x0, z1)); line((x0, z1), (x0, z0))
    def arc(cx, cz, r, a0, a1, steps=120):
        pts = [P(cx + r * math.cos(math.radians(a)), cz + r * math.sin(math.radians(a))) for a in np.linspace(a0, a1, steps)]
        dr.line(pts, fill=LC, width=lw)
    rect(-52.5, -34, 52.5, 34); line((0, -34), (0, 34)); arc(0, 0, 9.15, 0, 360, 240)
    for s in (-1, 1):
        gx = 52.5 * s
        rect(min(gx, gx - s * 16.5), -20.16, max(gx, gx - s * 16.5), 20.16)
        rect(min(gx, gx - s * 5.5), -9.16, max(gx, gx - s * 5.5), 9.16)
        px = gx - s * 11
        dr.ellipse([P(px - 0.15, -0.15), P(px + 0.15, 0.15)], fill=LC)
        ang = math.degrees(math.acos(5.5 / 9.15))
        arc(px, 0, 9.15, 180 - ang, 180 + ang) if s > 0 else arc(px, 0, 9.15, -ang, ang)
        for cz, a0 in ((-34, 90 if s > 0 else 0), (34, 180 if s > 0 else 270)):
            arc(gx, cz, 1.0, a0, a0 + 90, 24)
    dr.ellipse([P(-0.15, -0.15), P(0.15, 0.15)], fill=LC)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    img.save(f"{OUT}/pitch_c.jpg", quality=90)
    print("pitch")


def forecourt():
    """East forecourt disc: a giant football in red-brown and buff paving, 40 m across (image 1024 = 40 m)."""
    col = np.zeros((S, S, 3)); r = np.hypot(X - S / 2, Y - S / 2) / (S / 2)
    n = fbm(S, S, 30, 3)
    col[:] = np.array([196, 182, 160])
    # truncated-icosahedron-ish pattern: central pentagon + 5 surrounding patches
    img = Image.new("RGB", (S, S), (198, 184, 162)); dr = ImageDraw.Draw(img)
    def poly(cx, cy, rad, rot, fill):
        pts = [(cx + rad * math.cos(rot + k * 2 * math.pi / 5), cy + rad * math.sin(rot + k * 2 * math.pi / 5)) for k in range(5)]
        dr.polygon(pts, fill=fill)
    poly(S / 2, S / 2, S * 0.13, -math.pi / 2, (150, 74, 56))
    for k in range(5):
        a = -math.pi / 2 + k * 2 * math.pi / 5 + math.pi / 5
        poly(S / 2 + math.cos(a) * S * 0.36, S / 2 + math.sin(a) * S * 0.36, S * 0.11, a, (150, 74, 56))
    arr = np.asarray(img, float)
    bw, bh = 26, 13
    row = Y // bh; off = (row % 2) * (bw // 2); Xo = (X + off) % bw
    j = ((Y % bh) < 1) | (Xo < 1)
    arr = arr * (0.9 + 0.12 * n)[..., None]
    arr[j] *= 0.7
    arr[r > 1] = np.array([186, 172, 150])
    ring = (r > 0.97) & (r <= 1.0)
    arr[ring] = np.array([120, 110, 100])
    alpha = (r <= 1.0)
    hgt = -1.0 * j
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(f"{OUT}/forecourt_c.jpg", quality=90)
    Image.fromarray(normal_from_height(hgt.astype(float), 2.0)).save(f"{OUT}/forecourt_n.jpg", quality=90)
    print("forecourt")


def ground():
    """Generic surroundings: worn asphalt and dirt, tile 16 m."""
    n = fbm(S, S, 220, 4); n2 = fbm(S, S, 10, 3)
    col = np.array([96, 98, 94])[None, None] * (0.72 + 0.3 * n + 0.08 * n2)[..., None]
    patch = fbm(S, S, 300, 3) > 0.62
    col[patch] = col[patch] * 0.6 + np.array([70, 84, 52]) * 0.4
    save_set("ground", col, 0.5 * n2, 0.92 + 0 * n, 1.5)


def water():
    n = fbm(S, S, 40, 4); n2 = blur_noise(S, S, 3)
    col = np.array([38, 58, 52])[None, None] * (0.8 + 0.3 * n)[..., None]
    save_set("water", col, 0.6 * n + 0.2 * n2, 0.08 + 0.05 * n, 3.0)


def kit_number_atlas():
    pass


if __name__ == "__main__":
    concrete(); concrete("concrete_dark", (112, 112, 114), stains=False); terrace()
    brick(); brick("brick_house", (124, 62, 44), var=0.3)
    panels("panel_grey", (156, 162, 168)); panels("panel_grey_win", (150, 156, 162), windows=True)
    panels("panel_white", (226, 228, 228), gloss=0.32); panels("panel_white_win", (224, 226, 226), windows=True)
    panels("anthracite", (58, 62, 66), gloss=0.45)
    panels("panel_mid", (118, 122, 128), gloss=0.4); panels("panel_red", (178, 20, 28), gloss=0.35); panels("panel_red_win", (172, 20, 28), windows=True)
    water()
    curtain_glass(); dark_glass(); roofsheet(); roof_under()
    paving(); paving_red(); asphalt(); ballast(); slate(); grass_detail(); pitch_colour(); forecourt(); ground()
