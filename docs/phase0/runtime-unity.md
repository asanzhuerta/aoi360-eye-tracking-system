# Unity Runtime - Phase 0

## Active scene

The production scene for Phase 0 is:

- `Assets/Scenes/Phase0_360Playback_VR_sampleRIG.unity`

`Assets/Scenes/Phase0_360Playback_VR.unity` is now treated as a legacy scene and is no longer part of the normal runtime path.

## Runtime flow

The intended headset flow is:

1. `Initial_Scene` shows the runtime-generated stimulus list.
   - the selection canvas stays fixed in the scene instead of following the current head direction
2. Selecting a stimulus stores the experiment session state and loads `Phase0_360Playback_VR_sampleRIG`.
3. As soon as the experiment scene loads, the runtime must:
   - start a `5 -> 0` countdown overlay
   - show a black 360 background while the selected render texture is still being prepared
   - prepare the selected 360 video
   - resolve and preload the AOI manifest plus the first AOI frame
   - initialize eye-gaze, spherical mapping, fixation visualization, and CSV logging
4. The video starts only after the countdown is complete and playback has been explicitly unlocked by `ExperimentPlaybackFlowController`.
5. Pressing the right controller `A` button ends the experiment, stops the video, exports the CSV once, shows `Experimento finalizado`, and returns to `Initial_Scene` after `5` seconds.
6. If the non-looping video reaches its natural end first, the runtime must close the experiment with the same completion flow and return to `Initial_Scene`.

## Runtime injection

Some Phase 0 modules are authored directly in `Phase0_360Playback_VR_sampleRIG`, but others are injected at runtime.

Scene-authored modules:
- `VideoPlayback`
- `DataRecorder`
- `AOILookup`
- `GazeProviderBridge`
- `SphericalMapper`
- `EyeGazeSystem`
- `EyeGazeDebugVisualizer`
- `Phase0Bootstrap`

Runtime-injected modules:
- `ExperimentPlaybackFlowController`
- `AOISequenceRuntimeLoader`
- `RuntimeControllerPoseBridge`

The runtime-injected modules must subscribe to `SceneManager.sceneLoaded` because relying only on `RuntimeInitializeOnLoadMethod(AfterSceneLoad)` is not sufficient for later scene transitions triggered from `Initial_Scene`.
They must also resolve existing instances per loaded scene instead of globally, otherwise a bridge from the outgoing scene can block the bridge that the new scene needs for controllers, hands, and UI rays.

## Runtime modules

### Video playback

`VideoPlayback` prepares and plays a 360 video from the selected stimulus path.

Responsibilities:
- drive a runtime 360 sphere output that uses the same equirectangular calibration as the AOI overlay
- force the skybox into latitude-longitude panoramic mode
- clear the render texture to black before each new preparation cycle
- prepare the video before the experiment starts
- expose current frame and time
- keep playback deterministic for logging
- wait for the playback lock to be released before starting

### Eye tracking

`EyeGazeSystem` is the runtime entry point for gaze data.

Current behavior:
- reads `<EyeGaze>/pose/position`
- reads `<EyeGaze>/pose/rotation`
- reads `<EyeGaze>/pose/isTracked`
- falls back to HTC VIVE eye tracker API when the standard OpenXR path is not valid
- exposes the active tracking source
- exposes pupil diameters when HTC data is available

Tracking sources:
- `OpenXREyeGaze`
- `ViveEyeTracker`
- `None`

### Spherical mapping

`GazeProviderBridge` forwards the world-space gaze direction into `SphericalMapper`.

`SphericalMapper` converts gaze direction into:
- azimuth
- elevation
- UV coordinates on the equirectangular map

Calibration note:
- `Phase0_360Playback_VR_sampleRIG` currently uses the same editor calibration that the legacy VR scene used successfully: `yawOffsetDegrees = 180`, `verticalOffsetDegrees = 15`, `flipVertically = 1`

### AOI lookup

`AOILookup` resolves AOI hits from the AOI texture using the current UV.

Supported modes:
- `MetadataExactColor`
- `Grayscale8Bit`
- `LegacyDominantRgb`

For the future pipeline, `MetadataExactColor` is the preferred mode.

### AOI sequence loading

`AOISequenceRuntimeLoader` is the runtime boundary between offline AOI exports and the experiment scene.

Responsibilities:
- load the selected manifest
- bind AOI metadata into `AOILookup`
- preload the first AOI frame before playback starts
- stream later AOI keyframes in sync with the current video frame

### AOI overlay

`Phase0Bootstrap` creates a runtime sphere inside the 360 environment and renders a semi-transparent AOI overlay on top of the video.

Behavior:
- invisible background for non-AOI pixels
- regular opacity for AOIs

### Controller and UI pose bridge

`RuntimeControllerPoseBridge` is responsible for keeping `LeftHand`, `RightHand`, `LeftRay`, and `RightRay` alive across both `Initial_Scene` and `Phase0_360Playback_VR_sampleRIG`.

Current expectations:
- when changing scenes, the new scene must always receive a fresh bridge instance
- the bridge must attach to the existing `VRSRig_withRay` anchors instead of inventing a parallel hierarchy
- controller visuals and rays should remain visible even if `isTracked` is flaky, as long as valid OpenXR pose data is still arriving

`ExperimentSelectionSceneController` also keeps the menu canvas transform stabilized in world space after scene returns so that the menu does not drift with the current headset orientation.
- boosted opacity for the currently focused AOI

### Fixation visualization

`EyeGazeDebugVisualizer` includes a lightweight fixation detector for runtime debugging.

Current behavior:
- fixation commit interval: `250 ms`
- angular stability threshold: approximately `3 degrees`
- visible hit marker for the active fixation
- persistent fixation trail
- trail capped to `10` markers
- nearby repeated fixations merge into the latest trail marker instead of creating duplicates

### Logging

`DataRecorder` exports fixation-based CSV rows instead of raw per-frame samples.

Fields currently exported:
- participant and session identifiers
- video identifier
- fixation timestamp in milliseconds
- current video frame
- gaze origin
- gaze direction
- spherical angles
- UV coordinates
- AOI id
- AOI confidence
- left and right pupil diameter when available
- validity flag

Manual termination behavior:
- stop the active recording session
- export the CSV exactly once
- keep the exported file path available for the completion UI and logs
- return to `Initial_Scene` after the in-headset completion message has been visible for `5` seconds

## Why fixation-based logging

Phase 0 uses fixation commits instead of full-rate raw streaming because the immediate goal is to validate:
- AOI alignment
- fixation timing
- experimental flow
- downstream analytics contracts

Raw high-frequency sample logging can still be added later if the study protocol needs it.

## Known warnings

The warning `The referenced script (Unknown) on this Behaviour is missing!` does not currently point to the video startup path.

Current repository evidence suggests it comes from missing serialized overrides inside:

- `unity/AOI360Runtime/Assets/Settings/DefaultVolumeProfile.asset`

It should still be cleaned up in Unity, but it is separate from the countdown/video unlock issue.
