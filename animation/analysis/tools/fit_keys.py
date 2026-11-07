"""Key-pose fitting: one R6 pose per captured phase, with bilateral mirror symmetry.

The captures give n distinct phases per cycle (walk 12, run 8). The pose at phase i + n/2 is the
mirror image of the pose at phase i (left/right limbs swapped, lateral/yaw/roll channels negated),
so each of the n/2 "pose pairs" is fitted against all images at both of its phases.
Stage A: free facing-yaw per pair (multi-start)  -> global yaw = median.
Stage B: fixed yaw, multi-start + neighbour-smoothness prior (2 rounds).
usage: python3 fit_keys.py walk|run INIT_SYM_JSON [--tag NAME]"""
import sys, json, time
import numpy as np
from multiprocessing import Pool
from scipy.optimize import minimize
_argv = list(sys.argv)
CH = _argv[1]
sys.argv = [_argv[0], CH, "0"]
import fit_sym as FS
from fit_sym import *  # noqa
sys.argv = _argv
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
TAG = arg("--tag", "keys")
NOSYM = "--nosym" in sys.argv  # fit every phase independently (no mirror coupling): symmetry test
NPH = {"walk": 12, "run": 8}[CH]
NU = NPH if "--nosym" in sys.argv else NPH // 2
PH_IDX = np.rint(phase * NPH).astype(int) % NPH
GROUPS = [np.where(PH_IDX == i)[0] for i in range(NPH)]
P0, (h, px, pz, _), _ = load()
ODD_N = [NAMES.index(n) for n in ("tx", "t_yaw", "t_roll", "h_yaw", "h_roll")]
SWAP = [(NAMES.index(f"{a}_{c}"), NAMES.index(f"{b}_{c}")) for a, b in (("ra", "la"), ("rl", "ll")) for c in ("pitch", "out", "twist")]

def mirror(p):
    q = p.copy()
    for i, j in SWAP: q[i], q[j] = p[j], p[i]
    q[ODD_N] = -p[ODD_N]
    return q

def pair_loss(p, i, yaw):
    l = 0.0
    halves = ((0, p),) if NOSYM else ((0, p), (1, mirror(p)))
    for half, pp in halves:
        for k in GROUPS[(i + half * NPH // 2) % NPH]:
            lab, _, _ = REN.render(part_frames(np.clip(pp, LO, HI), (px, pz, yaw), face=True), cam_matrix(h))
            l += loss_img(lab, k)
    return l + np.sum(REG * p ** 2) * len(halves)

def obj(x, i, yaw_fixed, prior, pw):
    if yaw_fixed is None: p, yaw = x[:-1], x[-1]
    else: p, yaw = x, yaw_fixed
    l = pair_loss(p, i, yaw)
    if prior is not None: l += pw * np.sum(PRIOR_W * (p - prior) ** 2)
    return l

def solve(args):
    i, starts, yaw_fixed, prior, pw, fev = args
    best = None
    for s in starts:
        s = np.clip(s, LO + 1e-6, HI - 1e-6) if yaw_fixed is not None else np.append(np.clip(s[:-1], LO + 1e-6, HI - 1e-6), s[-1])
        b = BOUNDS if yaw_fixed is not None else BOUNDS + [(np.radians(150), np.radians(230))]
        r = minimize(obj, s, args=(i, yaw_fixed, prior, pw), method="Powell", bounds=b,
                     options={"maxfev": fev, "xtol": 1e-3, "ftol": 1e-5})
        if best is None or r.fun < best[1]: best = (r.x, r.fun)
    return best

def starts_for(p, rng, n_rand=3):
    st = [p.copy()]
    for idx in (9, 12, 15, 18):          # flip each limb's swing
        q = p.copy(); q[idx] = -q[idx] if abs(q[idx]) > 0.2 else q[idx] + 0.9; st.append(q)
    for _ in range(n_rand):              # random restarts around the start
        st.append(p + rng.normal(0, 1, NP) * np.array([.1] * 3 + [.25] * 6 + [.5, .3, .2] * 4))
    return st

if __name__ == "__main__":
    st = json.load(open(sys.argv[2])); c0, yaw0 = np.array(st["coef_sym"]), st["yaw"]
    init = poses(c0, np.arange(NPH) / NPH)
    rng = np.random.default_rng(3)
    pool = Pool(4)
    t0 = time.time()
    # Stage A: free yaw per pair
    jobs = [(i, [np.append(s, yaw0) for s in starts_for(init[i], rng)], None, None, 0, 2500) for i in range(NU)]
    resA = pool.map(solve, jobs)
    yaws = [r[0][-1] for r in resA]
    yaw = float(np.median(yaws))
    K = init.copy()
    for i, r in enumerate(resA):
        K[i] = r[0][:-1]
        if not NOSYM: K[i + NPH // 2] = mirror(K[i])
    print(f"stage A: per-pair yaw {np.round(np.degrees(yaws), 1).tolist()} -> {np.degrees(yaw):.1f}; loss/img {sum(r[1] for r in resA)/len(phase):.0f} ({time.time()-t0:.0f}s)", flush=True)
    # Stage B: fixed yaw, multi-start, then neighbour smoothing
    for rnd, pw in enumerate((0.0, 0.15, 0.3)):
        t0 = time.time()
        jobs = []
        for i in range(NU):
            prior = None
            if pw > 0:
                prior = 0.5 * (K[(i - 1) % NPH] + K[(i + 1) % NPH])
            jobs.append((i, starts_for(K[i], rng, 3 if rnd == 0 else 1), yaw, prior, pw, 3000))
        res = pool.map(solve, jobs)
        for i, r in enumerate(res):
            K[i] = r[0]
            if not NOSYM: K[i + NPH // 2] = mirror(K[i])
        print(f"stage B{rnd} (smooth {pw}): loss/img {sum(r[1] for r in res)/len(phase):.0f} ({time.time()-t0:.0f}s)", flush=True)
        json.dump({"K": K.tolist(), "yaw": yaw, "place": [h, px, pz, yaw], "nph": NPH},
                  open(f"{S}/data/keys_{CH}_{TAG}.json", "w"))
    # per-image fit file (for viz/validate) and a dense periodic interpolation (for curves)
    json.dump({"P": K[PH_IDX].tolist(), "place": [h, px, pz, yaw], "phase": phase.tolist(), "uniq": uniq.tolist()},
              open(f"{S}/data/fitkeys_{CH}_{TAG}.json", "w"))
    print("done", flush=True)
