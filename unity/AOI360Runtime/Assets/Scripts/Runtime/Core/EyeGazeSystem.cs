using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using VIVE.OpenXR;
using VIVE.OpenXR.EyeTracker;

namespace EyeGaze.Runtime.Core
{
    // This main module reads eye gaze data, performs the gaze raycast,
    // and delegates the result to the optional helper modules.
    public class EyeGazeSystem : MonoBehaviour
    {
        private enum EyeTrackingSource
        {
            None = 0,
            OpenXREyeGaze = 1,
            ViveEyeTracker = 2
        }

        [Header("Raycast")]
        // Maximum distance for the gaze raycast
        [SerializeField] private float maxDistance = 10f;

        // Layer mask to specify which objects can be detected by the gaze raycast
        [SerializeField] private LayerMask hitMask = ~0;

        [Header("Fallback Visual Fixation")]
        // Distance used to place a visual fixation point when gaze does not hit anything
        [SerializeField] private float fallbackFixationDistance = 3f;

        // Clamp the visual fixation distance so very far hits do not produce exaggerated depth
        [SerializeField] private bool clampVisualFixationDistance = false;

        // Maximum allowed distance for the visual fixation point when clamping is enabled
        [SerializeField] private float maxVisualFixationDistance = 5f;

        [Header("References")]
        // Camera used as reference (usually HMD / Main Camera)
        [SerializeField] private Camera referenceCamera;
        [SerializeField] private Transform trackingSpace;

        [Header("Input Source")]
        [SerializeField] private bool allowViveEyeTrackerFallback = true;
        [SerializeField] private bool logTrackingSourceChanges = true;

        [Header("Optional Modules")]
        // List of optional eye gaze modules to be driven by the system
        [SerializeField] private MonoBehaviour[] moduleBehaviours;

        // InputActions for eye gaze position, rotation and tracking state
        private InputAction gazePositionAction;
        private InputAction gazeRotationAction;
        private InputAction gazeTrackedAction;

        // Store the last valid gaze position and rotation
        private Vector3 lastValidPosition;
        private Quaternion lastValidRotation = Quaternion.identity;
        private bool hasValidGazePose;
        private EyeTrackingSource currentTrackingSource;
        private float lastLeftPupilDiameter = -1f;
        private float lastRightPupilDiameter = -1f;

        // Runtime list of valid modules implementing the common module interface
        private readonly List<IEyeGazeModule> modules = new();

        public Camera ReferenceCamera => referenceCamera;
        public bool HasValidGazePose => hasValidGazePose;
        public Vector3 LastValidPosition => lastValidPosition;
        public Quaternion LastValidRotation => lastValidRotation;
        public string CurrentTrackingSource => currentTrackingSource.ToString();
        public float LastLeftPupilDiameter => lastLeftPupilDiameter;
        public float LastRightPupilDiameter => lastRightPupilDiameter;
        public float MaxDistance => maxDistance;
        public LayerMask HitMask => hitMask;
        public float FallbackFixationDistance => fallbackFixationDistance;
        public bool ClampVisualFixationDistance => clampVisualFixationDistance;
        public float MaxVisualFixationDistance => maxVisualFixationDistance;

        // Initialize InputActions and modules
        private void Awake()
        {
            CreateInputActions();
            ResolveReferenceCamera();
            CacheModules();
            InitializeModules();
        }

        // Enable InputActions
        private void OnEnable()
        {
            gazePositionAction.Enable();
            gazeRotationAction.Enable();
            gazeTrackedAction.Enable();

            Debug.Log("[EyeGazeSystem] Devices activos:");
            foreach (var device in InputSystem.devices)
            {
                Debug.Log($"- {device.displayName} | {device.layout}");
            }
        }

        // Disable InputActions and clean state
        private void OnDisable()
        {
            gazePositionAction.Disable();
            gazeRotationAction.Disable();
            gazeTrackedAction.Disable();

            ResetAllModules();
        }

        // Main update loop
        private void Update()
        {
            ReadGazePose();

            if (!hasValidGazePose)
            {
                HandleInvalidTracking();
                return;
            }

            ProcessValidGaze();
        }

        // Create the InputActions used to read eye gaze data
        private void CreateInputActions()
        {
            gazePositionAction = new InputAction(
                name: "EyeGazePosition",
                type: InputActionType.Value,
                binding: "<EyeGaze>/pose/position"
            );

            gazeRotationAction = new InputAction(
                name: "EyeGazeRotation",
                type: InputActionType.Value,
                binding: "<EyeGaze>/pose/rotation"
            );

            gazeTrackedAction = new InputAction(
                name: "EyeGazeTracked",
                type: InputActionType.Button,
                binding: "<EyeGaze>/pose/isTracked"
            );
        }

        // Use main camera if none assigned
        private void ResolveReferenceCamera()
        {
            bool hasValidReferenceCamera = referenceCamera != null && referenceCamera.gameObject.activeInHierarchy;
            if (!hasValidReferenceCamera)
            {
                referenceCamera = ResolveActiveCamera();
            }

            if ((trackingSpace == null || !trackingSpace.gameObject.activeInHierarchy) &&
                referenceCamera != null &&
                referenceCamera.transform.parent != null)
            {
                trackingSpace = referenceCamera.transform.parent;
            }
        }

        private static Camera ResolveActiveCamera()
        {
            Camera mainCamera = Camera.main;
            if (mainCamera != null && mainCamera.gameObject.activeInHierarchy)
            {
                return mainCamera;
            }

            return FindFirstObjectByType<Camera>();
        }

        // Cache all assigned MonoBehaviours that implement IEyeGazeModule
        private void CacheModules()
        {
            modules.Clear();

            if (moduleBehaviours == null)
            {
                return;
            }

            foreach (MonoBehaviour behaviour in moduleBehaviours)
            {
                if (behaviour == null)
                {
                    continue;
                }

                if (behaviour is IEyeGazeModule module)
                {
                    modules.Add(module);
                }
                else
                {
                    Debug.LogWarning(
                        $"[EYE GAZE SYSTEM] Assigned behaviour '{behaviour.name}' does not implement IEyeGazeModule.",
                        behaviour
                    );
                }
            }
        }

        // Initialize all optional helper modules
        private void InitializeModules()
        {
            foreach (IEyeGazeModule module in modules)
            {
                module.Initialize(this);
            }
        }

        // Read the current eye gaze pose from Input System
        private void ReadGazePose()
        {
            Vector3 gazePosition = gazePositionAction.ReadValue<Vector3>();
            Quaternion gazeRotation = gazeRotationAction.ReadValue<Quaternion>();
            float trackedValue = gazeTrackedAction.ReadValue<float>();

            bool isTracked = trackedValue > 0.5f;
            if (isTracked)
            {
                SetTrackingState(gazePosition, gazeRotation, EyeTrackingSource.OpenXREyeGaze);
            }
            // Keep the standard OpenXR path as the primary source, but fall back to
            // the HTC eye-tracker extension when the generic <EyeGaze> device is unavailable.
            else if (!TryReadViveEyeTrackerPose(out Vector3 vivePosition, out Quaternion viveRotation))
            {
                hasValidGazePose = false;
                currentTrackingSource = EyeTrackingSource.None;
                lastLeftPupilDiameter = -1f;
                lastRightPupilDiameter = -1f;
            }
            else
            {
                SetTrackingState(vivePosition, viveRotation, EyeTrackingSource.ViveEyeTracker);
            }

            hasValidGazePose = currentTrackingSource != EyeTrackingSource.None;

            if (Time.frameCount % 30 == 0)
            {
                Debug.Log(
                    $"[EyeGazeSystem] tracked={hasValidGazePose} | source={currentTrackingSource} " +
                    $"pos={lastValidPosition} rot={lastValidRotation.eulerAngles}"
                );
            }
        }

        private void SetTrackingState(Vector3 gazePosition, Quaternion gazeRotation, EyeTrackingSource source)
        {
            hasValidGazePose = true;
            // OpenXR poses can be delivered relative to the XR rig space, so convert them
            // into world space once here before any downstream modules consume them.
            lastValidPosition = TransformTrackingPosePosition(gazePosition);
            lastValidRotation = TransformTrackingPoseRotation(gazeRotation);

            if (logTrackingSourceChanges && currentTrackingSource != source)
            {
                Debug.Log($"[EyeGazeSystem] Tracking source -> {source}", this);
            }

            currentTrackingSource = source;
        }

        private Vector3 TransformTrackingPosePosition(Vector3 trackingPosition)
        {
            if (trackingSpace != null)
            {
                return trackingSpace.TransformPoint(trackingPosition);
            }

            return trackingPosition;
        }

        private Quaternion TransformTrackingPoseRotation(Quaternion trackingRotation)
        {
            if (trackingSpace != null)
            {
                return trackingSpace.rotation * trackingRotation;
            }

            return trackingRotation;
        }

        private bool TryReadViveEyeTrackerPose(out Vector3 gazePosition, out Quaternion gazeRotation)
        {
            gazePosition = Vector3.zero;
            gazeRotation = Quaternion.identity;

            if (!allowViveEyeTrackerFallback)
            {
                return false;
            }

            if (!XR_HTC_eye_tracker.Interop.GetEyeGazeData(out XrSingleEyeGazeDataHTC[] eyeGazes) || eyeGazes == null || eyeGazes.Length < 2)
            {
                return false;
            }

            XrSingleEyeGazeDataHTC leftEye = eyeGazes[(int)XrEyePositionHTC.XR_EYE_POSITION_LEFT_HTC];
            XrSingleEyeGazeDataHTC rightEye = eyeGazes[(int)XrEyePositionHTC.XR_EYE_POSITION_RIGHT_HTC];

            bool leftValid = leftEye.isValid;
            bool rightValid = rightEye.isValid;

            if (!leftValid && !rightValid)
            {
                return false;
            }

            Vector3 origin;
            Vector3 direction;

            // When both eyes are valid, approximate a binocular gaze ray by averaging the eye
            // origins and forward directions. This keeps the rest of the runtime on one ray.
            if (leftValid && rightValid)
            {
                Vector3 leftOrigin = leftEye.gazePose.position.ToUnityVector();
                Vector3 rightOrigin = rightEye.gazePose.position.ToUnityVector();
                Vector3 leftDirection = leftEye.gazePose.orientation.ToUnityQuaternion() * Vector3.forward;
                Vector3 rightDirection = rightEye.gazePose.orientation.ToUnityQuaternion() * Vector3.forward;

                origin = (leftOrigin + rightOrigin) * 0.5f;
                direction = (leftDirection + rightDirection).normalized;
            }
            else if (rightValid)
            {
                origin = rightEye.gazePose.position.ToUnityVector();
                direction = (rightEye.gazePose.orientation.ToUnityQuaternion() * Vector3.forward).normalized;
            }
            else
            {
                origin = leftEye.gazePose.position.ToUnityVector();
                direction = (leftEye.gazePose.orientation.ToUnityQuaternion() * Vector3.forward).normalized;
            }

            if (direction.sqrMagnitude <= 0.0001f)
            {
                return false;
            }

            gazePosition = origin;
            gazeRotation = Quaternion.LookRotation(direction, Vector3.up);

            UpdateVivePupilData();
            return true;
        }

        private void UpdateVivePupilData()
        {
            lastLeftPupilDiameter = -1f;
            lastRightPupilDiameter = -1f;

            if (!XR_HTC_eye_tracker.Interop.GetEyePupilData(out XrSingleEyePupilDataHTC[] pupils) || pupils == null || pupils.Length < 2)
            {
                return;
            }

            XrSingleEyePupilDataHTC leftPupil = pupils[(int)XrEyePositionHTC.XR_EYE_POSITION_LEFT_HTC];
            XrSingleEyePupilDataHTC rightPupil = pupils[(int)XrEyePositionHTC.XR_EYE_POSITION_RIGHT_HTC];

            if (leftPupil.isDiameterValid)
            {
                lastLeftPupilDiameter = leftPupil.pupilDiameter;
            }

            if (rightPupil.isDiameterValid)
            {
                lastRightPupilDiameter = rightPupil.pupilDiameter;
            }
        }

        // Reset modules when the eye gaze is not currently tracked
        private void HandleInvalidTracking()
        {
            foreach (IEyeGazeModule module in modules)
            {
                module.HandleTrackingLost(Time.deltaTime);
            }
        }

        // Process the current valid eye gaze pose
        private void ProcessValidGaze()
        {
            Vector3 direction = lastValidRotation * Vector3.forward;
            Ray ray = new Ray(lastValidPosition, direction);

            bool hasHit = Physics.Raycast(ray, out RaycastHit hitInfo, maxDistance, hitMask);
            bool hasPhysicsHit = hasHit;

            GameObject hitObject = hasHit ? hitInfo.collider.gameObject : null;

            Vector3 hitPoint = hasHit
                ? hitInfo.point
                : lastValidPosition + direction * fallbackFixationDistance;

            Vector3 hitNormal = hasHit
                ? hitInfo.normal
                : -direction;

            Vector3 visualFixationPoint;
            Vector3 visualFixationNormal;
            bool isFallbackFixationPoint;

            if (hasPhysicsHit)
            {
                visualFixationPoint = hitInfo.point;
                visualFixationNormal = hitInfo.normal.sqrMagnitude > 0f
                    ? hitInfo.normal.normalized
                    : -direction;
                isFallbackFixationPoint = false;

                if (clampVisualFixationDistance)
                {
                    float hitDistance = Vector3.Distance(lastValidPosition, visualFixationPoint);

                    if (hitDistance > maxVisualFixationDistance)
                    {
                        visualFixationPoint = lastValidPosition + direction * maxVisualFixationDistance;
                        visualFixationNormal = -direction;
                        isFallbackFixationPoint = true;
                    }
                }
            }
            else
            {
                visualFixationPoint = lastValidPosition + direction * fallbackFixationDistance;
                visualFixationNormal = -direction;
                isFallbackFixationPoint = true;
            }

            Vector3 rayEndPoint = hasPhysicsHit
                ? visualFixationPoint
                : lastValidPosition + direction * maxDistance;

            EyeGazeFrameData frameData = new EyeGazeFrameData(
                isTracked: true,
                gazeOrigin: lastValidPosition,
                gazeRotation: lastValidRotation,
                gazeDirection: direction,
                gazeRay: ray,
                hasHit: hasHit,
                hitInfo: hitInfo,
                hitObject: hitObject,
                hitPoint: hitPoint,
                hitNormal: hitNormal,
                rayEndPoint: rayEndPoint,
                deltaTime: Time.deltaTime,
                hasPhysicsHit: hasPhysicsHit,
                visualFixationPoint: visualFixationPoint,
                visualFixationNormal: visualFixationNormal,
                isFallbackFixationPoint: isFallbackFixationPoint
            );

            foreach (IEyeGazeModule module in modules)
            {
                module.ProcessFrame(frameData);
            }
        }

        // Reset the internal state of all optional modules
        private void ResetAllModules()
        {
            foreach (IEyeGazeModule module in modules)
            {
                module.ResetModuleState();
            }
        }
    }
}
