--!strict
-- Locomotion animation configuration (R6).
--
-- After publishing the two KeyframeSequences (see README "Roblox Studio import"),
-- paste the resulting asset IDs below. While an ID is left at 0, the controller
-- falls back to the KeyframeSequence in ReplicatedStorage.LocomotionAnimation.Sources
-- *in Studio only* (KeyframeSequenceProvider:RegisterKeyframeSequence), so you can
-- test before publishing. Live servers require real published IDs.

local Config = {}

Config.WalkAnimationId = 0 -- rbxassetid of R6_Walk
Config.RunAnimationId = 0 -- rbxassetid of R6_Run

-- Ground speed (studs/s) at which each animation plays at exactly the timing of the
-- reference video (walk cycle 1.000 s, run cycle 0.667 s). Playback speed is scaled
-- by currentSpeed / referenceSpeed so feet keep pace with the character.
Config.WalkReferenceSpeed = 16 -- Roblox default Humanoid.WalkSpeed
Config.RunReferenceSpeed = 24 -- = SprintSpeed, so sprinting plays the run at the video's timing

-- Built-in sprint: hold Left/Right Shift (or press the left stick on a gamepad) to run.
-- Set EnableSprintKey = false if your game already has its own sprint system.
Config.EnableSprintKey = true
Config.SprintSpeed = 24

-- Speed band selection. Above RunEnterSpeed the run plays; it keeps playing until the
-- speed drops below RunExitSpeed (hysteresis prevents flicker at the boundary).
Config.MinMoveSpeed = 0.75
Config.RunEnterSpeed = 20
Config.RunExitSpeed = 18.5

-- Clamp for the speed-scaled playback rate.
Config.MinPlaybackRate = 0.55
Config.MaxPlaybackRate = 1.6

-- Crossfade durations (seconds).
Config.StartFade = 0.15 -- idle -> moving
Config.StopFade = 0.2 -- moving -> idle
Config.SwitchFade = 0.25 -- walk <-> run (phase-synced)
Config.SuspendFade = 0.1 -- jump/fall/ragdoll/suppression

-- Set this attribute (boolean) to true on the character model from any existing
-- system (e.g. while a crash/ragdoll or a full-body throw is active) to fade the
-- locomotion animations out without touching that system's own animations.
Config.SuppressAttribute = "LocomotionSuppressed"

return Config
