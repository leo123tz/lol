# R6 Walk & Run — reference-video recreation (Blender → Roblox)

Recreates the walking and running animations shown in the reference video
(TikTok clip "Walking and running animations") as real keyframed animations for an
**R6** rig. They're authored in Blender and exported as Roblox `KeyframeSequence`s, with a
small client controller that plays them in game.

```
animation/
  data/R6_Walk.json, R6_Run.json      keyframed curves measured from the video (source of truth)
  blender/build_r6_locomotion.py      builds the R6 rig + actions in Blender, exports everything
  output/R6_Locomotion.blend          Blender file: R6 rig, actions "R6_Walk" and "R6_Run"
  output/R6_Walk.rbxmx, R6_Run.rbxmx  Roblox KeyframeSequences (import into Studio)
  output/R6_Walk.fbx, R6_Run.fbx      skinned R6 + baked action (interchange / archive)
  output/compare_*.mp4                reference vs. recreation, side by side
  analysis/                           the measurement pipeline used to extract the motion
roblox/
  default.project.json                optional Rojo project (syncs only the files below)
  src/ReplicatedStorage/LocomotionAnimation/Config.lua         animation ids + tuning
  src/ReplicatedStorage/LocomotionAnimation/Sources/*.rbxmx    KeyframeSequences (Studio test)
  src/StarterPlayer/StarterCharacterScripts/LocomotionAnimator.client.lua
docs/REFERENCE_ANALYSIS.md            what the video shows, with measurements
```

## How the motion was obtained

The animations were **measured from the video**, not drawn by eye. See
[docs/REFERENCE_ANALYSIS.md](docs/REFERENCE_ANALYSIS.md) for details.

1. The clip is a 2.000 s recording looped ~7×, captured at a uniform 12 fps. Cycle
   lengths were measured by frame autocorrelation: **walk 1.000 s (30 frames @ 30 fps),
   run 0.667 s (20 frames)**. Each loop therefore shows 12 distinct walk poses and 8 distinct
   run poses, every one captured 2–3 times, which also gives a check on the measurements.
2. The camera was reconstructed from the frame: 16:9 capture, Roblox's default 70° vertical
   FOV, horizon height gives a 21.1° downward pitch, and R6 part sizes give scale and distance.
3. An R6 model with Roblox's exact Motor6D pivots (shoulders at the torso edge, hips at the
   outer top of each leg, neck, root joint) was fitted to every frame by silhouette and
   occlusion matching. That's 21 degrees of freedom per frame: root bob/sway, torso lean, yaw
   and roll, head, and swing/abduction/twist for each limb, all within anatomical bounds.
4. The per-frame poses were turned into smooth periodic curves and keyed in Blender
   (walk: a key every 3 frames, run: every 2 frames, Bézier handles from the curve slopes).
   The `.rbxmx` export is sampled from the evaluated Blender rig.

## Blender

The script runs in Blender 4.4+ / 5.x, or headless with the `bpy` module:

```bash
blender -b -P animation/blender/build_r6_locomotion.py -- --out animation/output
# or: pip install bpy && python3 animation/blender/build_r6_locomotion.py --out animation/output
# add --preview to also render the reference-camera previews (Cycles; --engine to override)
```

To edit the animation by hand, open `animation/output/R6_Locomotion.blend` and select
`R6Rig`. Its actions are `R6_Walk` and `R6_Run`, and every pose bone is named after its
R6 part:

| Bone | Euler | X | Y | Z |
|---|---|---|---|---|
| Torso | ZXY | −lean (pitch) | yaw | roll |
| Head | ZXY | −pitch | yaw | roll |
| Right/Left Arm, Right/Left Leg | YZX | swing (+ forward) | twist | abduction (+ out on the right, − out on the left) |

Bone heads sit exactly on the Motor6D pivots and bone axes equal the Roblox part axes, so
what you key is exactly what Roblox plays. Curves carry a Cycles modifier, so loops are
seamless. After hand-editing, re-export the `.rbxmx`/FBX from the edited file without
rebuilding it:

```bash
blender animation/output/R6_Locomotion.blend -b -P animation/blender/build_r6_locomotion.py -- --export-only
```

## Roblox Studio import (manual steps)

Publishing animations requires your Roblox account, so these steps are manual:

1. **Insert the KeyframeSequences.** In Studio, right-click `ServerStorage` → *Insert from
   File…* → choose `animation/output/R6_Walk.rbxmx`, then repeat for `R6_Run.rbxmx`.
2. **Publish.** Right-click each KeyframeSequence → *Save to Roblox…* (Studio also calls it
   *Publish to Roblox*). Publish it under the **same owner as the experience** (your user or
   the group). Roblox only plays animations owned by the experience's owner.
3. **Set the IDs.** Copy each asset ID into
   `ReplicatedStorage.LocomotionAnimation.Config` (`WalkAnimationId`, `RunAnimationId`).
4. **Add the scripts.** Either `rojo serve roblox/default.project.json` and connect, or copy
   these manually:
   - `Config.lua` → ModuleScript `ReplicatedStorage/LocomotionAnimation/Config`
   - `Sources/*.rbxmx` → `ReplicatedStorage/LocomotionAnimation/Sources/` (optional)
   - `LocomotionAnimator.client.lua` → LocalScript `StarterPlayer/StarterCharacterScripts/LocomotionAnimator`

Optional: to inspect the animation in the Animation Editor, build an R6 rig (Avatar → Rig
Builder → R6), put the KeyframeSequence in `ServerStorage.RBX_ANIMSAVES.<RigName>`, then
open the editor and use *Load*.

**Testing before publishing:** while an ID is still `0`, Studio play-tests register the
KeyframeSequence from `Sources` as a temporary local animation. This is Studio-only, and live
servers need the published IDs.

## How the controller behaves

- **R6 only.** On any other rig type it warns and does nothing.
- **Replication.** Tracks are loaded on the character's server-created `Animator` by the owning
  client, the path Roblox replicates to the server and every other player. No server code
  is needed.
- **Walk/run selection.** It uses smoothed horizontal speed with hysteresis
  (`RunEnterSpeed`/`RunExitSpeed`). Playback rate scales with speed, and at
  `WalkReferenceSpeed`/`RunReferenceSpeed` it plays exactly at the video's timing.
  Walk↔run crossfades carry the cycle phase over, since both cycles start on the same
  right-leg-forward contact.
- **States.** It plays only in the Running state on the ground. Jumping, falling, climbing,
  swimming, sitting, ragdoll/physics and death fade it out, and the default `Animate` script
  (left untouched) keeps handling those.
- **Respawn.** The script lives in StarterCharacterScripts, so every respawn gets a fresh
  instance with clean state. Tracks are stopped and destroyed when the character is.
- **Priority.** The tracks use `Movement`, which overrides the default walk (`Core`). Any
  `Action`-priority animation (for example a throw) still plays on top.

### Integrating with your throwing and crash systems

Those systems weren't in this repository (it was empty), so nothing in them was changed.
The controller is built so they need no changes:

- **Crash / ragdoll:** if your crash puts the Humanoid into `Ragdoll`, `Physics`,
  `FallingDown` or `PlatformStanding`, locomotion fades out automatically.
- **Throw:** if the throw animation uses `Action` (or higher) priority, it overrides the
  arms (and any other joints it keys) while the legs keep walking or running. That's the
  normal Roblox layering.
- **Anything else:** to silence locomotion from any script (server or client), set
  `character:SetAttribute("LocomotionSuppressed", true)`, and set it back to `false` to
  restore it.
