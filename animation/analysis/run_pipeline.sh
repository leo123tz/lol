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
python3 timing.py                    # cycle lengths by autocorrelation (walk 30 f, run 20 f)
python3 masks.py                     # per-frame labels: white parts / torso / certain background

# 1) initial tracking from a rough placement guess (torso pixel + apparent size)
python3 fit.py walk track 2
python3 fit.py run  track 2
# 2) global depth/yaw search per character (camera height follows from depth)
python3 place_search.py walk 212 165     # -> depth 7.7, yaw 180,   camera height 5.87
python3 place_search.py run  365 160     # -> depth 8.3, yaw 151.4, camera height 5.93
# 3) re-track with one shared camera height of 5.90 studs (depths solved for that height)
python3 fit.py walk track 2 --place 7.777 180 --fix-place
python3 fit.py run  track 2 --place 8.222 151.4 --fix-place
python3 fit_sym.py walk 6 --alt --tag sym     # bilaterally symmetric periodic model
python3 fit_sym.py run  6 --alt --tag sym

for CH in walk run; do
  cp "../data/fitsym_${CH}_sym.json" "../data/fit_${CH}.json"
  FITFILE="../data/dense_${CH}_sym.json" RIDGE=0 python3 make_curves.py "$CH" "$REPO/animation/data"
done

python3 "$REPO/animation/blender/build_r6_locomotion.py" --out "$REPO/animation/output" --preview
python3 validate.py walk "$REPO/animation/output/R6_Walk.rbxmx"
python3 validate.py run  "$REPO/animation/output/R6_Run.rbxmx"
python3 compare_video.py walk "$REPO/animation/output/preview/R6_Walk" ../data/curve_walk.json "$REPO/animation/output/compare_walk.mp4"
python3 compare_video.py run  "$REPO/animation/output/preview/R6_Run"  ../data/curve_run.json  "$REPO/animation/output/compare_run.mp4"
