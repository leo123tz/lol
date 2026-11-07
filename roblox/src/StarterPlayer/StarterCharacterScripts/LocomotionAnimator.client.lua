--!strict
-- LocomotionAnimator (LocalScript, StarterCharacterScripts)
--
-- Plays the reference-matched R6 walk and run cycles on the local player's character.
--
-- * Replication: tracks are loaded on the Humanoid's Animator, which the server creates
--   for every player character. Animations played on it by the owning client replicate
--   to the server and all other clients automatically. No server script is required.
-- * Respawn: this script lives in StarterCharacterScripts, so a fresh copy runs for
--   every new character; all state and connections die with the old character.
-- * Coexistence: the tracks run at Movement priority. The default "Animate" script
--   keeps handling idle/jump/fall/climb/swim/sit (Core/Idle priority), and any Action-
--   priority animation from other systems (e.g. throwing) still overrides these tracks.
-- * Suppression: locomotion fades out whenever the Humanoid leaves the Running state
--   (jumping, freefall, ragdoll, physics, seated, dead...) or while the character has
--   the boolean attribute Config.SuppressAttribute set to true.

local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local KeyframeSequenceProvider = game:GetService("KeyframeSequenceProvider")

local LocomotionFolder = ReplicatedStorage:WaitForChild("LocomotionAnimation")
local Config = require(LocomotionFolder:WaitForChild("Config") :: ModuleScript)

local character = script.Parent :: Model
local humanoid = character:WaitForChild("Humanoid") :: Humanoid
local rootPart = character:WaitForChild("HumanoidRootPart") :: BasePart

if humanoid.RigType ~= Enum.HumanoidRigType.R6 then
	warn("[LocomotionAnimator] Character is not R6; locomotion animations are R6-only. Disabled.")
	return
end

local animator = humanoid:WaitForChild("Animator") :: Animator

-- Resolve an animation id: published asset id, or (Studio only) a registered
-- KeyframeSequence from ReplicatedStorage.LocomotionAnimation.Sources.
local function resolveAnimationId(assetId: number, sourceName: string): string?
	if assetId and assetId > 0 then
		return "rbxassetid://" .. tostring(assetId)
	end
	if RunService:IsStudio() then
		local sources = LocomotionFolder:FindFirstChild("Sources")
		local sequence = sources and sources:FindFirstChild(sourceName)
		if sequence and sequence:IsA("KeyframeSequence") then
			warn(("[LocomotionAnimator] %s has no published id; using a Studio-only temporary id."):format(sourceName))
			return KeyframeSequenceProvider:RegisterKeyframeSequence(sequence)
		end
	end
	warn(("[LocomotionAnimator] No animation id for %s (set it in LocomotionAnimation.Config)."):format(sourceName))
	return nil
end

local function loadTrack(assetId: number, sourceName: string): AnimationTrack?
	local id = resolveAnimationId(assetId, sourceName)
	if not id then
		return nil
	end
	local animation = Instance.new("Animation")
	animation.Name = sourceName
	animation.AnimationId = id
	local track = animator:LoadAnimation(animation)
	track.Priority = Enum.AnimationPriority.Movement
	track.Looped = true
	return track
end

local walkTrack = loadTrack(Config.WalkAnimationId, "R6_Walk")
local runTrack = loadTrack(Config.RunAnimationId, "R6_Run")
if not walkTrack or not runTrack then
	-- Leave the default Animate script fully in charge rather than half-working.
	return
end

type Mode = "none" | "walk" | "run"
local tracks: { [Mode]: AnimationTrack } = { walk = walkTrack :: AnimationTrack, run = runTrack :: AnimationTrack }
local referenceSpeed: { [Mode]: number } = { walk = Config.WalkReferenceSpeed, run = Config.RunReferenceSpeed }

local LOCOMOTION_STATES: { [Enum.HumanoidStateType]: boolean } = {
	[Enum.HumanoidStateType.Running] = true,
	[Enum.HumanoidStateType.RunningNoPhysics] = true,
	[Enum.HumanoidStateType.Landed] = true,
}

local currentMode: Mode = "none"
local smoothedSpeed = 0

local function phaseOf(track: AnimationTrack): number?
	if track.IsPlaying and track.Length > 0 then
		return (track.TimePosition % track.Length) / track.Length
	end
	return nil
end

local function setMode(newMode: Mode, fade: number)
	if newMode == currentMode then
		return
	end
	local oldTrack = if currentMode ~= "none" then tracks[currentMode] else nil
	if newMode == "none" then
		if oldTrack then
			oldTrack:Stop(fade)
		end
	else
		local newTrack = tracks[newMode]
		-- Both cycles start on the same foot contact, so carrying the normalized phase
		-- across a walk<->run switch keeps the legs continuous during the crossfade.
		local phase = if oldTrack then phaseOf(oldTrack) else nil
		newTrack:Play(fade, 1, 1)
		if phase and newTrack.Length > 0 then
			newTrack.TimePosition = phase * newTrack.Length
		end
		if oldTrack then
			oldTrack:Stop(fade)
		end
	end
	currentMode = newMode
end

local function horizontalSpeed(): number
	local v = rootPart.AssemblyLinearVelocity
	return Vector3.new(v.X, 0, v.Z).Magnitude
end

local function update(dt: number)
	-- Exponential smoothing (~0.08 s) removes single-frame physics spikes.
	local alpha = 1 - math.exp(-dt / 0.08)
	smoothedSpeed += (horizontalSpeed() - smoothedSpeed) * alpha

	local suppressed = character:GetAttribute(Config.SuppressAttribute) == true
	local grounded = LOCOMOTION_STATES[humanoid:GetState()] == true
		and humanoid.FloorMaterial ~= Enum.Material.Air

	if suppressed or not grounded or humanoid.Health <= 0 then
		setMode("none", Config.SuspendFade)
		return
	end

	local target: Mode
	if smoothedSpeed < Config.MinMoveSpeed then
		target = "none"
	elseif currentMode == "run" then
		target = if smoothedSpeed >= Config.RunExitSpeed then "run" else "walk"
	else
		target = if smoothedSpeed >= Config.RunEnterSpeed then "run" else "walk"
	end

	if target == "none" then
		setMode("none", Config.StopFade)
	elseif currentMode == "none" then
		setMode(target, Config.StartFade)
	else
		setMode(target, Config.SwitchFade)
	end

	if currentMode ~= "none" then
		local rate = smoothedSpeed / referenceSpeed[currentMode]
		tracks[currentMode]:AdjustSpeed(math.clamp(rate, Config.MinPlaybackRate, Config.MaxPlaybackRate))
	end
end

local heartbeat = RunService.Heartbeat:Connect(update)

local function shutdown()
	heartbeat:Disconnect()
	for _, track in tracks do
		track:Stop(0)
		track:Destroy()
	end
end

humanoid.Died:Once(function()
	setMode("none", Config.SuspendFade)
end)
character.Destroying:Once(shutdown)
