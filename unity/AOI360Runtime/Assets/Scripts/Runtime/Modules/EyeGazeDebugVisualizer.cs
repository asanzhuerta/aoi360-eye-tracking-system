using AOI360.Runtime.AOI;
using AOI360.Runtime.Experiment;
using AOI360.Runtime.Mapping;
using EyeGaze.Runtime.Core;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EyeGaze.Runtime.Modules
{
    // Debug visualization plus a lightweight fixation detector for the Phase 0 runtime.
    public class EyeGazeDebugVisualizer : EyeGazeModuleBase
    {
        [Header("Debug")]
        [SerializeField] private bool enableDebugRay = false;
        [SerializeField] private LineRenderer debugLineRenderer;
        [SerializeField] private Color debugRayColor = Color.red;
        [SerializeField] private LineRenderer debugCameraLineRenderer;
        [SerializeField] private Color debugCameraRayColor = Color.blue;
        [SerializeField] private LineRenderer debugOffsetLineRenderer;
        [SerializeField] private Color debugOffsetLineColor = Color.white;

        [Header("Fallback")]
        [SerializeField] private bool showFallbackWhenTrackingLost = true;

        [Header("360 Debug")]
        [SerializeField] private SphericalMapper sphericalMapper;
        [SerializeField] private AOILookup aoiLookup;
        [SerializeField] private Transform sphereCenter;
        [SerializeField] private float sphereRadius = 5f;
        [SerializeField] private Transform hitMarker;
        [SerializeField] private bool enableHitMarker = true;
        [SerializeField] private bool enableAOILogging = true;

        [Header("Fixations")]
        [SerializeField] private float fixationCommitIntervalSeconds = 0.25f;
        [SerializeField] private float fixationAngularThresholdDegrees = 3f;
        [SerializeField] private float fixationMarkerBaseScale = 0.14f;
        [SerializeField] private float fixationMarkerScaleGrowth = 0.24f;
        [SerializeField] private float fixationMarkerMaxScale = 0.34f;
        [SerializeField] private int maxTrailMarkers = 10;
        [SerializeField] private float trailLineWidth = 0.012f;
        [SerializeField] private float trailMarkerDepthOffset = 0.02f;
        [SerializeField] private float trailMergeDistance = 0.18f;

        [Header("Logs")]
        [SerializeField] private bool enableDebugLogs = false;
        [SerializeField] private int debugLogEveryNFrames = 60;

        private Camera referenceCamera;
        private float maxDistance;
        private Renderer hitMarkerRenderer;
        private Transform hitMarkerVisual;
        private Material runtimeHitMarkerMaterial;
        private Texture hitMarkerTexture;
        private Vector3 hitMarkerInitialScale = Vector3.one;
        private float fixationCandidateStartTimestampMs;
        private Transform trailRoot;
        private Material runtimeTrailLineMaterial;
        private readonly Queue<GameObject> committedMarkerObjects = new Queue<GameObject>();
        private readonly Queue<GameObject> committedLineObjects = new Queue<GameObject>();

        private bool fixationCandidateValid;
        private Vector3 fixationCandidateDirection = Vector3.forward;
        private Vector3 fixationAnchorPoint = Vector3.zero;
        private Vector3 fixationAnchorNormal = Vector3.forward;
        private float fixationCandidateDuration;
        private int fixationCommitCount;
        private int fixationSequence;

        public bool HasCommittedFixation { get; private set; }
        public int LatestCommittedFixationSequence { get; private set; }
        public float LatestCommittedFixationTimestampMs { get; private set; }
        public Vector3 LatestCommittedFixationPoint { get; private set; }
        public Vector3 LatestCommittedFixationNormal { get; private set; }
        public Vector2 LatestCommittedFixationUv { get; private set; }
        public int LatestCommittedFixationAoiId { get; private set; }
        public float LatestCommittedFixationConfidence { get; private set; }
        public int ActiveFixationCommitCount => fixationCommitCount;

        public override void Initialize(EyeGazeSystem systemReference)
        {
            base.Initialize(systemReference);

            referenceCamera = system.ReferenceCamera;
            maxDistance = system.MaxDistance;

            NormalizeDebugSettings();
            ConfigureAllLineRenderers();
            CacheHitMarkerRenderer();
            EnsureTrailRoot();
            ResetFixationState();
            SetHitMarkerEnabled(false);
        }

        public override void ProcessFrame(EyeGazeFrameData frameData)
        {
            if (ExperimentSessionState.IsPlaybackStartLocked)
            {
                ResetModuleState();
                return;
            }

            UpdateVisualization(frameData.GazeOrigin, frameData.GazeDirection, frameData.RayEndPoint, frameData.DeltaTime);
        }

        public override void HandleTrackingLost(float deltaTime)
        {
            if (ExperimentSessionState.IsPlaybackStartLocked)
            {
                ResetModuleState();
                return;
            }

            ResetFixationState();

            if (!enableDebugRay)
            {
                DisableAll();
                return;
            }

            if (showFallbackWhenTrackingLost && referenceCamera != null)
            {
                Vector3 fallbackOrigin = referenceCamera.transform.position;
                Vector3 fallbackDirection = referenceCamera.transform.forward.normalized;
                Vector3 fallbackEndPoint = fallbackOrigin + fallbackDirection * maxDistance;

                DrawGazeRay(fallbackOrigin, fallbackEndPoint);
                DrawReferenceCameraRay();
                DrawCameraToGazeOffset(fallbackOrigin);
                SetHitMarkerEnabled(false);
                return;
            }

            DisableAll();
        }

        public override void ResetModuleState()
        {
            ResetFixationState();
            ClearTrail();
            DisableAll();
        }

        public void DisableAll()
        {
            SetLineRendererEnabled(debugLineRenderer, false);
            SetLineRendererEnabled(debugCameraLineRenderer, false);
            SetLineRendererEnabled(debugOffsetLineRenderer, false);
            SetHitMarkerEnabled(false);
            SetTrailVisible(false);
        }

        public void UpdateVisualization(Vector3 gazeOrigin, Vector3 gazeDirection, Vector3 gazeEndPoint, float deltaTime)
        {
            if (!enableDebugRay)
            {
                DisableAll();
                return;
            }

            DrawGazeRay(gazeOrigin, gazeEndPoint);
            DrawReferenceCameraRay();
            DrawCameraToGazeOffset(gazeOrigin);
            UpdateSphereHitMarker(gazeOrigin, gazeDirection, deltaTime);
            SetTrailVisible(true);
            WritePeriodicDebugLog(gazeOrigin, gazeDirection);
        }

        private void ConfigureAllLineRenderers()
        {
            EyeGazeUtils.ConfigureLineRenderer(debugLineRenderer, debugRayColor, enableDebugRay);
            EyeGazeUtils.ConfigureLineRenderer(debugCameraLineRenderer, debugCameraRayColor, enableDebugRay);
            EyeGazeUtils.ConfigureLineRenderer(debugOffsetLineRenderer, debugOffsetLineColor, enableDebugRay);
        }

        private void NormalizeDebugSettings()
        {
            fixationAngularThresholdDegrees = Mathf.Max(fixationAngularThresholdDegrees, 3f);
            fixationMarkerBaseScale = Mathf.Max(fixationMarkerBaseScale, 0.14f);
            fixationMarkerScaleGrowth = Mathf.Max(fixationMarkerScaleGrowth, 0.24f);
            fixationMarkerMaxScale = Mathf.Max(fixationMarkerMaxScale, 0.34f);
            maxTrailMarkers = Mathf.Max(maxTrailMarkers, 10);
            trailLineWidth = Mathf.Max(trailLineWidth, 0.012f);
            trailMarkerDepthOffset = Mathf.Max(trailMarkerDepthOffset, 0.02f);
            trailMergeDistance = Mathf.Max(trailMergeDistance, 0.08f);
        }

        private void CacheHitMarkerRenderer()
        {
            if (hitMarker == null)
            {
                return;
            }

            hitMarkerRenderer = hitMarker.GetComponentInChildren<Renderer>(true);

            if (hitMarkerRenderer == null)
            {
                return;
            }

            hitMarkerVisual = hitMarkerRenderer.transform;
            hitMarkerInitialScale = hitMarkerVisual.localScale;
            hitMarkerTexture = hitMarkerRenderer.sharedMaterial != null
                ? hitMarkerRenderer.sharedMaterial.mainTexture
                : null;
            hitMarkerVisual.localPosition = new Vector3(0f, 0f, -0.01f);

            Shader markerShader = ResolveTransparentShader();
            if (markerShader == null)
            {
                Debug.LogWarning("[EyeGazeDebugVisualizer] Could not find a transparent runtime shader for hit markers.");
                return;
            }

            runtimeHitMarkerMaterial = new Material(markerShader);
            runtimeHitMarkerMaterial.name = "Runtime_HitMarker";
            ConfigureTransparentMaterial(runtimeHitMarkerMaterial, hitMarkerTexture, Color.white);
            hitMarkerRenderer.material = runtimeHitMarkerMaterial;
            hitMarkerRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            hitMarkerRenderer.receiveShadows = false;
        }

        private void DrawGazeRay(Vector3 gazeOrigin, Vector3 gazeEndPoint)
        {
            if (debugLineRenderer == null)
            {
                return;
            }

            debugLineRenderer.enabled = true;
            debugLineRenderer.positionCount = 2;
            debugLineRenderer.SetPosition(0, gazeOrigin);
            debugLineRenderer.SetPosition(1, gazeEndPoint);
        }

        private void DrawReferenceCameraRay()
        {
            if (debugCameraLineRenderer == null || referenceCamera == null)
            {
                return;
            }

            Vector3 cameraStart = referenceCamera.transform.position;
            Vector3 cameraEnd = cameraStart + referenceCamera.transform.forward * maxDistance;

            debugCameraLineRenderer.enabled = true;
            debugCameraLineRenderer.positionCount = 2;
            debugCameraLineRenderer.SetPosition(0, cameraStart);
            debugCameraLineRenderer.SetPosition(1, cameraEnd);
        }

        private void DrawCameraToGazeOffset(Vector3 gazeOrigin)
        {
            if (debugOffsetLineRenderer == null || referenceCamera == null)
            {
                return;
            }

            debugOffsetLineRenderer.enabled = true;
            debugOffsetLineRenderer.positionCount = 2;
            debugOffsetLineRenderer.SetPosition(0, referenceCamera.transform.position);
            debugOffsetLineRenderer.SetPosition(1, gazeOrigin);
        }

        private void UpdateSphereHitMarker(Vector3 gazeOrigin, Vector3 gazeDirection, float deltaTime)
        {
            if (!enableHitMarker || sphereCenter == null || hitMarker == null)
            {
                SetHitMarkerEnabled(false);
                return;
            }

            if (!TryIntersectRaySphere(
                gazeOrigin,
                gazeDirection.normalized,
                sphereCenter.position,
                sphereRadius,
                out Vector3 hitPoint))
            {
                ResetFixationState();
                SetHitMarkerEnabled(false);
                return;
            }

            Vector3 outwardNormal = (hitPoint - sphereCenter.position).normalized;
            Vector3 inwardDirection = -outwardNormal;
            UpdateFixationState(hitPoint, outwardNormal, inwardDirection, deltaTime);
        }

        private void UpdateFixationState(Vector3 hitPoint, Vector3 outwardNormal, Vector3 inwardDirection, float deltaTime)
        {
            if (!fixationCandidateValid)
            {
                fixationCandidateValid = true;
                fixationCandidateDirection = inwardDirection;
                fixationAnchorPoint = hitPoint;
                fixationAnchorNormal = outwardNormal;
                fixationCandidateStartTimestampMs = Time.time * 1000f;
                fixationCandidateDuration = deltaTime;
                fixationCommitCount = 0;
                SetHitMarkerEnabled(false);
                return;
            }

            float angularDelta = Vector3.Angle(fixationCandidateDirection, inwardDirection);
            if (angularDelta > fixationAngularThresholdDegrees)
            {
                fixationCandidateDirection = inwardDirection;
                fixationAnchorPoint = hitPoint;
                fixationAnchorNormal = outwardNormal;
                fixationCandidateStartTimestampMs = Time.time * 1000f;
                fixationCandidateDuration = deltaTime;
                fixationCommitCount = 0;
                SetHitMarkerEnabled(false);
                return;
            }

            fixationCandidateDuration += deltaTime;
            // A fixation is treated as a sequence of 250 ms commits so the visualization and
            // exported runtime data follow the same temporal unit.
            int targetCommitCount = Mathf.FloorToInt(fixationCandidateDuration / fixationCommitIntervalSeconds);
            while (targetCommitCount > fixationCommitCount)
            {
                CommitFixation();
            }

            if (fixationCommitCount <= 0)
            {
                SetHitMarkerEnabled(false);
                return;
            }

            SetHitMarkerEnabled(true);
            hitMarker.position = fixationAnchorPoint - (fixationAnchorNormal * trailMarkerDepthOffset);
            hitMarker.rotation = Quaternion.LookRotation(fixationAnchorNormal);

            float scaleMultiplier = 1f + (fixationCommitCount - 1) * fixationMarkerScaleGrowth;
            float clampedScale = Mathf.Min(fixationMarkerBaseScale * scaleMultiplier, fixationMarkerMaxScale);
            if (hitMarkerVisual != null)
            {
                hitMarkerVisual.localScale = new Vector3(clampedScale, clampedScale, clampedScale);
            }

            if (runtimeHitMarkerMaterial != null)
            {
                runtimeHitMarkerMaterial.color = ResolveFixationColor();
            }
        }

        private void CommitFixation()
        {
            fixationCommitCount++;
            fixationSequence++;
            HasCommittedFixation = true;
            LatestCommittedFixationSequence = fixationSequence;
            LatestCommittedFixationTimestampMs = fixationCandidateStartTimestampMs + (fixationCommitCount * fixationCommitIntervalSeconds * 1000f);
            LatestCommittedFixationPoint = fixationAnchorPoint;
            LatestCommittedFixationNormal = fixationAnchorNormal;
            LatestCommittedFixationUv = sphericalMapper != null ? sphericalMapper.CurrentUV : Vector2.zero;
            LatestCommittedFixationAoiId = aoiLookup != null ? aoiLookup.CurrentAOIId : 0;
            LatestCommittedFixationConfidence = aoiLookup != null ? aoiLookup.CurrentAOIConfidence : 0f;
            AppendCommittedTrailMarker();
        }

        private Color ResolveFixationColor()
        {
            if (aoiLookup == null)
            {
                return Color.white;
            }

            Color baseColor = aoiLookup.CurrentAOIId > 0 ? aoiLookup.CurrentAOIColor : Color.white;
            baseColor.a = 1f;
            return Color.Lerp(baseColor, Color.white, 1f - Mathf.Clamp01(aoiLookup.CurrentAOIConfidence));
        }

        private void ResetFixationState()
        {
            fixationCandidateValid = false;
            fixationCandidateDirection = Vector3.forward;
            fixationAnchorPoint = Vector3.zero;
            fixationAnchorNormal = Vector3.forward;
            fixationCandidateStartTimestampMs = 0f;
            fixationCandidateDuration = 0f;
            fixationCommitCount = 0;
            HasCommittedFixation = false;
            LatestCommittedFixationSequence = 0;
            LatestCommittedFixationTimestampMs = 0f;
            LatestCommittedFixationPoint = Vector3.zero;
            LatestCommittedFixationNormal = Vector3.forward;
            LatestCommittedFixationUv = Vector2.zero;
            LatestCommittedFixationAoiId = 0;
            LatestCommittedFixationConfidence = 0f;

            if (hitMarkerVisual != null)
            {
                hitMarkerVisual.localScale = hitMarkerInitialScale;
            }
        }

        private void EnsureTrailRoot()
        {
            if (trailRoot != null || hitMarker == null)
            {
                return;
            }

            Transform parent = hitMarker.parent;
            GameObject root = new GameObject("HitMarkerTrail");
            trailRoot = root.transform;
            trailRoot.SetParent(parent, false);
            trailRoot.localPosition = Vector3.zero;
            trailRoot.localRotation = Quaternion.identity;
            trailRoot.localScale = Vector3.one;
        }

        private void AppendCommittedTrailMarker()
        {
            if (hitMarker == null || hitMarkerVisual == null)
            {
                return;
            }

            EnsureTrailRoot();

            Vector3 markerPosition = fixationAnchorPoint - (fixationAnchorNormal * trailMarkerDepthOffset);
            float scaleMultiplier = 1f + (fixationCommitCount - 1) * fixationMarkerScaleGrowth;
            float clampedScale = Mathf.Min(fixationMarkerBaseScale * scaleMultiplier, fixationMarkerMaxScale);
            Color markerColor = ResolveFixationColor();

            GameObject markerObject = CreateTrailMarker(markerPosition, fixationAnchorNormal, clampedScale, markerColor);
            if (markerObject == null)
            {
                return;
            }

            GameObject previousMarker = null;
            Vector3 previousPosition = Vector3.zero;
            if (committedMarkerObjects.Count > 0)
            {
                GameObject[] markers = committedMarkerObjects.ToArray();
                previousMarker = markers[markers.Length - 1];
                previousPosition = previousMarker.transform.position;

                // Nearby consecutive commits should reinforce the latest fixation instead of
                // flooding the trail with visually duplicated markers.
                if (Vector3.Distance(previousPosition, markerPosition) <= trailMergeDistance)
                {
                    UpdateTrailMarker(previousMarker, fixationAnchorNormal, clampedScale, markerColor);
                    Destroy(markerObject);
                    return;
                }
            }

            committedMarkerObjects.Enqueue(markerObject);

            if (previousMarker != null)
            {
                GameObject lineObject = CreateTrailLine(previousPosition, markerPosition, markerColor);
                if (lineObject != null)
                {
                    committedLineObjects.Enqueue(lineObject);
                }
            }

            while (committedMarkerObjects.Count > maxTrailMarkers)
            {
                GameObject oldestMarker = committedMarkerObjects.Dequeue();
                if (oldestMarker != null)
                {
                    Destroy(oldestMarker);
                }

                if (committedLineObjects.Count > 0)
                {
                    GameObject oldestLine = committedLineObjects.Dequeue();
                    if (oldestLine != null)
                    {
                        Destroy(oldestLine);
                    }
                }
            }
        }

        private GameObject CreateTrailMarker(Vector3 position, Vector3 outwardNormal, float scale, Color color)
        {
            if (hitMarkerVisual == null)
            {
                return null;
            }

            GameObject markerRoot = new GameObject($"FixationMarker_{fixationSequence}");
            Transform markerTransform = markerRoot.transform;
            markerTransform.SetParent(trailRoot, false);
            markerTransform.position = position;
            markerTransform.rotation = Quaternion.LookRotation(outwardNormal);

            GameObject markerVisualObject = Instantiate(hitMarkerVisual.gameObject, markerTransform);
            markerVisualObject.name = "Visual";
            markerVisualObject.SetActive(true);
            markerVisualObject.transform.localPosition = new Vector3(0f, 0f, -0.01f);
            markerVisualObject.transform.localRotation = Quaternion.identity;
            markerVisualObject.transform.localScale = new Vector3(scale, scale, scale);

            Renderer markerRenderer = markerVisualObject.GetComponent<Renderer>();
            if (markerRenderer != null)
            {
                Material markerMaterial = new Material(runtimeHitMarkerMaterial != null ? runtimeHitMarkerMaterial : markerRenderer.sharedMaterial);
                ConfigureTransparentMaterial(markerMaterial, hitMarkerTexture, color);
                markerRenderer.material = markerMaterial;
                markerRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                markerRenderer.receiveShadows = false;
            }

            return markerRoot;
        }

        private void UpdateTrailMarker(GameObject markerObject, Vector3 outwardNormal, float scale, Color color)
        {
            if (markerObject == null)
            {
                return;
            }

            markerObject.transform.rotation = Quaternion.LookRotation(outwardNormal);

            Transform markerVisualTransform = markerObject.transform.childCount > 0
                ? markerObject.transform.GetChild(0)
                : null;

            if (markerVisualTransform != null)
            {
                markerVisualTransform.localScale = new Vector3(scale, scale, scale);
                Renderer markerRenderer = markerVisualTransform.GetComponent<Renderer>();
                if (markerRenderer != null && markerRenderer.material != null)
                {
                    ConfigureTransparentMaterial(markerRenderer.material, hitMarkerTexture, color);
                }
            }
        }

        private GameObject CreateTrailLine(Vector3 start, Vector3 end, Color color)
        {
            EnsureTrailRoot();

            GameObject lineObject = new GameObject($"FixationLine_{fixationSequence}");
            Transform lineTransform = lineObject.transform;
            lineTransform.SetParent(trailRoot, false);

            LineRenderer lineRenderer = lineObject.AddComponent<LineRenderer>();
            lineRenderer.useWorldSpace = true;
            lineRenderer.positionCount = 2;
            lineRenderer.SetPosition(0, start);
            lineRenderer.SetPosition(1, end);
            lineRenderer.widthMultiplier = trailLineWidth;
            lineRenderer.numCornerVertices = 4;
            lineRenderer.numCapVertices = 4;
            lineRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            lineRenderer.receiveShadows = false;
            lineRenderer.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
            lineRenderer.lightProbeUsage = UnityEngine.Rendering.LightProbeUsage.Off;
            lineRenderer.reflectionProbeUsage = UnityEngine.Rendering.ReflectionProbeUsage.Off;

            if (runtimeTrailLineMaterial == null)
            {
                Shader shader = ResolveTransparentShader();
                if (shader != null)
                {
                    runtimeTrailLineMaterial = new Material(shader);
                    runtimeTrailLineMaterial.name = "Runtime_HitMarkerTrailLine";
                    ConfigureTransparentMaterial(runtimeTrailLineMaterial, null, color);
                }
            }

            if (runtimeTrailLineMaterial != null)
            {
                Material lineMaterial = new Material(runtimeTrailLineMaterial);
                ConfigureTransparentMaterial(lineMaterial, null, color);
                lineRenderer.material = lineMaterial;
            }

            Gradient gradient = new Gradient();
            gradient.SetKeys(
                new[]
                {
                    new GradientColorKey(color, 0f),
                    new GradientColorKey(color, 1f)
                },
                new[]
                {
                    new GradientAlphaKey(color.a, 0f),
                    new GradientAlphaKey(color.a, 1f)
                }
            );
            lineRenderer.colorGradient = gradient;

            return lineObject;
        }

        private void ClearTrail()
        {
            while (committedMarkerObjects.Count > 0)
            {
                GameObject marker = committedMarkerObjects.Dequeue();
                if (marker != null)
                {
                    Destroy(marker);
                }
            }

            while (committedLineObjects.Count > 0)
            {
                GameObject line = committedLineObjects.Dequeue();
                if (line != null)
                {
                    Destroy(line);
                }
            }
        }

        private void SetTrailVisible(bool value)
        {
            if (trailRoot != null)
            {
                trailRoot.gameObject.SetActive(value);
            }
        }

        private void WritePeriodicDebugLog(Vector3 gazeOrigin, Vector3 gazeDirection)
        {
            if ((!enableDebugLogs && !enableAOILogging) || debugLogEveryNFrames <= 0)
            {
                return;
            }

            if (Time.frameCount % debugLogEveryNFrames != 0)
            {
                return;
            }

            string cameraInfo = "";
            if (enableDebugLogs && referenceCamera != null)
            {
                Vector3 cameraPosition = referenceCamera.transform.position;
                Vector3 offset = gazeOrigin - cameraPosition;

                cameraInfo =
                    $"GazeOrigin={gazeOrigin} | " +
                    $"CameraPosition={cameraPosition} | " +
                    $"Offset={offset} | " +
                    $"OffsetMagnitude={offset.magnitude:F4} | " +
                    $"Direction={gazeDirection}";
            }

            string mapperInfo = "";
            if (enableAOILogging && sphericalMapper != null && sphericalMapper.HasValidDirection)
            {
                mapperInfo =
                    $" | UV=({sphericalMapper.CurrentUV.x:F3}, {sphericalMapper.CurrentUV.y:F3})" +
                    $" | Azimuth={sphericalMapper.CurrentAzimuthRad:F3}" +
                    $" | Elevation={sphericalMapper.CurrentElevationRad:F3}";
            }

            string aoiInfo = "";
            if (enableAOILogging && aoiLookup != null)
            {
                aoiInfo =
                    $" | AOI={aoiLookup.CurrentAOIId}" +
                    $" | Conf={aoiLookup.CurrentAOIConfidence:F2}" +
                    $" | FixSteps={fixationCommitCount}";
            }

            Debug.Log($"[EYE DEBUG] {cameraInfo}{mapperInfo}{aoiInfo}");
        }

        private bool TryIntersectRaySphere(
            Vector3 rayOrigin,
            Vector3 rayDirection,
            Vector3 sphereCenterWorld,
            float radius,
            out Vector3 hitPoint)
        {
            hitPoint = Vector3.zero;

            Vector3 oc = rayOrigin - sphereCenterWorld;
            float a = Vector3.Dot(rayDirection, rayDirection);
            float b = 2f * Vector3.Dot(oc, rayDirection);
            float c = Vector3.Dot(oc, oc) - (radius * radius);
            float discriminant = b * b - 4f * a * c;

            if (discriminant < 0f)
            {
                return false;
            }

            float sqrtDiscriminant = Mathf.Sqrt(discriminant);
            float t1 = (-b - sqrtDiscriminant) / (2f * a);
            float t2 = (-b + sqrtDiscriminant) / (2f * a);
            float t = -1f;

            if (t1 > 0f && t2 > 0f)
            {
                t = Mathf.Min(t1, t2);
            }
            else if (t1 > 0f)
            {
                t = t1;
            }
            else if (t2 > 0f)
            {
                t = t2;
            }

            if (t <= 0f)
            {
                return false;
            }

            hitPoint = rayOrigin + rayDirection * t;
            return true;
        }

        private void SetLineRendererEnabled(LineRenderer lineRenderer, bool value)
        {
            if (lineRenderer != null)
            {
                lineRenderer.enabled = value;
            }
        }

        private void SetHitMarkerEnabled(bool value)
        {
            if (hitMarker != null)
            {
                hitMarker.gameObject.SetActive(value);
            }
        }

        private Shader ResolveTransparentShader()
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Unlit");
            if (shader != null)
            {
                return shader;
            }

            shader = Shader.Find("Unlit/Transparent");
            return shader;
        }

        private void ConfigureTransparentMaterial(Material material, Texture texture, Color color)
        {
            material.mainTexture = texture;
            material.color = color;

            if (material.HasProperty("_BaseMap"))
            {
                material.SetTexture("_BaseMap", texture);
            }

            if (material.HasProperty("_BaseColor"))
            {
                material.SetColor("_BaseColor", color);
            }

            if (material.HasProperty("_Surface"))
            {
                material.SetFloat("_Surface", 1f);
            }

            if (material.HasProperty("_Blend"))
            {
                material.SetFloat("_Blend", 0f);
            }

            if (material.HasProperty("_Cull"))
            {
                material.SetFloat("_Cull", 0f);
            }

            if (material.HasProperty("_SrcBlend"))
            {
                material.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.SrcAlpha);
            }

            if (material.HasProperty("_DstBlend"))
            {
                material.SetFloat("_DstBlend", (float)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
            }

            if (material.HasProperty("_ZWrite"))
            {
                material.SetFloat("_ZWrite", 0f);
            }

            material.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
            material.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
        }
    }
}
