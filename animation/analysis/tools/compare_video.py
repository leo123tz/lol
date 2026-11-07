"""Side-by-side comparison video: reference | Blender render | outline overlay.
usage: python3 compare_video.py walk|run PREVIEW_DIR CURVE_JSON OUT.mp4"""
import sys, json, subprocess, os, tempfile
import numpy as np
from PIL import Image, ImageDraw
from common import *

CH, PREV, OUTMP4 = sys.argv[1], sys.argv[2], sys.argv[4]
cv = json.load(open(sys.argv[3])); phi0 = cv["phi0"]
_feval, _ = curve_eval_factory(cv)
st = json.load(open(os.environ.get("FITFILE", f"{S}/data/fit_{CH}.json"))); h, px, pz, yaw = st["place"]
PERIOD = {"walk": 30, "run": 20}[CH]
raw = np.fromfile(f"{S}/data/game.raw", np.uint8).reshape(-1, 324, 576, 3)
x0, y0, x1, y1 = ROI[CH]
R = Renderer(ROI[CH])
nprev = len([f for f in os.listdir(PREV) if f.endswith(".png")])
SC = 2

def fourier(phv):
    return _feval(phv)[0]

uniq = np.load(f"{S}/data/uniq.npy")
tmp = tempfile.mkdtemp()
for j in range(120):  # 4 s
    ref = raw[j % 60]
    u = int(np.searchsorted(uniq, j % 60, side="right") - 1)       # image on screen
    cap_phase = ((2.5 * u) % PERIOD) / PERIOD                       # its true capture phase
    play_phase = ((j - 0.5) % PERIOD) / PERIOD                      # smooth playback, avg display delay
    t_frames = ((play_phase - phi0) % 1) * nprev
    ours = np.array(Image.open(f"{PREV}/{int(round(t_frames)) % nprev:04d}.png").convert("RGB"))
    lab, _, _ = R.render(part_frames(fourier(cap_phase), (px, pz, yaw), face=True), cam_matrix(h))
    a = ref[y0:y1, x0:x1].copy()
    e = np.zeros(lab.shape, bool); e[1:] |= lab[1:] != lab[:-1]; e[:, 1:] |= lab[:, 1:] != lab[:, :-1]
    ov = a.copy(); ov[e] = [255, 40, 200]
    panels = [Image.fromarray(p).resize(((x1-x0)*SC, (y1-y0)*SC), Image.LANCZOS) for p in (a, ours[y0:y1, x0:x1], ov)]
    W = sum(p.width for p in panels) + 8; Hh = panels[0].height + 26
    canvas = Image.new("RGB", (W, Hh), (20, 20, 24)); d = ImageDraw.Draw(canvas)
    xo = 0
    for p, lbl in zip(panels, ("reference video", "recreation (Blender)", "recreation outline on reference")):
        canvas.paste(p, (xo, 26)); d.text((xo + 6, 7), lbl, fill=(235, 235, 235)); xo += p.width + 4
    canvas.save(f"{tmp}/{j:04d}.png")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", f"{tmp}/%04d.png", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", "20", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", OUTMP4], check=True)
Image.open(f"{tmp}/0000.png").save(OUTMP4.replace(".mp4", "_still.png"))
print("wrote", OUTMP4)
