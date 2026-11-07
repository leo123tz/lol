"""Extract the gameplay region of the reference video and its unique frames.
usage: python3 prepare.py path/to/reference.mp4
Writes data/game.raw (576x324 rgb24, 8 s from t=0.6 s), data/frames.npy (unique frames of one
2-second loop) and data/uniq.npy (their frame indices at 30 fps)."""
import subprocess, sys, os
import numpy as np
S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(f"{S}/data", exist_ok=True); os.makedirs(f"{S}/sheets", exist_ok=True)
video = sys.argv[1]
# The TikTok frame is 576x768; the 16:9 gameplay capture occupies rows 222..545.
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.6", "-t", "8.0", "-i", video, "-vf", "crop=576:324:0:222",
                "-pix_fmt", "rgb24", "-f", "rawvideo", f"{S}/data/game.raw"], check=True)
a = np.fromfile(f"{S}/data/game.raw", np.uint8).reshape(-1, 324, 576, 3)[:61].astype(np.float32)
# the capture runs at ~12.5 fps inside a 30 fps stream: keep the first copy of each new frame
d = [np.abs(a[i] - a[i - 1]).mean() for i in range(1, 61)]
uniq = [0] + [i for i in range(1, 60) if d[i - 1] > 1.0]
np.save(f"{S}/data/uniq.npy", np.array(uniq)); np.save(f"{S}/data/frames.npy", a[uniq].astype(np.uint8))
print(len(uniq), "unique frames in one 60-frame loop:", uniq)
