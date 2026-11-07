"""Build the R6 locomotion rig + animations in Blender and export them for Roblox.

Run with Blender (4.4+ / 5.x):
    blender -b -P animation/blender/build_r6_locomotion.py -- [--out DIR] [--data DIR] [--preview [--engine E]]
After hand-editing the keys in the saved .blend, re-export without rebuilding:
    blender animation/output/R6_Locomotion.blend -b -P animation/blender/build_r6_locomotion.py -- --export-only
or with the bpy module (pip install bpy):
    python3 animation/blender/build_r6_locomotion.py [--out DIR] [--data DIR] [--preview]

Inputs : animation/data/R6_Walk.json, animation/data/R6_Run.json  (keyframed curves)
Outputs: R6_Locomotion.blend            rig + both actions (edit these in Blender)
         R6_Walk.fbx / R6_Run.fbx       skinned R6 + baked action (interchange)
         R6_Walk.rbxmx / R6_Run.rbxmx   Roblox KeyframeSequence (import into Studio)
         preview/<anim>/####.png        (--preview) renders from the reference camera

Coordinate conventions
----------------------
Roblox is Y-up, character faces -Z. Blender is Z-up. We map Roblox -> Blender with the
proper rotation C = [[-1,0,0],[0,0,1],[0,1,0]], so the character faces -Y in Blender
(the Front view shows the face) and the character's right side is Blender -X.

Every bone rests pointing up with its local axes equal to the character's Roblox axes
(X = character right, Y = up, Z = back). Bone heads sit exactly on the R6 Motor6D
pivots. A pose-bone rotation is therefore literally the rotation of that part about its
Roblox joint pivot, expressed in its parent's frame:
    Torso / Head  Euler ZXY : X = -lean (pitch), Y = yaw, Z = roll
    Arms / Legs   Euler YZX : X = swing (+ forward), Z = abduction (+out on right,
                              -out on left), Y = twist
For export each sample is converted to a Motor6D Transform:
    T = R0^T * Tr(o) * R * R0      (R0 = rotation of the joint's C0)
which is exactly what a KeyframeSequence Pose.CFrame stores.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
OUT = os.path.join(ROOT, "animation", "output")
if "--out" in argv:
    OUT = os.path.abspath(argv[argv.index("--out") + 1])
PREVIEW = "--preview" in argv
ENGINE = argv[argv.index("--engine") + 1] if "--engine" in argv else "CYCLES"
DATA = os.path.join(ROOT, "animation", "data")
if "--data" in argv:
    DATA = os.path.abspath(argv[argv.index("--data") + 1])

# Roblox -> Blender basis (proper rotation, det +1, its own inverse).
C3 = Matrix(((-1, 0, 0), (0, 0, 1), (0, 1, 0)))
C4 = C3.to_4x4()


def rb2bl(v):
    return C3 @ Vector(v)


# ---------------------------------------------------------------------------------
# R6 definition (Roblox units, character space: HumanoidRootPart at (0, 3, 0)).
# ---------------------------------------------------------------------------------
HRP_Y = 3.0
# bone name -> (parent, pivot in Roblox character space, Euler order)
BONES = {
    "HumanoidRootPart": (None, (0, HRP_Y, 0), "XYZ"),
    "Torso": ("HumanoidRootPart", (0, HRP_Y, 0), "ZXY"),
    "Head": ("Torso", (0, HRP_Y + 1, 0), "ZXY"),
    "Right Arm": ("Torso", (1, HRP_Y + 0.5, 0), "YZX"),
    "Left Arm": ("Torso", (-1, HRP_Y + 0.5, 0), "YZX"),
    "Right Leg": ("Torso", (1, HRP_Y - 1, 0), "YZX"),
    "Left Leg": ("Torso", (-1, HRP_Y - 1, 0), "YZX"),
}
# part name -> (size, center in Roblox character space)
PARTS = {
    "Torso": ((2, 2, 1), (0, HRP_Y, 0)),
    "Head": ((1.2, 1.2, 1.2), (0, HRP_Y + 1.5, 0)),
    "Right Arm": ((1, 2, 1), (1.5, HRP_Y, 0)),
    "Left Arm": ((1, 2, 1), (-1.5, HRP_Y, 0)),
    "Right Leg": ((1, 2, 1), (0.5, HRP_Y - 2, 0)),
    "Left Leg": ((1, 2, 1), (-0.5, HRP_Y - 2, 0)),
}
# Motor6D C0 rotations (Roblox), keyed by Part1 name.
_RJ = Matrix(((-1, 0, 0), (0, 0, 1), (0, 1, 0)))
_RS = Matrix(((0, 0, 1), (0, 1, 0), (-1, 0, 0)))
_LS = Matrix(((0, 0, -1), (0, 1, 0), (1, 0, 0)))
C0_ROT = {"Torso": _RJ, "Head": _RJ, "Right Arm": _RS, "Right Leg": _RS, "Left Arm": _LS, "Left Leg": _LS}


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_material(name, rgb):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Roughness"].default_value = 0.6
    return m


def build_rig():
    scene = bpy.context.scene
    arm = bpy.data.armatures.new("R6")
    rig = bpy.data.objects.new("R6Rig", arm)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (parent, pivot, _) in BONES.items():
        eb = arm.edit_bones.new(name)
        eb.head = rb2bl(pivot)
        eb.tail = eb.head + Vector((0, 0, 0.6 if name != "HumanoidRootPart" else 1.0))
        eb.align_roll(Vector((0, 1, 0)))  # local Z -> Blender +Y (= Roblox +Z), local X -> Roblox +X
        if parent:
            eb.parent = arm.edit_bones[parent]
            eb.use_connect = False
        eb.use_deform = name != "HumanoidRootPart"
    bpy.ops.object.mode_set(mode="OBJECT")
    for name, (_, _, order) in BONES.items():
        rig.pose.bones[name].rotation_mode = order

    white = make_material("R6_White", (0.85, 0.87, 0.9))
    grey = make_material("R6_Torso", (0.32, 0.32, 0.36))
    black = make_material("R6_Face", (0.02, 0.02, 0.02))
    for name, (size, center) in PARTS.items():
        if name == "Head":
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.6, depth=1.2)
        else:
            bpy.ops.mesh.primitive_cube_add(size=1)
        ob = bpy.context.active_object
        ob.name = name
        if name != "Head":
            ob.scale = (size[0], size[2], size[1])  # Roblox (x, y, z) -> Blender (x, z, y)
        ob.location = rb2bl(center)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bev = ob.modifiers.new("Bevel", "BEVEL")
        bev.width = 0.18 if name == "Head" else 0.04
        bev.segments = 4 if name == "Head" else 2
        ob.data.materials.append(grey if name == "Torso" else white)
        vg = ob.vertex_groups.new(name=name)
        vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
        ob.parent = rig
    # simple face (eyes + mouth) so orientation reads clearly in previews
    head_c = rb2bl(PARTS["Head"][1])
    for i, (dx, dz, sx, sz) in enumerate(((-0.13, 0.18, 0.07, 0.16), (0.13, 0.18, 0.07, 0.16), (0, -0.24, 0.42, 0.08))):
        bpy.ops.mesh.primitive_cube_add(size=1)
        f = bpy.context.active_object
        f.name = f"Face{i}"
        f.scale = (sx, 0.02, sz)
        f.location = head_c + Vector((dx, -0.6, dz))
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        f.data.materials.append(black)
        vg = f.vertex_groups.new(name="Head")
        vg.add(list(range(len(f.data.vertices))), 1.0, "REPLACE")
        mod = f.modifiers.new("Armature", "ARMATURE")
        mod.object = rig
        f.parent = rig
    return rig


def channelbag(action, rig):
    from bpy_extras import anim_utils
    return anim_utils.action_get_channelbag_for_slot(action, rig.animation_data.action_slot)


def build_action(rig, spec):
    """spec: {'name', 'frames', 'channels': {bone: {'rotation_euler'|'location': [[ [f, v, slope], ...] x3 ]}}}"""
    act = bpy.data.actions.new(spec["name"])
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    # create a slot by inserting one key, then write curves explicitly
    pb0 = rig.pose.bones["HumanoidRootPart"]
    pb0.keyframe_insert("location", frame=0, group="HumanoidRootPart")
    cb = channelbag(act, rig)
    n = spec["frames"]
    for bone, chans in spec["channels"].items():
        for prop, comps in chans.items():
            for idx, keys in enumerate(comps):
                path = f'pose.bones["{bone}"].{prop}'
                fc = cb.fcurves.ensure(path, index=idx, group_name=bone)
                fc.keyframe_points.clear()
                fc.keyframe_points.add(len(keys))
                for kp, (fr, val, slope) in zip(fc.keyframe_points, keys):
                    kp.co = (fr, val)
                    kp.interpolation = "BEZIER"
                for i, kp in enumerate(fc.keyframe_points):
                    fr, val, slope = keys[i]
                    dl = (fr - keys[i - 1][0]) if i > 0 else (keys[1][0] - keys[0][0])
                    dr = (keys[i + 1][0] - fr) if i + 1 < len(keys) else dl
                    kp.handle_left_type = "FREE"
                    kp.handle_right_type = "FREE"
                    kp.handle_left = (fr - dl / 3, val - slope * dl / 3)
                    kp.handle_right = (fr + dr / 3, val + slope * dr / 3)
                fc.modifiers.new("CYCLES")
                fc.update()
    # HumanoidRootPart stays at rest; keep its curves flat
    for fc in cb.fcurves:
        if fc.data_path.startswith('pose.bones["HumanoidRootPart"]'):
            for kp in fc.keyframe_points:
                kp.co.y = 0.0
    act.frame_range = (0, n)
    act.use_frame_range = True
    act.use_cyclic = True
    return act


# ---------------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------------
def joint_frames(rig):
    """Bone pose matrices in Roblox character space (origin on the pivot). Bone-local axes
    already equal the Roblox axes by construction, so only the world basis is converted."""
    C4inv = C4.inverted()
    return {pb.name: C4inv @ pb.matrix for pb in rig.pose.bones}


def joint_frames_rest(rig):
    C4inv = C4.inverted()
    return {b.name: C4inv @ b.matrix_local for b in rig.data.bones}


def motor_transforms(rig, rest):
    J = joint_frames(rig)
    out = {}
    for name, (parent, _, _) in BONES.items():
        if parent is None:
            continue
        rel = J[parent].inverted() @ J[name]
        rel_rest = rest[parent].inverted() @ rest[name]
        R = rel.to_3x3()
        o = rel.translation - rel_rest.translation
        R0 = C0_ROT[name]
        T = (R0.transposed() @ R @ R0).to_4x4()
        T.translation = R0.transposed() @ o
        out[name] = T
    return out


def cf_xml(m):
    r = m.to_3x3()
    vals = [m.translation.x, m.translation.y, m.translation.z] + [r[i][j] for i in range(3) for j in range(3)]
    tags = ["X", "Y", "Z", "R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22"]
    return "".join(f"<{t}>{0.0 if abs(v) < 1e-9 else round(v, 7)}</{t}>" for t, v in zip(tags, vals))


_ref = [0]


def _referent():
    _ref[0] += 1
    return f"RBX{_ref[0]:08X}"


def pose_xml(name, cf, children):
    kids = "".join(children)
    return (f'<Item class="Pose" referent="{_referent()}"><Properties>'
            f'<CoordinateFrame name="CFrame">{cf}</CoordinateFrame>'
            f'<token name="EasingDirection">0</token><token name="EasingStyle">0</token>'
            f'<string name="Name">{name}</string><float name="Weight">1</float>'
            f'</Properties>{kids}</Item>')


def export_rbxmx(rig, act, path, sample_hz=60):
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    rig.animation_data.action = act
    rest = joint_frames_rest(rig)
    n = int(round(act.frame_range[1] - act.frame_range[0]))
    length = n / fps
    steps = int(round(length * sample_hz))
    ident = cf_xml(Matrix.Identity(4))
    keyframes = []
    for s in range(steps + 1):
        t = s / sample_hz
        fr = act.frame_range[0] + t * fps
        scene.frame_set(int(math.floor(fr)), subframe=fr - math.floor(fr))
        bpy.context.view_layer.update()
        T = motor_transforms(rig, rest)
        limbs = [pose_xml(nm, cf_xml(T[nm]), []) for nm in ("Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")]
        torso = pose_xml("Torso", cf_xml(T["Torso"]), limbs)
        hrp = pose_xml("HumanoidRootPart", ident, [torso])
        keyframes.append(f'<Item class="Keyframe" referent="{_referent()}"><Properties>'
                         f'<string name="Name">Keyframe</string><float name="Time">{round(t, 6)}</float>'
                         f'</Properties>{hrp}</Item>')
    xml = ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">'
           f'<Item class="KeyframeSequence" referent="{_referent()}"><Properties>'
           f'<bool name="Loop">true</bool><string name="Name">{act.name}</string>'
           f'<token name="Priority">1</token>'  # Enum.AnimationPriority.Movement
           f'</Properties>{"".join(keyframes)}</Item></roblox>')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    return steps + 1, length


def export_fbx(rig, act, path):
    rig.animation_data.action = act
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = int(act.frame_range[0]), int(act.frame_range[1])
    bpy.ops.object.select_all(action="DESELECT")
    for ob in scene.objects:
        if ob.type in {"ARMATURE", "MESH"}:
            ob.select_set(True)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, add_leaf_bones=False, bake_anim=True,
                             bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                             bake_anim_force_startend_keying=True, bake_anim_step=1.0,
                             bake_anim_simplify_factor=0.0, apply_scale_options="FBX_SCALE_ALL",
                             object_types={"ARMATURE", "MESH"})


def setup_preview(rig, cam_spec):
    """cam_spec: {'height', 'pitch_deg', 'fov_deg', 'place': [px, pz, yaw]} in Roblox space."""
    scene = bpy.context.scene
    px, pz, yaw = cam_spec["place"]
    c, s = math.cos(yaw), math.sin(yaw)
    Ry = Matrix(((c, 0, s, 0), (0, 1, 0, 0), (-s, 0, c, 0), (0, 0, 0, 1)))
    place = Matrix.Translation((px, 0, pz)) @ Ry
    rig.matrix_world = C4 @ place @ C4.inverted()
    cam_data = bpy.data.cameras.get("RefCam") or bpy.data.cameras.new("RefCam")
    cam_data.sensor_fit = "VERTICAL"
    cam_data.angle_y = math.radians(cam_spec["fov_deg"])
    cam = bpy.data.objects.get("RefCam") or bpy.data.objects.new("RefCam", cam_data)
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)
    p = math.radians(cam_spec["pitch_deg"])
    Rx = Matrix(((1, 0, 0, 0), (0, math.cos(-p), -math.sin(-p), 0), (0, math.sin(-p), math.cos(-p), 0), (0, 0, 0, 1)))
    cam.matrix_world = C4 @ Matrix.Translation((0, cam_spec["height"], 0)) @ Rx
    scene.camera = cam
    if "Ground" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=200)
        g = bpy.context.active_object
        g.name = "Ground"
        g.data.materials.append(make_material("Ground", (0.35, 0.4, 0.5)))
    if "Sun" not in bpy.data.objects:
        sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        sun.data.energy = 3.0
        sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(30))
        scene.collection.objects.link(sun)
    scene.render.resolution_x, scene.render.resolution_y = 576, 324
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.color = (0.55, 0.7, 0.85)
    if bpy.app.version < (5, 0, 0):
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background") if world.node_tree else None
    if bg:
        bg.inputs["Color"].default_value = (0.45, 0.62, 0.85, 1)
        bg.inputs["Strength"].default_value = 0.8


def render_preview(rig, act, cam_spec, outdir):
    scene = bpy.context.scene
    rig.animation_data.action = act
    setup_preview(rig, cam_spec)
    # Cycles on CPU works everywhere (including headless servers without EGL/GPU);
    # pass --engine BLENDER_WORKBENCH or BLENDER_EEVEE on a desktop for faster previews.
    scene.render.engine = ENGINE
    if ENGINE == "CYCLES":
        scene.cycles.device = "CPU"
        scene.cycles.samples = 16
        scene.cycles.use_denoising = False
    os.makedirs(outdir, exist_ok=True)
    for f in range(int(act.frame_range[0]), int(act.frame_range[1])):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(outdir, f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    rig.matrix_world = Matrix.Identity(4)


def export_only():
    """Re-export from the currently open .blend (after hand-editing the keys in Blender)."""
    os.makedirs(OUT, exist_ok=True)
    rig = bpy.data.objects["R6Rig"]
    rig.matrix_world = Matrix.Identity(4)
    report = {}
    for name in ("R6_Walk", "R6_Run"):
        act = bpy.data.actions[name]
        n, length = export_rbxmx(rig, act, os.path.join(OUT, f"{name}.rbxmx"))
        export_fbx(rig, act, os.path.join(OUT, f"{name}.fbx"))
        report[name] = {"keyframes": n, "length_s": round(length, 4)}
    print("EXPORT_REPORT", json.dumps(report))


def main():
    if "--export-only" in argv:
        return export_only()
    os.makedirs(OUT, exist_ok=True)
    reset_scene()
    scene = bpy.context.scene
    scene.render.fps = 30
    rig = build_rig()
    specs = [json.load(open(os.path.join(DATA, f"{n}.json"))) for n in ("R6_Walk", "R6_Run")]
    actions = [build_action(rig, sp) for sp in specs]
    report = {}
    for sp, act in zip(specs, actions):
        n, length = export_rbxmx(rig, act, os.path.join(OUT, f"{act.name}.rbxmx"))
        export_fbx(rig, act, os.path.join(OUT, f"{act.name}.fbx"))
        report[act.name] = {"keyframes": n, "length_s": round(length, 4)}
        if PREVIEW and "reference_camera" in sp:
            render_preview(rig, act, sp["reference_camera"], os.path.join(OUT, "preview", act.name))
    rig.animation_data.action = actions[0]
    scene.frame_start, scene.frame_end = 0, specs[0]["frames"] - 1
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "R6_Locomotion.blend"))
    print("EXPORT_REPORT", json.dumps(report))


if __name__ == "__main__":
    main()
