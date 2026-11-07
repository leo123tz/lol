"""Joint fit of a bilaterally-symmetric periodic R6 model to all frames of one character.

Model: left limb(t) = right limb(t + 1/2); torso/head channels are split into even channels
(bob, depth sway, lean, head pitch: period 1/2) and odd channels (lateral sway, yaw, roll, head
yaw/roll: sign flips every half cycle). The character's facing yaw is optimised jointly.

usage: python3 fit_sym.py walk|run ITERS [--init template|perframe|FILE] [--alt] [--tag NAME]"""
import sys, json, time
import numpy as np
from multiprocessing import Pool
from scipy.optimize import minimize
_argv = list(sys.argv)
CH = _argv[1]
sys.argv = [_argv[0], CH]
from fit import *  # noqa: masks, renderer and loss for this character
sys.argv = _argv
ITERS = int(sys.argv[2])
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
TAG = arg("--tag", "sym"); INIT = arg("--init", "perframe")
H = {"walk": 4, "run": 3}[CH]  # run: 8 distinct phases -> at most 7 coefficients per channel
EVEN = ["ty", "tz", "t_lean", "h_pitch"]
ODD = ["tx", "t_yaw", "t_roll", "h_yaw", "h_roll"]
RIGHT = ["ra_pitch", "ra_out", "ra_twist", "rl_pitch", "rl_out", "rl_twist"]
LAYOUT = []
for n in EVEN: LAYOUT += [(n, 0, "c")] + [(n, k, t) for k in (2, 4) if k <= H for t in "cs"]
for n in ODD: LAYOUT += [(n, k, t) for k in (1, 3) if k <= H for t in "cs"]
for n in RIGHT: LAYOUT += [(n, 0, "c")] + [(n, k, t) for k in range(1, H + 1) for t in "cs"]
NC = len(LAYOUT)
IDX = {n: [i for i, l in enumerate(LAYOUT) if l[0] == n] for n in EVEN + ODD + RIGHT}

def basis(ph, k, t):
    if k == 0: return np.ones_like(ph)
    return np.cos(2*np.pi*k*ph) if t == "c" else np.sin(2*np.pi*k*ph)

def poses(c, ph):
    ph = np.atleast_1d(np.asarray(ph, float)); P = np.zeros((len(ph), NP))
    for v, (n, k, t) in zip(c, LAYOUT):
        P[:, NAMES.index(n)] += v * basis(ph, k, t)
        if n in RIGHT:
            P[:, NAMES.index(n.replace("ra_", "la_").replace("rl_", "ll_"))] += v * basis((ph + 0.5) % 1, k, t)
    return P

def project(P, ph):
    """least-squares projection using both sides (left mirrored by half a cycle)"""
    c = np.zeros(NC)
    for n in EVEN + ODD + RIGHT:
        if n in RIGHT:
            m = NAMES.index(n.replace("ra_", "la_").replace("rl_", "ll_"))
            x = np.concatenate([ph, (ph - 0.5) % 1]); y = np.concatenate([P[:, NAMES.index(n)], P[:, m]])
        else:
            s = -1 if n in ODD else 1
            x = np.concatenate([ph, (ph + 0.5) % 1]); y = np.concatenate([P[:, NAMES.index(n)], s * P[:, NAMES.index(n)]])
        A = np.stack([basis(x, LAYOUT[i][1], LAYOUT[i][2]) for i in IDX[n]], 1)
        c[IDX[n]] = np.linalg.lstsq(A, y, rcond=None)[0]
    return c

def template(a, kind):
    """parametric start: legs and arms in counter-phase, a = phase of right-leg max forward swing"""
    c = np.zeros(NC)
    def setf(n, k, amp, ph0=a):  # amp*cos(2pi k (phi - ph0))
        ic, is_ = [i for i in IDX[n] if LAYOUT[i][1] == k]
        c[ic] = amp * np.cos(2*np.pi*k*ph0); c[is_] = amp * np.sin(2*np.pi*k*ph0)
    def const(n, v): c[[i for i in IDX[n] if LAYOUT[i][1] == 0][0]] = v
    if kind == "run":
        const("t_lean", 0.6); const("ty", -0.15); const("rl_pitch", 0.2); setf("rl_pitch", 1, 1.0)
        const("ra_pitch", 0.3); setf("ra_pitch", 1, -1.3); const("ra_out", 0.25); const("rl_out", 0.05)
    else:
        const("rl_pitch", 0.35); setf("rl_pitch", 1, 0.8); const("ra_pitch", 0.0); setf("ra_pitch", 1, -0.7)
        const("ra_out", 0.3); const("rl_out", 0.0)
    return c

def _job(a):
    k, p, place, h = a
    p = np.clip(p, LO, HI)
    lab, _, _ = REN.render(part_frames(p, place, face=True), cam_matrix(h))
    return loss_img(lab, k) + np.sum(REG * p ** 2)

def total(x, pool, base):
    c, yaw = x[:-1], x[-1]
    h, px, pz = base
    P = poses(c, phase)
    l = sum(pool.map(_job, [(k, P[k], (px, pz, yaw), h) for k in range(NF)]))
    G = poses(c, np.linspace(0, 1, 60, endpoint=False))  # stay within joint limits between samples too
    l += 2000 * (np.clip(LO - G, 0, None) ** 2 + np.clip(G - HI, 0, None) ** 2).sum()
    return l / NF

def _pf(a):
    k, starts, prior, pw, place, h = a
    best = None
    for s0 in starts:
        x, f = opt((k, s0, place, h, prior, pw, 1500))
        if best is None or f < best[1]: best = (x, f)
    return best

def save(x, base):
    h, px, pz = base; c, yaw = x[:-1], x[-1]
    json.dump({"coef_sym": c.tolist(), "yaw": float(yaw), "place": [h, px, pz, float(yaw)]},
              open(f"{S}/data/sym_{CH}_{TAG}.json", "w"))
    Ps = poses(c, phase)
    json.dump({"P": Ps.tolist(), "place": [h, px, pz, float(yaw)], "phase": phase.tolist(), "uniq": uniq.tolist()},
              open(f"{S}/data/fitsym_{CH}_{TAG}.json", "w"))
    g = np.linspace(0, 1, 120, endpoint=False)
    json.dump({"P": poses(c, g).tolist(), "place": [h, px, pz, float(yaw)], "phase": g.tolist()},
              open(f"{S}/data/dense_{CH}_{TAG}.json", "w"))

if __name__ == "__main__":
    P0, (h, px, pz, yaw0), _ = load()
    base = (h, px, pz)
    pool = Pool(4)
    if INIT == "template":
        grid = {}
        for yawd in range(140, 225, 10):
            for a in np.arange(0, 1, 1 / 12):
                x = np.append(template(a, CH), np.radians(yawd))
                grid[(yawd, round(a, 3))] = total(x, pool, base)
        top = sorted(grid, key=grid.get)[:5]
        print("template grid best:", [(k, round(grid[k])) for k in top], flush=True)
        x = np.append(template(top[0][1], CH), np.radians(top[0][0]))
    elif INIT == "perframe":
        x = np.append(project(P0, phase), yaw0)
    else:
        st = json.load(open(INIT)); x = np.append(st["coef_sym"], st["yaw"])
    print(f"init ({INIT}): loss/frame {total(x, pool, base):.1f} yaw {np.degrees(x[-1]):.1f}", flush=True)
    if "--alt" in sys.argv:
        for rnd, pw in enumerate((0.3, 0.6, 1.2, 2.5)):
            t0 = time.time(); yaw = x[-1]
            prior = np.clip(poses(x[:-1], phase), LO, HI)
            Pc = P0 if (rnd == 0 and INIT == "perframe") else prior
            jobs = []
            for k in range(NF):
                st_ = [prior[k], Pc[k]]
                for i in (15, 18, 9, 12):
                    q = prior[k].copy(); q[i] = -q[i]; st_.append(q)
                jobs.append((k, st_, prior[k], pw, (px, pz, yaw), h))
            res = pool.map(_pf, jobs)
            P0 = np.array([r[0] for r in res])
            x = np.append(project(P0, phase), yaw)
            print(f"alt round {rnd} pw={pw}: per-frame {np.mean([r[1] for r in res]):.1f}  symmetric {total(x, pool, base):.1f} ({time.time()-t0:.0f}s)", flush=True)
            save(x, base)
    for it in range(ITERS):
        t0 = time.time()
        r = minimize(total, x, args=(pool, base), method="Powell", options={"maxiter": 1, "xtol": 1e-3, "ftol": 1e-5})
        x = r.x
        print(f"iter {it}: loss/frame {r.fun:.1f} yaw {np.degrees(x[-1]):.1f} ({time.time()-t0:.0f}s)", flush=True)
        save(x, base)
    save(x, base)
