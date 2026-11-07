"""Fit per-frame R6 poses + placement to the reference silhouettes.
usage: python3 fit.py walk|run track|refine N"""
import sys, time, json
import numpy as np
from multiprocessing import Pool
from scipy.optimize import minimize
from scipy import ndimage as ndi
from common import *

CH = sys.argv[1]
PERIOD = {"walk": 30, "run": 20}[CH]
roi = ROI[CH]; x0, y0, x1, y1 = roi
fr = np.load(f"{S}/data/frames.npy").astype(float)
labs = np.load(f"{S}/data/labels.npy")[:, y0:y1, x0:x1]
uniq = np.load(f"{S}/data/uniq.npy")
# The gameplay was captured at a uniform 12 fps (one capture per 2.5 video frames); TikTok's 30 fps
# conversion duplicates frames unevenly, so first-appearance indices are NOT the capture times.
# Unique frame j was captured at 2.5*j video frames -> walk: 12 distinct phases (each seen twice),
# run: 8 distinct phases (each seen three times). Verified: frames j and j+12 (walk) / j+8 (run) match.
phase = ((2.5 * np.arange(len(uniq))) % PERIOD) / PERIOD
crop = fr[:, y0:y1, x0:x1]
br = crop.mean(-1); ratio = (crop[..., 2] - crop[..., 0]) / np.maximum(br, 1)
refW = labs == 2
refT = labs == 1
BGS = np.load(f"{S}/data/bgsure.npy")[:, y0:y1, x0:x1]
if CH == "run":  # static ground-tile highlights below/right of the runner's feet
    yy, xx = np.mgrid[y0:y1, x0:x1]; junk = (yy > 245) & (xx > 398)
    refW = refW & ~junk[None]; refT = refT & ~junk[None]; BGS = BGS | junk[None]
    walker_arm = xx < 290  # the walker's outstretched arm reaches into this crop
    refW = refW & ~walker_arm[None]; refT = refT & ~walker_arm[None]; BGS = BGS | walker_arm[None]
FACE = np.load(f"{S}/data/face.npy")[:, y0:y1, x0:x1]
if CH == "run":
    FACE = FACE & ~walker_arm[None]
refW = refW | FACE
UNK = ~BGS & ~refW & ~refT
DT = np.stack([np.minimum(ndi.distance_transform_edt(b), 10) for b in BGS])  # distance into certain-bg
REN = Renderer(roi)
NF = len(uniq)

B = {"ty": (-.6, .6), "tx": (-.5, .5), "tz": (-.6, .6), "t_lean": (-.4, 1.3), "t_yaw": (-.7, .7), "t_roll": (-.4, .4),
     "h_pitch": (-.5, .6), "h_yaw": (-.8, .8), "h_roll": (-.4, .4)}
for s in ("ra", "la"): B.update({f"{s}_pitch": (-2.6, 2.8), f"{s}_out": (-.35, 1.7), f"{s}_twist": (-.6, .6)})
for s in ("rl", "ll"): B.update({f"{s}_pitch": (-1.7, 2.0), f"{s}_out": (-.25, .7), f"{s}_twist": (-.5, .5)})
BOUNDS = [B[n] for n in NAMES]
LO = np.array([b[0] for b in BOUNDS]); HI = np.array([b[1] for b in BOUNDS])
REG = np.zeros(NP)
for n, w in (("t_roll", 100), ("h_roll", 150), ("h_yaw", 60), ("h_pitch", 40), ("ra_twist", 200), ("la_twist", 200),
             ("rl_twist", 200), ("ll_twist", 200), ("tx", 100), ("tz", 100)):
    REG[NAMES.index(n)] = w

def loss_img(lab, k):
    mF = lab == 3; mW = (lab == 2) | mF; mT = lab == 1; mA = lab > 0
    onbg = mA & BGS[k]
    return (3.0 * ((FACE[k] & ~mF).sum() + (mF & ~FACE[k]).sum()) + onbg.sum() + 0.15 * DT[k][onbg].sum() + 0.3 * (mA & UNK[k]).sum() + (refW[k] & ~mW).sum()
            + (mW & refT[k]).sum() + 0.5 * (refT[k] & ~mT).sum())

PRIOR_W = np.array([4, 4, 4, 1, 1, 1, 0.5, 0.5, 0.5] + [0.2, 0.2, 1.0] * 4) * 60

def frame_obj(p, k, place, h, prior=None, pw=0.0):
    lab, _, _ = REN.render(part_frames(p, place, face=True), cam_matrix(h))
    l = loss_img(lab, k) + np.sum(REG * p ** 2)
    if prior is not None and pw > 0:
        l += pw * np.sum(PRIOR_W * (p - prior) ** 2)
    return l

def opt(args):
    k, s, place, h, prior, pw, fev = args
    s = np.clip(s, LO + 1e-6, HI - 1e-6)
    r = minimize(frame_obj, s, args=(k, place, h, prior, pw), method="Powell", bounds=BOUNDS,
                 options={"maxfev": fev, "xtol": 1e-3, "ftol": 1e-5})
    return r.x, r.fun

def fourier_mat(ph, H):
    cols = [np.ones_like(ph)]
    for n in range(1, H + 1):
        cols += [np.cos(2*np.pi*n*ph), np.sin(2*np.pi*n*ph)]
    return np.stack(cols, 1)

def fourier_fit(P, ph, H=3):
    coef, *_ = np.linalg.lstsq(fourier_mat(ph, H), P, rcond=None); return coef

def fourier_eval(coef, ph):
    return fourier_mat(np.atleast_1d(ph), (len(coef) - 1) // 2) @ coef

def place_obj(q, P):
    h, px, pz, yaw = q
    return sum(loss_img(REN.render(part_frames(P[k], (px, pz, yaw), face=True), cam_matrix(h))[0], k) for k in range(NF))

def save(P, place, L):
    json.dump({"P": P.tolist(), "place": list(place), "phase": phase.tolist(), "uniq": uniq.tolist(),
               "loss": list(map(float, L))}, open(f"{S}/data/fit_{CH}.json", "w"))

def load():
    st = json.load(open(f"{S}/data/fit_{CH}.json")); return np.array(st["P"]), st["place"], st.get("loss")

if __name__ == "__main__":
    mode = sys.argv[2]; N = int(sys.argv[3])
    pool = Pool(4)
    FIX = "--fix-place" in sys.argv
    if mode == "track" and "--place" in sys.argv:
        i = sys.argv.index("--place"); d, yawd = float(sys.argv[i+1]), float(sys.argv[i+2])
        U, V = {"walk": (212, 165), "run": (365, 160)}[CH]
        h, px, pz = place_from_pixel(U, V, d); yaw = np.radians(yawd)
        P0, _, _ = load(); order = np.argsort(phase); P = P0.copy(); L = np.zeros(NF)
        p0 = None
    elif mode == "track":
        if CH == "walk":
            h, px, pz = place_from_pixel(212, 165, 7.2); yaw = np.pi
            p0 = np.zeros(NP)
        else:
            h, px, pz = place_from_pixel(365, 160, 7.6); yaw = np.pi - 0.5
            p0 = np.zeros(NP); p0[3] = 0.6
        order = np.argsort(phase)
        P = np.tile(p0, (NF, 1)); L = np.zeros(NF)
    if mode == "track":
        for sweep in range(N):
            t0 = time.time(); prev = None; prevprev = None
            seq = list(order) + list(order[:3])  # wrap a little so the start frame gets context too
            for k in seq:
                base = P[k] if (prev is None) else prev
                starts = [base, P[k]]
                if prevprev is not None: starts.append(np.clip(2 * prev - prevprev, LO, HI))
                for idx in (9, 12, 15, 18):
                    q = base.copy(); q[idx] = -q[idx] if abs(q[idx]) > 0.15 else q[idx] + 0.8; starts.append(q)
                    q = base.copy(); q[idx] = q[idx] - 0.8; starts.append(q)
                res = pool.map(opt, [(k, s, (px, pz, yaw), h, None, 0, 1500) for s in starts])
                best = min(res, key=lambda r: r[1])
                xb, fb = opt((k, best[0], (px, pz, yaw), h, None, 0, 3000))
                prevprev, prev = prev, xb
                P[k] = xb; L[k] = fb
            if not FIX:
                r = minimize(place_obj, [h, px, pz, yaw], args=(P,), method="Powell",
                             bounds=[(3, 9), (px - 2, px + 2), (pz - 3, pz + 3), (yaw - 1, yaw + 1)], options={"maxfev": 400, "xtol": 1e-3})
                h, px, pz, yaw = r.x
            save(P, (h, px, pz, yaw), L)
            print(f"track sweep {sweep}: loss/frame {L.mean():.0f} (max {L.max():.0f}) place h={h:.2f} px={px:.2f} pz={pz:.2f} yaw={np.degrees(yaw):.1f} ({time.time()-t0:.0f}s)", flush=True)
    else:
        P, (h, px, pz, yaw), L = load()
        for rnd in range(N):
            t0 = time.time()
            prior = fourier_eval(fourier_fit(P, phase, 3), phase)
            starts = [(k, 0.5 * (P[k] + prior[k]), (px, pz, yaw), h, prior[k], 1.0, 3000) for k in range(NF)]
            res = pool.map(opt, starts)
            P = np.array([r[0] for r in res]); L = np.array([r[1] for r in res])
            r = minimize(place_obj, [h, px, pz, yaw], args=(P,), method="Powell",
                         bounds=[(3, 9), (px - 1, px + 1), (pz - 2, pz + 2), (yaw - .5, yaw + .5)], options={"maxfev": 300, "xtol": 1e-3})
            h, px, pz, yaw = r.x
            save(P, (h, px, pz, yaw), L)
            print(f"refine {rnd}: loss/frame {L.mean():.0f} (max {L.max():.0f}) place h={h:.2f} px={px:.2f} pz={pz:.2f} yaw={np.degrees(yaw):.1f} ({time.time()-t0:.0f}s)", flush=True)
