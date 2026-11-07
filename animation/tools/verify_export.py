"""Check that the exported KeyframeSequences reproduce the original animations exactly.
usage: python3 animation/tools/verify_export.py"""
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import rbxm  # noqa: E402

TAGS = ["X", "Y", "Z", "R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22"]


def read_rbxmx(path):
    ks = ET.parse(path).getroot().find("Item")
    out = []
    for kf in ks.findall("Item[@class='Keyframe']"):
        t = float(kf.find("Properties/float[@name='Time']").text)
        poses = {}
        for p in kf.iter("Item"):
            if p.get("class") != "Pose":
                continue
            c = p.find("Properties/CoordinateFrame[@name='CFrame']")
            v = [float(c.find(tg).text) for tg in TAGS]
            m = np.eye(4); m[:3, :3] = np.array(v[3:]).reshape(3, 3); m[:3, 3] = v[:3]
            poses[p.find("Properties/string[@name='Name']").text] = m
        out.append((t, poses))
    props = {e.get("name"): e.text for e in ks.find("Properties")}
    return sorted(out, key=lambda k: k[0]), props


def read_rbxm(path):
    ks = next(d for d in rbxm.read(path)[0].descendants() if d.ClassName == "KeyframeSequence")
    out = [(kf.props["Time"], {p.Name: p.props["CFrame"] for p in kf.descendants() if p.ClassName == "Pose"})
           for kf in ks.children if kf.ClassName == "Keyframe"]
    return sorted(out, key=lambda k: k[0])


import json


def ang(R):
    return np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))


def max_step(frames):
    """largest per-frame rotation of any part (degrees) and number of frames where nothing moves"""
    worst, frozen = 0.0, 0
    for i in range(len(frames) - 1):
        a, b = frames[i][1], frames[i + 1][1]
        steps = [ang(a[p][:3, :3].T @ b[p][:3, :3]) for p in a]
        worst = max(worst, max(steps)); frozen += max(steps) < 0.01
    return worst, frozen


ok = True
for name, src in (("R6_Walk", "Rig animation walk.rbxm"), ("R6_Run", "Rig animation run.rbxm")):
    spec = json.load(open(os.path.join(ROOT, "animation", "data", f"{name}.json")))
    step = spec.get("key_step", 1)
    orig = read_rbxm(os.path.join(ROOT, "animation", "source", "rbxm", src))
    exp, props = read_rbxmx(os.path.join(ROOT, "animation", "output", f"{name}.rbxmx"))
    n = len(orig)
    length = n / 60
    rot = pos = 0.0
    checked = 0
    for t, P in exp:
        f = int(round(t * 60))
        if f % step:
            continue                       # in smooth mode only the authored key poses must match
        checked += 1
        for part, m in orig[f % n][1].items():
            rot = max(rot, np.abs(P[part][:3, :3] - m[:3, :3]).max())
            pos = max(pos, np.abs(P[part][:3, 3] - m[:3, 3]).max())
    good = rot < 1e-4 and pos < 1e-4 and abs(exp[-1][0] - length) < 1e-6 and len(exp) == n + 1
    ok &= good
    o_step, o_frozen = max_step(orig + [orig[0]])
    e_step, e_frozen = max_step(exp)
    mode = "smooth" if spec.get("smoothed") else "stepped (exact)"
    print(f"{name} [{mode}]: {len(exp)} keyframes, length {exp[-1][0]:.4f} s, Loop={props['Loop']}, Priority={props['Priority']}")
    print(f"   authored key poses matched: {checked} frames, max rotation diff {rot:.1e}, max position diff {pos:.1e} -> {'OK' if good else 'MISMATCH'}")
    print(f"   biggest single-frame joint jump: original {o_step:.1f} deg, exported {e_step:.1f} deg | "
          f"frames with no motion: original {o_frozen}/{n}, exported {e_frozen}/{n}")
sys.exit(0 if ok else 1)
