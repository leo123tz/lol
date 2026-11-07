"""Overlay sheet of the current fit for a character: python3 viz.py walk|run [fourier]"""
import sys, json
from common import *
sys.argv += [""]
CH = sys.argv[1]
import os
st = json.load(open(os.environ.get("FITFILE", f"{S}/data/fit_{CH}.json")))
P = np.array(st["P"]); h, px, pz, yaw = st["place"]; ph = np.array(st["phase"])
if sys.argv[2] == "fourier":
    import fit as _f  # noqa
fr = np.load(f"{S}/data/frames.npy")
R = Renderer(ROI[CH])
order = np.argsort(ph)
tiles = []
for k in order:
    lab, _, _ = R.render(part_frames(P[k], (px, pz, yaw), face=True), cam_matrix(h))
    im = overlay(fr[k], lab, ROI[CH], 1)
    im = np.array(im); im[:12, :40] = 0
    from PIL import ImageDraw
    pi = Image.fromarray(im); ImageDraw.Draw(pi).text((2, 0), f"{ph[k]:.2f}", fill=(255, 255, 0)); tiles.append(np.array(pi))
rows = [np.concatenate(tiles[i:i+8], 1) for i in range(0, len(tiles), 8)]
Image.fromarray(np.concatenate(rows, 0)).save(os.environ.get("OUT", f"{S}/sheets/fit_{CH}.png"))
print("loss", np.round(st.get("loss", []), 0))
