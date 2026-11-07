import numpy as np, sys
sys.path.insert(0, __file__.rsplit('/',1)[0])
from r6 import *
from PIL import Image
S = __file__.rsplit('/',2)[0]
ROI = {"walk": (100, 75, 300, 280), "run": (270, 75, 460, 270)}
def place_from_pixel(u, v, depth, h_known=None):
    pc = np.array([(u-CX)/F, -(v-CY)/F, -1.0]) * depth
    pw = Rx(-PITCH) @ pc
    h = 3.0 - pw[1]
    return h, pw[0], pw[2]
def overlay(frame, lab, roi, scale=3):
    x0,y0,x1,y1 = roi
    img = frame[y0:y1, x0:x1].astype(float).copy()
    edge = np.zeros(lab.shape, bool)
    edge[1:,:] |= lab[1:,:] != lab[:-1,:]; edge[:,1:] |= lab[:,1:] != lab[:,:-1]
    col = np.where((lab==1)[...,None], [255,60,60], [255,230,0])
    e = edge & (lab>0) | edge
    img[edge] = [255,0,255]
    img[lab==3] = [255,0,0]
    tint = ((lab>0)&(lab<3))[...,None]
    img = np.where(tint, img*0.75 + 0.25*np.where((lab==1)[...,None],[255,0,0],[0,255,0]), img)
    img[edge] = [255,0,255]
    return Image.fromarray(img.clip(0,255).astype(np.uint8)).resize(((x1-x0)*scale,(y1-y0)*scale), Image.NEAREST)

def curve_eval_factory(curve):
    """curve JSON -> function(phase array) -> (n, NP) poses. Supports periodic spline and Fourier."""
    if curve.get("type") == "spline":
        from scipy.interpolate import CubicSpline
        K = np.array(curve["K"]); n = len(K)
        x = np.arange(n + 1) / n; y = np.vstack([K, K[:1]])
        cs = CubicSpline(x, y, bc_type="periodic", axis=0)
        return lambda ph: cs(np.atleast_1d(np.asarray(ph, float)) % 1.0), cs
    coef = np.array(curve["coef"]); H = curve["H"]
    def f(ph):
        ph = np.atleast_1d(np.asarray(ph, float)); cols = [np.ones_like(ph)]
        for k in range(1, H + 1): cols += [np.cos(2*np.pi*k*ph), np.sin(2*np.pi*k*ph)]
        return np.stack(cols, 1) @ coef
    return f, None
