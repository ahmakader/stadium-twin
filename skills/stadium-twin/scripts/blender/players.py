"""Rigged, animated footballer for the Old Trafford demo (Blender 5.x, background mode).
Mesh: skin-modifier body (subdivided) parented to an armature with automatic weights.
Material slots: Skin, Hair, Shirt, Shorts, Socks, Boots (the web app recolours kits per team).
Actions (in place): Idle, Jog, Sprint, Kick, Celebrate, KeeperReady. Character faces -Y (three.js +Z after export)."""
import bpy, math, sys, os
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(HERE, "..", "out")
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 30

# ------------------------------------------------------------------ skeleton (metres)
J = {
    "pelvis": (0, 0, 0.98), "spine": (0, 0.0, 1.16), "chest": (0, 0.0, 1.34), "neck": (0, 0.0, 1.53), "head": (0, -0.01, 1.64), "top": (0, -0.005, 1.80),
    "sh.L": (0.2, 0, 1.45), "ua.L": (0.235, 0.01, 1.31), "el.L": (0.265, 0.02, 1.17), "fa.L": (0.28, 0.01, 1.06), "wr.L": (0.29, 0.0, 0.95), "hd.L": (0.30, -0.01, 0.86),
    "sh.R": (-0.2, 0, 1.45), "ua.R": (-0.235, 0.01, 1.31), "el.R": (-0.265, 0.02, 1.17), "fa.R": (-0.28, 0.01, 1.06), "wr.R": (-0.29, 0.0, 0.95), "hd.R": (-0.30, -0.01, 0.86),
    "hip.L": (0.10, 0, 0.93), "th.L": (0.104, -0.012, 0.73), "kn.L": (0.105, -0.015, 0.52), "cf.L": (0.108, 0.01, 0.34), "an.L": (0.11, 0.02, 0.1), "to.L": (0.11, -0.16, 0.035),
    "hip.R": (-0.10, 0, 0.93), "th.R": (-0.104, -0.012, 0.73), "kn.R": (-0.105, -0.015, 0.52), "cf.R": (-0.108, 0.01, 0.34), "an.R": (-0.11, 0.02, 0.1), "to.R": (-0.11, -0.16, 0.035),
}
RAD = {
    "pelvis": (0.16, 0.12), "spine": (0.15, 0.11), "chest": (0.19, 0.125), "neck": (0.06, 0.06), "head": (0.098, 0.11), "top": (0.08, 0.09),
    "sh.L": (0.075, 0.075), "ua.L": (0.058, 0.06), "el.L": (0.045, 0.045), "fa.L": (0.045, 0.042), "wr.L": (0.033, 0.03), "hd.L": (0.045, 0.028),
    "sh.R": (0.075, 0.075), "ua.R": (0.058, 0.06), "el.R": (0.045, 0.045), "fa.R": (0.045, 0.042), "wr.R": (0.033, 0.03), "hd.R": (0.045, 0.028),
    "hip.L": (0.095, 0.1), "th.L": (0.085, 0.09), "kn.L": (0.058, 0.06), "cf.L": (0.06, 0.068), "an.L": (0.042, 0.05), "to.L": (0.045, 0.036),
    "hip.R": (0.095, 0.1), "th.R": (0.085, 0.09), "kn.R": (0.058, 0.06), "cf.R": (0.06, 0.068), "an.R": (0.042, 0.05), "to.R": (0.045, 0.036),
}
EDGES = [("pelvis", "spine"), ("spine", "chest"), ("chest", "neck"), ("neck", "head"), ("head", "top"),
         ("chest", "sh.L"), ("sh.L", "ua.L"), ("ua.L", "el.L"), ("el.L", "fa.L"), ("fa.L", "wr.L"), ("wr.L", "hd.L"),
         ("chest", "sh.R"), ("sh.R", "ua.R"), ("ua.R", "el.R"), ("el.R", "fa.R"), ("fa.R", "wr.R"), ("wr.R", "hd.R"),
         ("pelvis", "hip.L"), ("hip.L", "th.L"), ("th.L", "kn.L"), ("kn.L", "cf.L"), ("cf.L", "an.L"), ("an.L", "to.L"),
         ("pelvis", "hip.R"), ("hip.R", "th.R"), ("th.R", "kn.R"), ("kn.R", "cf.R"), ("cf.R", "an.R"), ("an.R", "to.R")]

names = list(J.keys())
me = bpy.data.meshes.new("PlayerSkin")
me.from_pydata([J[n] for n in names], [(names.index(a), names.index(b)) for a, b in EDGES], [])
body = bpy.data.objects.new("Player", me)
scene.collection.objects.link(body)
bpy.context.view_layer.objects.active = body
body.select_set(True)
sk = body.modifiers.new("Skin", "SKIN")
sk.use_smooth_shade = True
for i, n in enumerate(names):
    sv = me.skin_vertices[0].data[i]
    sv.radius = RAD[n]
    sv.use_root = (n == "pelvis")
sub = body.modifiers.new("Sub", "SUBSURF"); sub.levels = 2; sub.render_levels = 2
bpy.ops.object.modifier_apply(modifier="Skin")
bpy.ops.object.modifier_apply(modifier="Sub")
bpy.ops.object.shade_smooth()
print("player verts", len(me.vertices), "faces", len(me.polygons))

# ------------------------------------------------------------------ kit material slots by region
def mk(name, col, rough=0.6):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*col, 1); b.inputs["Roughness"].default_value = rough
    return m
mats = {"Skin": mk("Skin", (0.72, 0.5, 0.38), 0.55), "Hair": mk("Hair", (0.06, 0.045, 0.035), 0.7),
        "Shirt": mk("Shirt", (0.75, 0.05, 0.08), 0.62), "Shorts": mk("Shorts", (0.95, 0.95, 0.95), 0.6),
        "Socks": mk("Socks", (0.08, 0.08, 0.09), 0.7), "Boots": mk("Boots", (0.1, 0.1, 0.1), 0.35)}
order = ["Skin", "Hair", "Shirt", "Shorts", "Socks", "Boots"]
for k in order:
    me.materials.append(mats[k])

def region(c):
    x, y, z = c
    ax = abs(x)
    if z < 0.135: return "Boots"
    if z < 0.47: return "Socks"
    if z < 0.6: return "Skin"
    if z < 0.99 and ax < 0.21: return "Shorts"
    if z >= 1.70 or (z > 1.6 and y > 0.0): return "Hair"
    if z >= 1.5 and ax < 0.09: return "Skin"
    if ax > 0.205 and z < 1.32: return "Skin"     # forearms + hands (short sleeves)
    if z >= 0.99 or ax >= 0.17: return "Shirt"
    return "Shorts"
for p in me.polygons:
    p.material_index = order.index(region(p.center))

# ------------------------------------------------------------------ armature
arm_d = bpy.data.armatures.new("Rig")
rig = bpy.data.objects.new("Rig", arm_d)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_d.edit_bones
BONES = [  # name, head, tail, parent
    ("hips", "pelvis", "spine", None), ("spine", "spine", "chest", "hips"), ("chest", "chest", "neck", "spine"),
    ("neck", "neck", "head", "chest"), ("head", "head", "top", "neck"),
    ("upper_arm.L", "sh.L", "el.L", "chest"), ("forearm.L", "el.L", "wr.L", "upper_arm.L"), ("hand.L", "wr.L", "hd.L", "forearm.L"),
    ("upper_arm.R", "sh.R", "el.R", "chest"), ("forearm.R", "el.R", "wr.R", "upper_arm.R"), ("hand.R", "wr.R", "hd.R", "forearm.R"),
    ("thigh.L", "hip.L", "kn.L", "hips"), ("shin.L", "kn.L", "an.L", "thigh.L"), ("foot.L", "an.L", "to.L", "shin.L"),
    ("thigh.R", "hip.R", "kn.R", "hips"), ("shin.R", "kn.R", "an.R", "thigh.R"), ("foot.R", "an.R", "to.R", "shin.R"),
]
for n, h, t, par in BONES:
    b = eb.new(n); b.head = Vector(J[h]); b.tail = Vector(J[t])
    # align roll so local X is world X (side axis) for every bone
    b.align_roll(Vector((0, -1, 0)) if abs((b.tail - b.head).normalized().z) > 0.7 else Vector((0, 0, 1)))
    if par:
        b.parent = eb[par]
        b.use_connect = (n not in ("upper_arm.L", "upper_arm.R", "thigh.L", "thigh.R"))
bpy.ops.object.mode_set(mode="OBJECT")

# skin to rig with automatic (heat) weights
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
print("vertex groups", len(body.vertex_groups))

# ------------------------------------------------------------------ animation helpers
pb = rig.pose.bones
for b in pb:
    b.rotation_mode = "XYZ"
D = math.radians


def side_sign(bone):
    """Sign so that a positive angle means 'swing forward' for limbs pointing down."""
    return -1.0


LIMBS = {"thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R", "upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R", "hand.L", "hand.R"}


def key_pose(frame, pose, hip_z=0.0, hip_y=0.0):
    """Convention: positive X = forward swing for limbs, forward lean for the spine; knees/elbows given as
    the anatomical bend (positive) and converted here."""
    for b in pb:
        rx, ry, rz = pose.get(b.name, (0, 0, 0))
        if b.name in LIMBS:
            rx = -rx
        b.rotation_euler = (D(rx), D(ry), D(rz))
        b.keyframe_insert("rotation_euler", frame=frame)
    pb["hips"].location = (0, hip_y, hip_z)   # local: y = along bone (up), z = forward/back
    pb["hips"].keyframe_insert("location", frame=frame)


def new_action(name):
    act = bpy.data.actions.new(name); act.use_fake_user = True
    rig.animation_data_create(); rig.animation_data.action = act
    return act


def push(act, cyclic=True):
    tr = rig.animation_data.nla_tracks.new(); tr.name = act.name
    st = tr.strips.new(act.name, int(act.frame_range[0]), act)
    rig.animation_data.action = None
    try:
        for fc in act.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
            if cyclic:
                fc.modifiers.new("CYCLES")
    except Exception:
        pass


def run_pose(phase, amp_leg, amp_knee, amp_arm, elbow, lean):
    """phase in [0,1): right leg forward at 0."""
    s = math.sin(2 * math.pi * phase); c = math.cos(2 * math.pi * phase)
    s2 = math.sin(2 * math.pi * (phase + 0.5))
    kneeR = amp_knee * max(0.0, math.sin(2 * math.pi * (phase - 0.15))) ** 1.2 + 8
    kneeL = amp_knee * max(0.0, math.sin(2 * math.pi * (phase + 0.35))) ** 1.2 + 8
    return {
        "thigh.R": (-amp_leg * s, 0, 0), "thigh.L": (-amp_leg * s2, 0, 0),
        "shin.R": (kneeR, 0, 0), "shin.L": (kneeL, 0, 0),
        "foot.R": (-10 * c, 0, 0), "foot.L": (10 * c, 0, 0),
        "upper_arm.R": (amp_arm * s, 0, -8), "upper_arm.L": (amp_arm * s2, 0, 8),
        "forearm.R": (-elbow, 0, 0), "forearm.L": (-elbow, 0, 0),
        "spine": (lean * 0.6, 0, 4 * s), "chest": (lean * 0.4, 0, -6 * s), "neck": (-lean * 0.7, 0, 0), "head": (-lean * 0.3, 0, -2 * s),
        "hips": (0, -6 * s, 0),
    }


def cycle(name, frames, amp_leg, amp_knee, amp_arm, elbow, lean, bob):
    act = new_action(name)
    for f in range(frames + 1):
        ph = f / frames
        key_pose(f, run_pose(ph, amp_leg, amp_knee, amp_arm, elbow, lean), hip_y=-bob * abs(math.cos(2 * math.pi * ph)) + bob * 0.5)
    push(act)


# Idle: weight shift and breathing (2 s)
act = new_action("Idle")
for f in range(0, 61, 6):
    t = f / 60.0; s = math.sin(2 * math.pi * t)
    key_pose(f, {"spine": (2 + 1.2 * s, 0, 0), "chest": (1.5 * s, 0, 0), "upper_arm.L": (3, 0, 10 + 2 * s), "upper_arm.R": (3, 0, -10 - 2 * s),
                 "forearm.L": (-12, 0, 0), "forearm.R": (-12, 0, 0), "thigh.L": (-3, 0, 3), "thigh.R": (2, 0, -3), "shin.L": (6, 0, 0), "shin.R": (4, 0, 0),
                 "hips": (0, 3 * s, 0), "head": (0, 6 * s, 0)}, hip_y=-0.01 + 0.005 * s)
push(act)
cycle("Jog", 20, 34, 70, 30, 75, 9, 0.035)       # ~0.67 s per stride pair, ~4 m/s
cycle("Sprint", 15, 55, 105, 55, 90, 16, 0.05)   # 0.5 s, ~7.5 m/s

# Kick (right foot), 0.8 s one-shot
act = new_action("Kick")
keys = [
    (0, {"thigh.R": (-5, 0, 0), "upper_arm.L": (0, 0, 15), "upper_arm.R": (0, 0, -15)}),
    (8, {"thigh.R": (40, 0, 0), "shin.R": (95, 0, 0), "thigh.L": (-8, 0, 0), "shin.L": (20, 0, 0), "spine": (-6, 0, 10), "upper_arm.L": (-20, 0, 55), "upper_arm.R": (20, 0, -40), "forearm.L": (-30, 0, 0)}),
    (13, {"thigh.R": (-60, 0, 0), "shin.R": (10, 0, 0), "foot.R": (25, 0, 0), "thigh.L": (-5, 0, 0), "shin.L": (25, 0, 0), "spine": (10, 0, -8), "upper_arm.L": (20, 0, 60), "upper_arm.R": (-30, 0, -50), "forearm.L": (-30, 0, 0)}),
    (18, {"thigh.R": (-70, 0, 0), "shin.R": (20, 0, 0), "foot.R": (10, 0, 0), "spine": (8, 0, -5), "upper_arm.L": (10, 0, 45), "upper_arm.R": (-20, 0, -40)}),
    (24, {"thigh.R": (-10, 0, 0), "shin.R": (15, 0, 0), "upper_arm.L": (0, 0, 15), "upper_arm.R": (0, 0, -15)}),
]
for f, pose in keys:
    key_pose(f, pose, hip_y=-0.04 if f in (8, 13) else 0.0)
push(act, cyclic=False)

# Celebrate: arms up, jumping (1.2 s)
act = new_action("Celebrate")
for f in range(0, 37, 3):
    t = f / 36.0; s = math.sin(2 * math.pi * t * 2)
    key_pose(f, {"upper_arm.L": (-150 + 10 * s, 0, 30), "upper_arm.R": (-150 - 10 * s, 0, -30), "forearm.L": (-20, 0, 0), "forearm.R": (-20, 0, 0),
                 "thigh.L": (-20 * max(0, s), 0, 4), "thigh.R": (-20 * max(0, s), 0, -4), "shin.L": (40 * max(0, s), 0, 0), "shin.R": (40 * max(0, s), 0, 0),
                 "spine": (-8, 0, 0), "head": (-15, 0, 0)}, hip_y=0.18 * max(0, s))
push(act)

# Goalkeeper ready stance with small bounce (1 s)
act = new_action("KeeperReady")
for f in range(0, 31, 5):
    t = f / 30.0; s = math.sin(2 * math.pi * t * 2)
    key_pose(f, {"thigh.L": (-35, 0, 12), "thigh.R": (-35, 0, -12), "shin.L": (60, 0, 0), "shin.R": (60, 0, 0), "foot.L": (-20, 0, 0), "foot.R": (-20, 0, 0),
                 "spine": (22, 0, 0), "chest": (8, 0, 0), "neck": (-20, 0, 0), "head": (-10, 0, 0),
                 "upper_arm.L": (-45, 0, 35), "upper_arm.R": (-45, 0, -35), "forearm.L": (-35, 0, 0), "forearm.R": (-35, 0, 0)}, hip_y=-0.16 + 0.02 * s)
push(act)

scene.frame_start, scene.frame_end = 0, 60
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/player.blend")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=f"{OUT}/player.glb", export_format="GLB", use_selection=True, export_animations=True,
                          export_animation_mode="NLA_TRACKS", export_image_format="NONE", export_yup=True, export_skins=True)
print("exported")
