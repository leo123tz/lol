"""Validate an exported KeyframeSequence (.rbxmx) against the fitted curves and the video.
usage: python3 validate.py walk|run path/to/R6_X.rbxmx"""
import sys, json
import xml.etree.ElementTree as ET
import numpy as np
from common import *

CH, PATH = sys.argv[1], sys.argv[2]
import os
SYN = os.environ.get("SYNTH")
if SYN:
    h, px, pz, yaw = 5.7, -2.4, -6.7, np.pi; ph = None
else:
    st = json.load(open(os.environ.get("FITFILE", f"{S}/data/fit_{CH}.json"))); h, px, pz, yaw = st["place"]; ph = np.array(st["phase"])
cv = json.load(open(SYN or f"{S}/data/curve_{CH}.json")); phi0 = cv["phi0"]
_feval, _ = curve_eval_factory(cv)

def cf(vals):
    x, y, z, *r = vals; m = np.eye(4); m[:3, :3] = np.array(r).reshape(3, 3); m[:3, 3] = (x, y, z); return m

def CF(*v): return cf(v)
MOTORS = {  # Part1: (Part0, C0, C1)
    "Torso": ("HumanoidRootPart", CF(0,0,0,-1,0,0,0,0,1,0,1,0), CF(0,0,0,-1,0,0,0,0,1,0,1,0)),
    "Head": ("Torso", CF(0,1,0,-1,0,0,0,0,1,0,1,0), CF(0,-0.5,0,-1,0,0,0,0,1,0,1,0)),
    "Right Arm": ("Torso", CF(1,0.5,0,0,0,1,0,1,0,-1,0,0), CF(-0.5,0.5,0,0,0,1,0,1,0,-1,0,0)),
    "Left Arm": ("Torso", CF(-1,0.5,0,0,0,-1,0,1,0,1,0,0), CF(0.5,0.5,0,0,0,-1,0,1,0,1,0,0)),
    "Right Leg": ("Torso", CF(1,-1,0,0,0,1,0,1,0,-1,0,0), CF(0.5,1,0,0,0,1,0,1,0,-1,0,0)),
    "Left Leg": ("Torso", CF(-1,-1,0,0,0,-1,0,1,0,1,0,0), CF(-0.5,1,0,0,0,-1,0,1,0,1,0,0)),
}
TAGS = ["X","Y","Z","R00","R01","R02","R10","R11","R12","R20","R21","R22"]

root = ET.parse(PATH).getroot()
ks = root.find("Item")
assert ks.get("class") == "KeyframeSequence"
loop = ks.find("Properties/bool[@name='Loop']").text
prio = ks.find("Properties/token[@name='Priority']").text
kfs = []
for kf in ks.findall("Item[@class='Keyframe']"):
    t = float(kf.find("Properties/float[@name='Time']").text)
    poses = {}
    def walk(item):
        nm = item.find("Properties/string[@name='Name']").text
        c = item.find("Properties/CoordinateFrame[@name='CFrame']")
        poses[nm] = cf([float(c.find(tg).text) for tg in TAGS])
        for ch_ in item.findall("Item[@class='Pose']"): walk(ch_)
    for p in kf.findall("Item[@class='Pose']"): walk(p)
    kfs.append((t, poses))
kfs.sort(key=lambda x: x[0])
L = kfs[-1][0]
print(f"{PATH.rsplit('/',1)[-1]}: Loop={loop} Priority={prio} keyframes={len(kfs)} length={L:.4f}s")

def roblox_parts(T, place):
    pxx, pzz, yy = place
    parts = {"HumanoidRootPart": M(Ry(yy), (pxx, 3.0, pzz))}
    for p1 in ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        p0, C0, C1 = MOTORS[p1]
        parts[p1] = parts[p0] @ C0 @ T.get(p1, np.eye(4)) @ np.linalg.inv(C1)
    del parts["HumanoidRootPart"]; return parts

def fourier(phv):
    return _feval(phv)[0]

# 1) exact agreement between exported transforms and the fitted pose model
err = 0
corners = np.array([[sx, sy, sz, 1] for sx in (-.5, .5) for sy in (-.5, .5) for sz in (-.5, .5)])
for t, T in kfs:
    a = roblox_parts(T, (px, pz, yaw)); b = part_frames(fourier((t / L + phi0) % 1), (px, pz, yaw))
    for nm in a:
        S_ = np.diag(list(SIZES[nm]) + [1])
        err = max(err, np.abs((a[nm] @ S_ @ corners.T) - (b[nm] @ S_ @ corners.T)).max())
print(f"max corner deviation exported-vs-curve: {err:.2e} studs")
first, last = kfs[0][1], kfs[-1][1]
print("loop seam deviation:", max(np.abs(first[k] - last[k]).max() for k in first))

if SYN: sys.exit(0)
# 2) Roblox-style playback (linear between keyframes) vs the video samples
def sample(t):
    t = t % L
    for i in range(len(kfs) - 1):
        t0, P0 = kfs[i]; t1, P1 = kfs[i + 1]
        if t0 <= t <= t1:
            a = (t - t0) / (t1 - t0); out = {}
            for k in P0:  # small-step lerp is fine at 60 Hz (rotations orthonormalised)
                m = (1 - a) * P0[k] + a * P1[k]; u, _, vt = np.linalg.svd(m[:3, :3]); m[:3, :3] = u @ vt; out[k] = m
            return out
    return kfs[-1][1]

x0, y0, x1, y1 = ROI[CH]
labs = np.load(f"{S}/data/labels.npy")[:, y0:y1, x0:x1]
fr = np.load(f"{S}/data/frames.npy")
R = Renderer(ROI[CH]); view = cam_matrix(h)
ious = []; tiles = []
for k in np.argsort(ph):
    t = ((ph[k] - phi0) % 1) * L
    lab, _, _ = R.render(roblox_parts(sample(t), (px, pz, yaw)), view)
    a = lab == 2; b = labs[k] == 2
    ious.append((a & b).sum() / max((a | b).sum(), 1))
    tiles.append(np.array(overlay(fr[k], lab, ROI[CH], 1)))
ious = np.array(ious)
print(f"silhouette IoU (white parts) vs video: mean {ious.mean():.3f}  min {ious.min():.3f}  per-sample {np.round(ious, 2).tolist()}")
rows = [np.concatenate(tiles[i:i+8], 1) for i in range(0, len(tiles), 8)]
Image.fromarray(np.concatenate(rows, 0)).save(f"{S}/sheets/validate_{CH}.png")
