# Reference video analysis

Source: the provided TikTok clip *"Walking and running animations"* (576×768, 30 fps, 19.0 s).
Two R6 characters animate in place on a Baseplate: the left one is labelled **Walk** and
the right one **Run** (the name tags are visible above their heads). From 14.5 s onward the
clip is a TikTok outro with no animation.

## Timing

| Measurement | Result | How |
|---|---|---|
| Gameplay region | 576×324 (exactly 16:9) at rows 222–545 | frame layout |
| Recording | a **2.000 s clip looped ~7×** | frame difference at lag 60 is at the compression-noise floor for both characters |
| Capture rate | **12 fps, uniform** (24 distinct images per loop) | 60 video frames contain 24 unique images. TikTok's 30 fps conversion repeats them in an uneven 3-2-3-2… pattern |
| Walk cycle | **1.000 s** (30 frames @ 30 fps) | autocorrelation peak at lag 30. Images *j* and *j*+12 match, so 12 distinct poses per cycle, each captured twice |
| Run cycle | **0.667 s** (20 frames @ 30 fps) | autocorrelation peaks at lags 20/40/60. Images *j*, *j*+8 and *j*+16 are identical (mean abs. difference 1.5 vs 11–20 between neighbours), so 8 distinct poses per cycle, each captured three times |

Watch out for this when reading the video by eye: because of the uneven duplication, the
first-appearance frame of an image is **not** its capture time. Using it shifts some poses by
up to a frame (5% of the run cycle). All measurements here use the true 12 fps capture
times, *t = j × 2.5* video frames.

## Camera and placement

| Quantity | Value | Evidence |
|---|---|---|
| Vertical FOV | 70° | Roblox default; the 16:9 capture is uncropped |
| Pitch | 21.1° down | horizon at row 72.5 of 324 |
| Camera height above the floor | 5.90 studs | independent depth searches for the two characters gave 5.87 and 5.93 |
| Walker | 7.8 studs away, facing the camera | its face is centred on the head |
| Runner | 8.2 studs away, to the right | its face is off-centre, so it is turned (see fitted yaw below) |

The fact that two characters fitted independently agree on the camera height (within 1%)
is the main check that the camera model is right.

## Measurement method

1. **Segmentation.** Each of the 24 images is split into: lit white parts (head and limbs),
   grey torso, certain background (a pixel matching a temporally stable ground plate whose
   colour fits that image row's floor colour, plus cast shadows on the floor), and
   *unknown*. Faces turned away from the sun take Roblox's blue sky-ambient tint and become
   indistinguishable from the floor. A margin around lit regions is therefore treated as
   unknown, not as background. The face (eyes and smile) is extracted separately, as dark
   pixels enclosed by the white head.
2. **Model.** The R6 body uses Roblox's exact Motor6D geometry: RootJoint at the torso centre,
   Neck at (0, 1, 0), shoulders at (±1, 0.5, 0) on the torso edge, hips at (±1, −1, 0) on the
   outer top of each leg. Parts are Torso 2×2×1, limbs 1×2×1 and head ≈1.2³, plus the face
   features. The model is rendered with a z-buffer through the reconstructed camera.
3. **Loss.** For every image this counts reference white pixels not covered by white model
   parts, model parts on certain background (plus a distance term), white/torso
   occlusion-order mismatches, face mismatch, and a small cost for covering unknown pixels.
4. **Symmetric periodic model.** The poses are smooth periodic curves (Fourier series:
   4 harmonics for the walk, 3 for the run, since it has only 8 distinct phases):
   - the left limbs are the right limbs half a cycle later;
   - bob, depth sway, lean and head pitch repeat every half cycle;
   - lateral sway, yaw, roll and head yaw/roll flip sign every half cycle.

   The walk was checked to be bilaterally symmetric by comparing each image with the
   mirror image of the one half a cycle later. Fitting both sides jointly removes the
   front/back ambiguity of a single camera view: a leg swung back and a leg hanging down look
   alike from the front, but their mirrored partners don't.
5. **Optimisation.** A grid search over facing yaw × phase offset of a parametric template
   (or a projection of independent per-frame fits) provides the start. CMA-ES then
   optimises the curve coefficients and the facing yaw against all 24 images together.
6. **Export.** The curves are keyed in Blender (walk: a key every 3 frames, run: every 2 frames,
   Bézier handles from the analytic slopes, Cycles modifiers for seamless looping). The
   Roblox KeyframeSequence is sampled at 60 Hz from the evaluated Blender rig.

## Results and comparison with the original files

The creator's source files (`animation/source/`) later became available. They confirm the
measurements:

| | Measured from the video | Original file |
|---|---|---|
| Walk cycle | 1.000 s | 60 frames @ 60 fps = 1.000 s |
| Run cycle | 0.667 s | 40 frames @ 60 fps = 0.667 s |

Rendered through the reconstructed camera, the original walk overlays the video almost
perfectly (`img/verify_walk.png`). The original run reproduces the pose sequence
(`img/verify_run.png`). The residual offset comes from the runner's estimated placement,
which was taken from the approximate pose fit.

The pose fitting itself recovered the walk only approximately and the run poorly. From a
single front/three-quarter view at 12 fps, a limb swung forward and one swung back look
nearly the same. The shipped animations are therefore the originals, not the fitted curves.
