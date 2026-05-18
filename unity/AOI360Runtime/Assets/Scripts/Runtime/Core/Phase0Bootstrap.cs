using AOI360.Runtime.AOI;
using AOI360.Runtime.Mapping;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace AOI360.Runtime.Core
{
    [DefaultExecutionOrder(-200)]
    public class Phase0Bootstrap : MonoBehaviour
    {
        // This bootstrap owns the optional AOI overlay layer used for in-headset
        // validation. It should stay visually helpful without competing with the
        // main video playback path for CPU time.
        private static readonly string[] TargetSceneNames =
        {
            "Phase0_360Playback_VR_sampleRIG"
        };
        private const string RuntimeBootstrapName = "Phase0Bootstrap_Runtime";
        private static bool sceneHookRegistered;

        [Header("Overlay")]
        [SerializeField] private bool createAoiOverlay = true;
        [SerializeField] private float overlaySphereRadius = 4.98f;
        [SerializeField] private float overlayOpacity = 0.24f;
        [SerializeField] private float focusedOverlayOpacity = 0.6f;
        [SerializeField] private float focusedColorTolerance = 0.0025f;

        private AOILookup aoiLookup;
        private SphericalMapper sphericalMapper;
        private Transform sphereCenter;
        private GameObject overlaySphere;
        private Material overlayMaterial;
        private int lastHighlightedAoiId = int.MinValue;
        private Texture2D lastOverlaySourceTexture;
        private Color lastFocusedAoiColor = Color.clear;
        private float lastYawOffsetDegrees = float.NaN;
        private float lastVerticalOffsetDegrees = float.NaN;
        private bool? lastHorizontalFlip;
        private bool? lastVerticalFlip;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void RegisterSceneHook()
        {
            if (sceneHookRegistered)
            {
                return;
            }

            SceneManager.sceneLoaded += HandleSceneLoaded;
            sceneHookRegistered = true;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void EnsureBootstrapAfterSceneLoad()
        {
            EnsureBootstrapForScene(SceneManager.GetActiveScene());
        }

        private static void HandleSceneLoaded(Scene scene, LoadSceneMode loadMode)
        {
            EnsureBootstrapForScene(scene);
        }

        private static void EnsureBootstrapForScene(Scene scene)
        {
            if (!IsTargetScene(scene.name))
            {
                return;
            }

            if (FindFirstObjectByType<Phase0Bootstrap>() != null)
            {
                return;
            }

            GameObject bootstrap = new GameObject(RuntimeBootstrapName);
            bootstrap.AddComponent<Phase0Bootstrap>();
        }

        private void Awake()
        {
            if (!IsTargetScene(SceneManager.GetActiveScene().name))
            {
                enabled = false;
                return;
            }

            ResolveReferences();
            EnsureOverlaySphere();
            RefreshOverlayMaterial(forceRefresh: true);
        }

        private static bool IsTargetScene(string sceneName)
        {
            for (int i = 0; i < TargetSceneNames.Length; i++)
            {
                if (string.Equals(sceneName, TargetSceneNames[i], System.StringComparison.Ordinal))
                {
                    return true;
                }
            }

            return false;
        }

        private void Update()
        {
            ResolveReferences();

            if (!createAoiOverlay || aoiLookup == null)
            {
                return;
            }

            if (overlaySphere == null || overlayMaterial == null)
            {
                EnsureOverlaySphere();
            }

            if (overlayMaterial == null)
            {
                return;
            }

            Texture2D currentSourceTexture = aoiLookup.AOIMapTexture;
            if (currentSourceTexture == null)
            {
                return;
            }

            if (currentSourceTexture != lastOverlaySourceTexture)
            {
                RefreshOverlayMaterial(forceRefresh: true);
                return;
            }

            if (HasProjectionCalibrationChanged())
            {
                RefreshOverlayMaterial(forceRefresh: true);
                return;
            }

            if (aoiLookup.CurrentAOIId != lastHighlightedAoiId || aoiLookup.CurrentAOIColor != lastFocusedAoiColor)
            {
                RefreshOverlayMaterial(forceRefresh: false);
            }
        }

        private void ResolveReferences()
        {
            if (aoiLookup == null)
            {
                aoiLookup = FindFirstObjectByType<AOILookup>();
            }

            if (sphericalMapper == null)
            {
                sphericalMapper = FindFirstObjectByType<SphericalMapper>();
            }

            if (sphereCenter == null)
            {
                GameObject center = GameObject.Find("SphereCenter");
                sphereCenter = center != null ? center.transform : null;
            }
        }

        private void EnsureOverlaySphere()
        {
            if (!createAoiOverlay || aoiLookup == null || aoiLookup.AOIMapTexture == null)
            {
                return;
            }

            if (overlaySphere != null)
            {
                return;
            }

            Shader overlayShader = ResolveTransparentShader();
            if (overlayShader == null)
            {
                Debug.LogWarning("[Phase0Bootstrap] Could not find a transparent runtime shader for AOI overlay.");
                return;
            }

            overlayMaterial = new Material(overlayShader);
            overlayMaterial.name = "Runtime_AOIOverlay";
            ConfigureTransparentMaterial(overlayMaterial, null, Color.white);

            // Render the AOI map on a second sphere slightly inside the video sphere so AOIs
            // can be debugged directly in-headset without modifying the source video asset.
            overlaySphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            overlaySphere.name = "AOIOverlaySphere";
            overlaySphere.transform.SetParent(sphereCenter, false);
            overlaySphere.transform.localPosition = Vector3.zero;
            overlaySphere.transform.localRotation = Quaternion.identity;
            overlaySphere.transform.localScale = new Vector3(
                overlaySphereRadius * 2f,
                overlaySphereRadius * 2f,
                overlaySphereRadius * 2f
            );

            Collider overlayCollider = overlaySphere.GetComponent<Collider>();
            if (overlayCollider != null)
            {
                Destroy(overlayCollider);
            }

            MeshRenderer overlayRenderer = overlaySphere.GetComponent<MeshRenderer>();
            if (overlayRenderer != null)
            {
                overlayRenderer.shadowCastingMode = ShadowCastingMode.Off;
                overlayRenderer.receiveShadows = false;
                overlayRenderer.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
                overlayRenderer.lightProbeUsage = LightProbeUsage.Off;
                overlayRenderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
                overlayRenderer.material = overlayMaterial;
            }

            MeshFilter overlayFilter = overlaySphere.GetComponent<MeshFilter>();
            if (overlayFilter != null && overlayFilter.sharedMesh != null)
            {
                overlayFilter.sharedMesh = CreateInvertedSphereMesh(overlayFilter.sharedMesh);
            }
        }

        private void RefreshOverlayMaterial(bool forceRefresh)
        {
            Texture2D sourceTexture = aoiLookup != null ? aoiLookup.AOIMapTexture : null;
            if (sourceTexture == null || overlayMaterial == null)
            {
                return;
            }

            int highlightedAoiId = aoiLookup.CurrentAOIId;
            Color focusedAoiColor = highlightedAoiId > 0 ? aoiLookup.CurrentAOIColor : Color.clear;
            if (!forceRefresh &&
                highlightedAoiId == lastHighlightedAoiId &&
                focusedAoiColor == lastFocusedAoiColor)
            {
                return;
            }

            lastHighlightedAoiId = highlightedAoiId;
            lastOverlaySourceTexture = sourceTexture;
            lastFocusedAoiColor = focusedAoiColor;
            if (forceRefresh)
            {
                // Rebind the whole texture only when the AOI map itself changes.
                // AOI focus changes should stay on the lighter property-update path.
                ConfigureTransparentMaterial(overlayMaterial, sourceTexture, Color.white);
                return;
            }

            UpdateFocusedOverlayState();
        }

        private Mesh CreateInvertedSphereMesh(Mesh sourceMesh)
        {
            Mesh invertedMesh = Instantiate(sourceMesh);
            invertedMesh.name = $"{sourceMesh.name}_Inverted";

            // The observer stands inside the 360 sphere, so the triangles and normals must be
            // flipped to make the overlay visible from the interior.
            int[] triangles = invertedMesh.triangles;
            for (int i = 0; i < triangles.Length; i += 3)
            {
                int tmp = triangles[i];
                triangles[i] = triangles[i + 1];
                triangles[i + 1] = tmp;
            }

            invertedMesh.triangles = triangles;

            Vector3[] normals = invertedMesh.normals;
            for (int i = 0; i < normals.Length; i++)
            {
                normals[i] = -normals[i];
            }

            invertedMesh.normals = normals;
            invertedMesh.RecalculateBounds();
            return invertedMesh;
        }

        private Shader ResolveTransparentShader()
        {
            Shader shader = Shader.Find("AOI360/Equirectangular Overlay");
            if (shader != null)
            {
                return shader;
            }

            shader = Shader.Find("Universal Render Pipeline/Unlit");
            if (shader != null)
            {
                return shader;
            }

            return Shader.Find("Unlit/Transparent");
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

            if (material.HasProperty("_YawOffsetDegrees"))
            {
                material.SetFloat("_YawOffsetDegrees", sphericalMapper != null ? sphericalMapper.YawOffsetDegrees : 0f);
            }

            if (material.HasProperty("_VerticalOffsetDegrees"))
            {
                material.SetFloat("_VerticalOffsetDegrees", sphericalMapper != null ? sphericalMapper.VerticalOffsetDegrees : 0f);
            }

            if (material.HasProperty("_FlipHorizontal"))
            {
                material.SetFloat("_FlipHorizontal", sphericalMapper != null && sphericalMapper.FlipHorizontally ? 1f : 0f);
            }

            if (material.HasProperty("_FlipVertical"))
            {
                material.SetFloat("_FlipVertical", sphericalMapper != null && sphericalMapper.FlipVertically ? 1f : 0f);
            }

            if (material.HasProperty("_BaseOpacity"))
            {
                material.SetFloat("_BaseOpacity", overlayOpacity);
            }

            if (material.HasProperty("_FocusedOpacity"))
            {
                material.SetFloat("_FocusedOpacity", focusedOverlayOpacity);
            }

            if (material.HasProperty("_FocusedColorTolerance"))
            {
                material.SetFloat("_FocusedColorTolerance", focusedColorTolerance);
            }

            UpdateFocusedOverlayState();

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
                material.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            }

            if (material.HasProperty("_DstBlend"))
            {
                material.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            }

            if (material.HasProperty("_ZWrite"))
            {
                material.SetFloat("_ZWrite", 0f);
            }

            material.renderQueue = (int)RenderQueue.Transparent;
            material.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            CacheProjectionCalibrationState();
        }

        private void UpdateFocusedOverlayState()
        {
            if (overlayMaterial == null)
            {
                return;
            }

            if (overlayMaterial.HasProperty("_FocusedAoiColor"))
            {
                overlayMaterial.SetColor(
                    "_FocusedAoiColor",
                    aoiLookup != null && aoiLookup.CurrentAOIId > 0 ? aoiLookup.CurrentAOIColor : Color.clear
                );
            }

            if (overlayMaterial.HasProperty("_HasFocusedAoi"))
            {
                overlayMaterial.SetFloat("_HasFocusedAoi", aoiLookup != null && aoiLookup.CurrentAOIId > 0 ? 1f : 0f);
            }
        }

        private bool HasProjectionCalibrationChanged()
        {
            if (sphericalMapper == null)
            {
                return false;
            }

            return !Mathf.Approximately(lastYawOffsetDegrees, sphericalMapper.YawOffsetDegrees) ||
                   !Mathf.Approximately(lastVerticalOffsetDegrees, sphericalMapper.VerticalOffsetDegrees) ||
                   lastHorizontalFlip != sphericalMapper.FlipHorizontally ||
                   lastVerticalFlip != sphericalMapper.FlipVertically;
        }

        private void CacheProjectionCalibrationState()
        {
            if (sphericalMapper == null)
            {
                lastYawOffsetDegrees = 0f;
                lastVerticalOffsetDegrees = 0f;
                lastHorizontalFlip = false;
                lastVerticalFlip = false;
                return;
            }

            lastYawOffsetDegrees = sphericalMapper.YawOffsetDegrees;
            lastVerticalOffsetDegrees = sphericalMapper.VerticalOffsetDegrees;
            lastHorizontalFlip = sphericalMapper.FlipHorizontally;
            lastVerticalFlip = sphericalMapper.FlipVertically;
        }
    }
}
