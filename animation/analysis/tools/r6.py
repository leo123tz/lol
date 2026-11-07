"""R6 kinematics (exact Roblox Motor6D pivots) + tiny z-buffered box renderer for fitting."""
import numpy as np

F = 162.0 / np.tan(np.radians(35.0))  # 70 deg vertical FOV on a 324px-tall frame
CX, CY = 288.0, 162.0
HORIZON_V = 72.5
PITCH = np.arctan((CY - HORIZON_V) / F)

def Rx(a):
    c, s = np.cos(a), np.sin(a); return np.array([[1,0,0],[0,c,-s],[0,s,c]])
def Ry(a):
    c, s = np.cos(a), np.sin(a); return np.array([[c,0,s],[0,1,0],[-s,0,c]])
def Rz(a):
    c, s = np.cos(a), np.sin(a); return np.array([[c,-s,0],[s,c,0],[0,0,1]])
def M(R=None, t=(0,0,0)):
    m = np.eye(4)
    if R is not None: m[:3,:3] = R
    m[:3,3] = t; return m

# parameter layout (21): bob ty, tx, tz | torso lean, yaw, roll | head pitch, yaw, roll |
# RA pitch, roll(out), twist | LA ... | RL ... | LL ...   (angles in radians)
NAMES = ["ty","tx","tz","t_lean","t_yaw","t_roll","h_pitch","h_yaw","h_roll",
         "ra_pitch","ra_out","ra_twist","la_pitch","la_out","la_twist",
         "rl_pitch","rl_out","rl_twist","ll_pitch","ll_out","ll_twist"]
NP = len(NAMES)

def torso_rot(p):  return Ry(p[4]) @ Rx(-p[3]) @ Rz(p[5])
def head_rot(p):   return Ry(p[7]) @ Rx(-p[6]) @ Rz(p[8])
def limb_rot(pitch, out, twist, side):  # side +1 right, -1 left
    return Rx(pitch) @ Rz(side * out) @ Ry(-side * twist)

FACE_PARTS = {"FaceL": ((0.07, 0.16, 0.02), (-0.13, 0.18, -0.61)), "FaceR": ((0.07, 0.16, 0.02), (0.13, 0.18, -0.61)),
              "Mouth": ((0.42, 0.08, 0.02), (0.0, -0.24, -0.61))}
SIZES = {"FaceL": FACE_PARTS["FaceL"][0], "FaceR": FACE_PARTS["FaceR"][0], "Mouth": FACE_PARTS["Mouth"][0],
         "Torso": (2,2,1), "Head": (1.2,1.2,1.2), "Right Arm": (1,2,1), "Left Arm": (1,2,1),
         "Right Leg": (1,2,1), "Left Leg": (1,2,1)}
LIMBS = [("Right Arm", (1,0.5,0), (0.5,-0.5,0), 9, 1), ("Left Arm", (-1,0.5,0), (-0.5,-0.5,0), 12, -1),
         ("Right Leg", (1,-1,0), (-0.5,-1,0), 15, 1), ("Left Leg", (-1,-1,0), (0.5,-1,0), 18, -1)]

def part_frames(p, place, face=False):
    """place = (px, pz, yaw). Returns dict part -> 4x4 world matrix (Roblox space)."""
    px, pz, yaw = place
    hrp = M(Ry(yaw), (px, 3.0, pz))
    torso = hrp @ M(None, (p[1], p[0], p[2])) @ M(torso_rot(p))
    out = {"Torso": torso}
    out["Head"] = torso @ M(None, (0,1,0)) @ M(head_rot(p)) @ M(None, (0,0.5,0))
    for name, piv, off, i, side in LIMBS:
        out[name] = torso @ M(None, piv) @ M(limb_rot(p[i], p[i+1], p[i+2], side)) @ M(None, off)
    if face:
        for fn, (_, pos) in FACE_PARTS.items():
            out[fn] = out["Head"] @ M(None, pos)
    return out

def cam_matrix(h):
    C = M(Rx(-PITCH), (0, h, 0))
    return np.linalg.inv(C)

_CORN = np.array([[sx,sy,sz] for sx in (-.5,.5) for sy in (-.5,.5) for sz in (-.5,.5)])
_FACES = [((1,0,0),[4,5,7,6]),((-1,0,0),[0,2,3,1]),((0,1,0),[2,6,7,3]),((0,-1,0),[0,1,5,4]),
          ((0,0,1),[1,3,7,5]),((0,0,-1),[0,4,6,2])]

class Renderer:
    def __init__(self, roi, ss=1):
        x0, y0, x1, y1 = roi; self.roi = roi; self.ss = ss
        us = x0 + (np.arange((x1-x0)*ss) + 0.5) / ss
        vs = y0 + (np.arange((y1-y0)*ss) + 0.5) / ss
        self.U, self.V = np.meshgrid(us, vs)
        self.D = np.stack([(self.U-CX)/F, -(self.V-CY)/F, -np.ones_like(self.U)], -1)
        self.H, self.W = self.U.shape

    def render(self, frames, view, labels=None):
        """returns label image (0 bg, 1 torso, 2 white parts) and depth. labels: part->label"""
        lab = np.zeros((self.H, self.W), np.uint8); z = np.full((self.H, self.W), np.inf)
        pid = np.full((self.H, self.W), -1, np.int8)
        for k, (name, Mw) in enumerate(frames.items()):
            L = 1 if name == "Torso" else (3 if name in FACE_PARTS else 2)
            if labels: L = labels.get(name, L)
            Mc = view @ Mw
            S = np.array(SIZES[name])
            P = (Mc[:3,:3] @ (_CORN * S).T).T + Mc[:3,3]
            if np.any(P[:,2] > -0.05): continue
            uv = np.stack([CX + F*P[:,0]/(-P[:,2]), CY - F*P[:,1]/(-P[:,2])], -1)
            for n, idx in _FACES:
                nc = Mc[:3,:3] @ np.array(n, float)
                fc = P[idx].mean(0)
                if nc @ (-fc) <= 0: continue
                q = uv[idx]
                xa = int(max(np.floor((q[:,0].min()-self.roi[0])*self.ss), 0)); xb = int(min(np.ceil((q[:,0].max()-self.roi[0])*self.ss), self.W))
                ya = int(max(np.floor((q[:,1].min()-self.roi[1])*self.ss), 0)); yb = int(min(np.ceil((q[:,1].max()-self.roi[1])*self.ss), self.H))
                if xa >= xb or ya >= yb: continue
                Us = self.U[ya:yb, xa:xb]; Vs = self.V[ya:yb, xa:xb]
                inside = np.ones(Us.shape, bool)
                area = 0.0
                for j in range(4):
                    a, b = q[j], q[(j+1)%4]; area += a[0]*b[1]-a[1]*b[0]
                sg = 1.0 if area > 0 else -1.0
                for j in range(4):
                    a, b = q[j], q[(j+1)%4]
                    inside &= sg*((b[0]-a[0])*(Vs-a[1]) - (b[1]-a[1])*(Us-a[0])) >= 0
                if not inside.any(): continue
                d = nc @ fc
                den = self.D[ya:yb, xa:xb] @ nc
                t = d / np.where(np.abs(den) < 1e-9, 1e-9, den)
                zs = z[ya:yb, xa:xb]
                w = inside & (t < zs) & (t > 0)
                zs[w] = t[w]; lab[ya:yb, xa:xb][w] = L; pid[ya:yb, xa:xb][w] = k
        return lab, z, pid
