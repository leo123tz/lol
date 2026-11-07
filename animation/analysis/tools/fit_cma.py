"""CMA-ES refinement of the symmetric periodic model (coefficients + facing yaw).
usage: python3 fit_cma.py walk|run INIT_SYM_JSON GENERATIONS [--tag NAME] [--sigma S]"""
import sys, json, time
import numpy as np
from multiprocessing import Pool
import cma
_argv = list(sys.argv)
CH = _argv[1]
sys.argv = [_argv[0], CH, "0"]
import fit_sym as FS
from fit_sym import *  # noqa
sys.argv = _argv
INIT, GENS = sys.argv[2], int(sys.argv[3])
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
TAG = arg("--tag", "cma"); SIG = float(arg("--sigma", "0.12"))
P0, (h, px, pz, _), _ = load()

def score(x):
    c, yaw = x[:-1], x[-1]
    P = np.clip(poses(c, phase), LO, HI)
    l = 0.0
    for k in range(NF):
        lab, _, _ = REN.render(part_frames(P[k], (px, pz, yaw), face=True), cam_matrix(h))
        l += loss_img(lab, k) + np.sum(REG * P[k] ** 2)
    G = poses(c, np.linspace(0, 1, 60, endpoint=False))
    l += 2000 * (np.clip(LO - G, 0, None) ** 2 + np.clip(G - HI, 0, None) ** 2).sum()
    return l / NF

if __name__ == "__main__":
    st = json.load(open(INIT)); x0 = np.append(st["coef_sym"], st["yaw"])
    scale = np.array([0.6 if LAYOUT[i][0] in ("ty", "tx", "tz") else 1.0 for i in range(NC)] + [0.6])
    es = cma.CMAEvolutionStrategy(x0, SIG, {"CMA_stds": scale, "popsize": 24, "verbose": -9, "seed": 7})
    pool = Pool(4)
    best = (score(x0), x0); t0 = time.time()
    print(f"start {best[0]:.1f}", flush=True)
    for g in range(GENS):
        X = es.ask(); F = pool.map(score, X); es.tell(X, F)
        i = int(np.argmin(F))
        if F[i] < best[0]: best = (F[i], np.array(X[i]))
        if g % 50 == 0 or g == GENS - 1:
            print(f"gen {g}: best {best[0]:.1f}  pop-median {np.median(F):.1f}  sigma {es.sigma:.3f}  yaw {np.degrees(best[1][-1]):.1f}  ({time.time()-t0:.0f}s)", flush=True)
            FS.TAG = TAG; FS.save(best[1], (h, px, pz))
        if es.stop(): print("stop", es.stop(), flush=True); break
    FS.TAG = TAG; FS.save(best[1], (h, px, pz))
    print(f"final {best[0]:.1f}", flush=True)
