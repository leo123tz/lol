"""Global depth search for a character's placement (camera height derived from depth).
usage: python3 place_search.py walk|run u v"""
import sys, json, time
import numpy as np
from multiprocessing import Pool
CH = sys.argv[1]; U, V = float(sys.argv[2]), float(sys.argv[3])
sys.argv = [sys.argv[0], CH]
from fit import *
P0, (h0, px0, pz0, yaw0), _ = load()
order = np.argsort(phase); reps = order[::4]  # 6 representative frames spread over the cycle

def job(a):
    k, d, yaw = a
    h, px, pz = place_from_pixel(U, V, d)
    p, f = opt((k, P0[k], (px, pz, yaw), h, None, 0, 1500))
    return f

if __name__ == "__main__":
    pool = Pool(4)
    res = {}
    for yaw in (yaw0 - 0.15, yaw0, yaw0 + 0.15):
        for d in np.arange(5.6, 9.01, 0.3):
            fs = pool.map(job, [(k, d, yaw) for k in reps])
            res[(round(d, 2), round(float(np.degrees(yaw)), 1))] = float(np.mean(fs))
        best = min(res, key=res.get)
        print(f"yaw {np.degrees(yaw):.1f}: " + " ".join(f"{k[0]}:{v:.0f}" for k, v in res.items() if k[1] == round(float(np.degrees(yaw)), 1)), flush=True)
    best = min(res, key=res.get)
    h, px, pz = place_from_pixel(U, V, best[0])
    print("BEST depth", best[0], "yaw", best[1], "loss", round(res[best]), "-> h", round(h, 3), "px", round(px, 3), "pz", round(pz, 3))
