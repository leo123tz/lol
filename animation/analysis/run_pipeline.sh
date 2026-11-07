#!/usr/bin/env bash
# Re-measure the walk/run animation from the reference video and rebuild every output.
# Requirements: ffmpeg, python3 with numpy, scipy, pillow and bpy (pip install numpy scipy pillow bpy).
# usage: animation/analysis/run_pipeline.sh path/to/reference.mp4
set -euo pipefail
VIDEO="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$HERE/tools"

python3 prepare.py "$VIDEO"          # gameplay crop + the unique frames of one 2 s loop
python3 timing.py "$(pwd)/.."         # cycle lengths by autocorrelation (walk 30 f, run 20 f)
python3 masks.py "$(pwd)/.."         # per-frame labels: white parts / torso / certain background

# 1) initial tracking from a rough placement guess (torso pixel + apparent size)
python3 fit.py walk track 2
python3 fit.py run  track 2
# 2) global depth/yaw search per character (camera height follows from depth)
python3 place_search.py walk 212 165     # -> depth 7.7, yaw 180,   camera height 5.87
python3 place_search.py run  365 160     # -> depth 8.3, yaw 151.4, camera height 5.93
# 3) re-track with one shared camera height of 5.90 studs (depths solved for that height)
python3 fit.py walk track 2 --place 7.777 180 --fix-place
python3 fit.py run  track 2 --place 8.222 151.4 --fix-place
# 4) per-phase key poses (12 walk / 8 run phases, mirror-coupled) -> projected onto a smooth
#    symmetric periodic model -> CMA-ES over all images (smooth by construction)
python3 fit_sym.py walk 0 --init template --tag tem
python3 fit_sym.py run  0 --init perframe --tag per
python3 fit_keys.py walk ../data/sym_walk_tem.json --tag keys
python3 fit_keys.py run  ../data/sym_run_per.json  --tag keys
for CH in walk run; do
  python3 -c "import sys,json,numpy as np; sys.argv=['fit_sym.py','$CH','0']; import fit_sym as F; k=json.load(open(f'{F.S}/data/keys_${CH}_keys.json')); json.dump({'coef_sym':F.project(np.array(k['K']),np.arange(k['nph'])/k['nph']).tolist(),'yaw':k['yaw']},open(f'{F.S}/data/sym_${CH}_fromkeys.json','w'))"
  python3 fit_cma.py "$CH" "../data/sym_${CH}_fromkeys.json" 700 --tag cma --sigma 0.2
  FITFILE="../data/dense_${CH}_cma.json" RIDGE=0 python3 make_curves.py "$CH" "$REPO/animation/data"
done

python3 "$REPO/animation/blender/build_r6_locomotion.py" --out "$REPO/animation/output" --preview
FITFILE=../data/fitsym_walk_cma.json python3 validate.py walk "$REPO/animation/output/R6_Walk.rbxmx"
FITFILE=../data/fitsym_run_cma.json python3 validate.py run  "$REPO/animation/output/R6_Run.rbxmx"
FITFILE=../data/fitsym_walk_cma.json python3 compare_video.py walk "$REPO/animation/output/preview/R6_Walk" ../data/curve_walk.json "$REPO/animation/output/compare_walk.mp4"
FITFILE=../data/fitsym_run_cma.json python3 compare_video.py run  "$REPO/animation/output/preview/R6_Run"  ../data/curve_run.json  "$REPO/animation/output/compare_run.mp4"
