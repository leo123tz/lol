"""Fitted per-frame poses -> periodic curves -> Blender keyframe JSON.
usage: python3 make_curves.py walk|run OUTDIR [--sym]"""
import sys, json
import numpy as np
from common import *

CH, OUTDIR = sys.argv[1], sys.argv[2]
SYM = "--sym" in sys.argv
CFG = {"walk": dict(name="R6_Walk", frames=30, step=3, H=4),
       "run": dict(name="R6_Run", frames=20, step=2, H=4)}[CH]
import os
SYN = os.environ.get("SYNTH")
if SYN:  # test mode: synthetic poses on a dense phase grid
    rng = np.random.default_rng(1); ph = np.linspace(0, 1, 40, endpoint=False)
    P = np.stack([0.4 * rng.uniform(0.3, 1) * np.sin(2*np.pi*(ph + rng.uniform())) + (0.6 if i == 9 else 0) for i in range(NP)], 1)
    P[:, :3] *= 0.5; h, px, pz, yaw = 5.7, -2.4, -6.7, np.pi
else:
    st = json.load(open(os.environ.get("FITFILE", f"{S}/data/fit_{CH}.json")))
    P = np.array(st["P"]); ph = np.array(st["phase"]); h, px, pz, yaw = st["place"]

def mat(phv, H):
    phv = np.atleast_1d(phv); cols = [np.ones_like(phv)]; dcols = [np.zeros_like(phv)]
    for n in range(1, H + 1):
        w = 2 * np.pi * n
        cols += [np.cos(w * phv), np.sin(w * phv)]; dcols += [-w * np.sin(w * phv), w * np.cos(w * phv)]
    return np.stack(cols, 1), np.stack(dcols, 1)

def fit(P, ph, H, lam=float(os.environ.get("RIDGE", "0.002"))):
    A, _ = mat(ph, H)
    reg = np.diag([0] + [lam * n * n for n in range(1, H + 1) for _ in (0, 1)])
    return np.linalg.solve(A.T @ A + reg * len(ph), A.T @ P)

# mirror pairs for optional bilateral symmetry (right(t) == left(t + 1/2))
MIRROR = {}
for a, b in (("ra", "la"), ("rl", "ll")):
    for c in ("pitch", "out", "twist"):
        MIRROR[NAMES.index(f"{a}_{c}")] = NAMES.index(f"{b}_{c}")

if SYM:
    # augment the data with mirrored copies shifted by half a cycle
    Pm = P.copy()
    for i, j in MIRROR.items():
        Pm[:, i], Pm[:, j] = P[:, j], P[:, i]
    for n in ("tx", "t_yaw", "t_roll", "h_yaw", "h_roll"):
        Pm[:, NAMES.index(n)] *= -1
    P2 = np.concatenate([P, Pm]); ph2 = np.concatenate([ph, (ph + 0.5) % 1])
    coef = fit(P2, ph2, CFG["H"])
else:
    coef = fit(P, ph, CFG["H"])

KEYS = os.environ.get("KEYS")
if KEYS:
    kd = json.load(open(KEYS)); h, px, pz, yaw = kd["place"]
    curve = {"type": "spline", "K": kd["K"]}
    feval, cs = curve_eval_factory(curve)
    dfeval = lambda q: cs(np.atleast_1d(q) % 1.0, 1)
else:
    curve = {"type": "fourier", "coef": coef.tolist(), "H": CFG["H"]}
    feval, _ = curve_eval_factory(curve)
    dfeval = lambda q: mat(q, CFG["H"])[1] @ coef

# cycle start: right leg at its most-forward swing (same event for walk and run)
grid = np.linspace(0, 1, 2000, endpoint=False)
rl = feval(grid)[:, NAMES.index("rl_pitch")]
phi0 = grid[np.argmax(rl)]

N, step = CFG["frames"], CFG["step"]
frames = np.arange(0, N + 1, step)
V = feval((frames / N + phi0) % 1); D = dfeval((frames / N + phi0) % 1) / N  # per-frame slopes

def ch(i, sign=1.0):
    return [[int(f), float(sign * V[k, i]), float(sign * D[k, i])] for k, f in enumerate(frames)]

idx = {n: i for i, n in enumerate(NAMES)}
channels = {
    "Torso": {"location": [ch(idx["tx"]), ch(idx["ty"]), ch(idx["tz"])],
              "rotation_euler": [ch(idx["t_lean"], -1), ch(idx["t_yaw"]), ch(idx["t_roll"])]},
    "Head": {"rotation_euler": [ch(idx["h_pitch"], -1), ch(idx["h_yaw"]), ch(idx["h_roll"])]},
}
for bone, p, side in (("Right Arm", "ra", 1), ("Left Arm", "la", -1), ("Right Leg", "rl", 1), ("Left Leg", "ll", -1)):
    channels[bone] = {"rotation_euler": [ch(idx[f"{p}_pitch"]), ch(idx[f"{p}_twist"], -side), ch(idx[f"{p}_out"], side)]}

spec = {"name": CFG["name"], "fps": 30, "frames": N, "loop": True, "priority": "Movement",
        "source": {"video_cycle_s": N / 30, "phase_offset": float(phi0), "harmonics": CFG["H"],
                   "symmetric": SYM, "samples": len(ph)},
        "reference_camera": {"height": h, "pitch_deg": float(np.degrees(PITCH)), "fov_deg": 70.0, "place": [px, pz, yaw]},
        "channels": channels}
json.dump(spec, open(f"{OUTDIR}/{CFG['name']}.json", "w"), indent=1)
curve.update({"phi0": float(phi0)})
json.dump(curve, open(SYN or f"{S}/data/curve_{CH}.json", "w"))
# report fit residual of curve vs per-frame poses (degrees, radians->deg for angles)
res = P - feval(ph)
print(CH, "phi0", round(phi0, 3), "rms residual per channel:")
print({n: round(float(np.degrees(np.sqrt((res[:, i] ** 2).mean()))) if i > 2 else float(np.sqrt((res[:, i] ** 2).mean())), 2) for i, n in enumerate(NAMES)})
