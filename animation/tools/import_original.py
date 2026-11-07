"""Convert the original KeyframeSequences (.rbxm) into keyed curves for the Blender R6 rig.

usage: python3 animation/tools/import_original.py [--stepped]   (needs bpy: pip install bpy lz4)
       default: smooth (authored key poses, flowing Bezier interpolation)
       --stepped: exact original (hold each pose 5 frames, then snap)
Reads  animation/source/rbxm/Rig animation walk.rbxm, Rig animation run.rbxm
Writes animation/data/R6_Walk.json, R6_Run.json  (consumed by animation/blender/build_r6_locomotion.py)

Each Pose.CFrame is a Motor6D Transform T. The rotation of the part about its joint pivot,
expressed in the parent part's frame, is R = R0 T R0^T and the offset is o = R0 * T.position
(R0 = rotation of the joint's C0). The Blender rig's bone axes equal the R6 part axes, so R is
written straight into the bone's Euler channels (Torso/Head: ZXY, limbs: YZX).
The original keys are baked at 60 Hz with linear easing, so they are keyed the same way, and a
closing key equal to the first is added so the loop length equals the authored cycle
(walk 60 frames = 1.000 s, run 40 frames = 0.667 s)."""
import json
import os
import sys

import bpy  # noqa: F401  (makes mathutils importable when running outside Blender)
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import rbxm  # noqa: E402

R0 = {
    "Torso": Matrix(((-1, 0, 0), (0, 0, 1), (0, 1, 0))),
    "Head": Matrix(((-1, 0, 0), (0, 0, 1), (0, 1, 0))),
    "Right Arm": Matrix(((0, 0, 1), (0, 1, 0), (-1, 0, 0))),
    "Right Leg": Matrix(((0, 0, 1), (0, 1, 0), (-1, 0, 0))),
    "Left Arm": Matrix(((0, 0, -1), (0, 1, 0), (1, 0, 0))),
    "Left Leg": Matrix(((0, 0, -1), (0, 1, 0), (1, 0, 0))),
}
ORDER = {"Torso": "ZXY", "Head": "ZXY", "Right Arm": "YZX", "Left Arm": "YZX", "Right Leg": "YZX", "Left Leg": "YZX"}
KEY_STEP = 5  # the originals change pose every 5 frames (12 key poses per walk cycle, 8 per run cycle)
SOURCES = {"R6_Walk": "Rig animation walk.rbxm", "R6_Run": "Rig animation run.rbxm"}


def load_keyframes(path):
    model = rbxm.read(path)[0]
    ks = next(d for d in model.descendants() if d.ClassName == "KeyframeSequence")
    kfs = []
    for kf in ks.children:
        if kf.ClassName != "Keyframe":
            continue
        poses = {p.Name: p.props["CFrame"] for p in kf.descendants() if p.ClassName == "Pose"}
        kfs.append((kf.props["Time"], poses))
    kfs.sort(key=lambda k: k[0])
    return ks, kfs


def convert(name, src, smooth=True):
    ks, kfs = load_keyframes(src)
    fps = 60
    n = len(kfs)  # frames 0..n-1 at 60 Hz; frame n closes the loop
    times = [round(t * fps) for t, _ in kfs]
    assert times == list(range(n)), f"{name}: expected one keyframe per 60 Hz frame"
    channels = {}
    prev = {}
    # The originals are stepped: every part holds a pose for 5 frames and then snaps to the next
    # (Constant interpolation in the source .blend). In smooth mode only those authored key poses
    # are kept, at their original frames, and Blender interpolates between them with auto-clamped
    # Bezier curves (no overshoot), so the poses and timing stay the same but the motion flows.
    step = KEY_STEP if smooth else 1
    for frame, (_, poses) in enumerate(kfs + [kfs[0]]):
        if frame % step:
            continue
        for bone, r0 in R0.items():
            T = poses.get(bone)
            if T is None:
                continue
            Rt = Matrix([[float(T[i][j]) for j in range(3)] for i in range(3)])
            R = r0 @ Rt @ r0.transposed()
            o = r0 @ Vector([float(T[i][3]) for i in range(3)])
            e = R.to_euler(ORDER[bone], prev[bone]) if bone in prev else R.to_euler(ORDER[bone])
            prev[bone] = e
            ch = channels.setdefault(bone, {"rotation_euler": [[], [], []], "location": [[], [], []]})
            for i in range(3):
                ch["rotation_euler"][i].append([frame, e[i], 0.0])
                ch["location"][i].append([frame, o[i], 0.0])
    # drop location channels that never move (limbs/head normally have none)
    for bone, ch in channels.items():
        if all(abs(k[1]) < 1e-6 for comp in ch["location"] for k in comp):
            del ch["location"]
    return {
        "name": name, "fps": fps, "frames": n, "loop": True, "priority": "Movement",
        "interpolation": "BEZIER" if smooth else "LINEAR",
        "handles": "AUTO_CLAMPED" if smooth else "FREE",
        "smoothed": smooth, "key_step": step,
        "source": {"file": os.path.basename(src), "keyframe_sequence": ks.Name,
                   "original_priority": ks.props.get("Priority"), "keyframes": n,
                   "authored_length_s": n / fps},
        "channels": channels,
    }


if __name__ == "__main__":
    src_dir = os.path.join(ROOT, "animation", "source", "rbxm")
    out_dir = os.path.join(ROOT, "animation", "data")
    for name, fn in SOURCES.items():
        spec = convert(name, os.path.join(src_dir, fn), smooth="--stepped" not in sys.argv)
        json.dump(spec, open(os.path.join(out_dir, f"{name}.json"), "w"), indent=1)
        print(name, spec["source"])
