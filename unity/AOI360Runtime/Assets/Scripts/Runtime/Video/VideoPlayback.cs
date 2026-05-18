using System.IO;
using AOI360.Runtime.Experiment;
using AOI360.Runtime.Mapping;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Video;

namespace AOI360.Runtime.Video
{
    [RequireComponent(typeof(VideoPlayer))]
    public class VideoPlayback : MonoBehaviour
    {
        private const string LatitudeLongitudeLayoutKeyword = "_MAPPING_LATITUDE_LONGITUDE_LAYOUT";
        private const string SixFramesLayoutKeyword = "_MAPPING_6_FRAMES_LAYOUT";
        private const string MirrorOnBackKeyword = "_MIRRORONBACK_ON";
        private const string RuntimeVideoSphereName = "Runtime360VideoSphere";
        private const float RuntimeVideoSphereRadius = 5f;

        [Header("Video")]
        [SerializeField] private string videoFileName = "sample360.mp4";
        [SerializeField] private bool playOnStart = true;
        [SerializeField] private bool loop = true;

        [Header("Output")]
        [SerializeField] private RenderTexture targetTexture;
        [SerializeField] private Material skyboxMaterial;

        [Header("Runtime Output Fallback")]
        [SerializeField] private bool createRuntimeOutputIfMissing = true;
        [SerializeField] private int runtimeTextureWidth = 4096;
        [SerializeField] private int runtimeTextureHeight = 2048;
        [SerializeField] private bool forceSkyboxOutput = true;
        [SerializeField] private bool useImmersiveSphereOutput = true;

        [Header("Debug")]
        [SerializeField] private bool logVideoEvents = true;

        [Header("Performance")]
        [SerializeField] private bool allowFrameDrop = true;

        private VideoPlayer videoPlayer;
        private bool isPrepared;
        private bool hasPreparationStarted;
        private bool hasPreparationFailed;
        private bool playRequestedBeforePrepare;
        private string runtimeSelectedVideoPath = string.Empty;
        private string activeVideoPath = string.Empty;
        private string lastPrepareErrorMessage = string.Empty;
        private bool ownsRuntimeTexture;
        private bool ownsRuntimeMaterial;
        private bool hasReachedPlaybackEnd;
        private SphericalMapper sphericalMapper;
        private Transform sphereCenter;
        private GameObject runtimeVideoSphere;
        private Material runtimeVideoSphereMaterial;
        private float lastYawOffsetDegrees = float.NaN;
        private float lastVerticalOffsetDegrees = float.NaN;
        private bool? lastHorizontalFlip;
        private bool? lastVerticalFlip;

        public bool IsPrepared => isPrepared;
        public bool HasPreparationStarted => hasPreparationStarted;
        public bool HasPreparationFailed => hasPreparationFailed;
        public string LastPrepareErrorMessage => lastPrepareErrorMessage;
        public string VideoFileName => videoFileName;
        public string VideoStem => Path.GetFileNameWithoutExtension(videoFileName);
        public string ActiveVideoPath => activeVideoPath;
        public long CurrentFrame => videoPlayer != null ? videoPlayer.frame : -1;
        public double CurrentTime => videoPlayer != null ? videoPlayer.time : 0d;
        public bool IsPlaying => videoPlayer != null && videoPlayer.isPlaying;
        public bool HasReachedPlaybackEnd => hasReachedPlaybackEnd;

        private void Awake()
        {
            videoPlayer = GetComponent<VideoPlayer>();

            if (videoPlayer == null)
            {
                videoPlayer = gameObject.AddComponent<VideoPlayer>();
            }

            EnsureRuntimeOutput();
            ResolveImmersiveOutputReferences();

            videoPlayer.playOnAwake = false;
            videoPlayer.isLooping = loop;
            videoPlayer.renderMode = VideoRenderMode.RenderTexture;
            videoPlayer.targetTexture = targetTexture;
            videoPlayer.audioOutputMode = VideoAudioOutputMode.None;
            videoPlayer.sendFrameReadyEvents = false;
            videoPlayer.skipOnDrop = allowFrameDrop;
            videoPlayer.waitForFirstFrame = true;

            videoPlayer.prepareCompleted += HandlePrepareCompleted;
            videoPlayer.errorReceived += HandleErrorReceived;
            videoPlayer.loopPointReached += HandleLoopPointReached;

            ClearOutputToBlack();
            ApplySkyboxOutput();
            EnsureImmersiveSphereOutput();
            ApplySelectedStimulusOverride();
            BeginPrepareIfNeeded();

            if (logVideoEvents)
            {
                Debug.Log(
                    $"[VideoPlayback] Awake configured. " +
                    $"targetTexture={(targetTexture != null ? targetTexture.name : "NULL")} " +
                    $"skyboxMaterial={(skyboxMaterial != null ? skyboxMaterial.name : "NULL")} " +
                    $"renderMode={videoPlayer.renderMode}"
                );
            }
        }

        private void Start()
        {
            BeginPrepareIfNeeded();

            if (playOnStart && !ExperimentSessionState.IsPlaybackStartLocked)
            {
                PlayVideo();
            }
        }

        private void Update()
        {
            if (!useImmersiveSphereOutput)
            {
                return;
            }

            ResolveImmersiveOutputReferences();
            EnsureImmersiveSphereOutput();
            RefreshImmersiveSphereMaterial(forceRefresh: false);
        }

        private void OnDestroy()
        {
            if (videoPlayer != null)
            {
                videoPlayer.prepareCompleted -= HandlePrepareCompleted;
                videoPlayer.errorReceived -= HandleErrorReceived;
                videoPlayer.loopPointReached -= HandleLoopPointReached;
            }

            if (ownsRuntimeTexture && targetTexture != null)
            {
                targetTexture.Release();
                Destroy(targetTexture);
                targetTexture = null;
            }

            if (ownsRuntimeMaterial && skyboxMaterial != null)
            {
                Destroy(skyboxMaterial);
                skyboxMaterial = null;
            }

            if (runtimeVideoSphere != null)
            {
                Destroy(runtimeVideoSphere);
                runtimeVideoSphere = null;
            }

            if (runtimeVideoSphereMaterial != null)
            {
                Destroy(runtimeVideoSphereMaterial);
                runtimeVideoSphereMaterial = null;
            }
        }

        private void EnsureRuntimeOutput()
        {
            if (!createRuntimeOutputIfMissing)
            {
                return;
            }

            if (targetTexture == null)
            {
                targetTexture = new RenderTexture(runtimeTextureWidth, runtimeTextureHeight, 0, RenderTextureFormat.ARGB32)
                {
                    name = "AOI360_RuntimeVideoTexture",
                    dimension = UnityEngine.Rendering.TextureDimension.Tex2D,
                    useMipMap = false,
                    autoGenerateMips = false,
                    wrapMode = TextureWrapMode.Repeat,
                    filterMode = FilterMode.Bilinear
                };

                targetTexture.Create();
                ownsRuntimeTexture = true;

                if (logVideoEvents)
                {
                    Debug.Log($"[VideoPlayback] Created runtime RenderTexture {runtimeTextureWidth}x{runtimeTextureHeight}.");
                }
            }

            if (skyboxMaterial == null)
            {
                Shader skyboxShader = Shader.Find("Skybox/Panoramic");

                if (skyboxShader == null)
                {
                    Debug.LogError("[VideoPlayback] Shader 'Skybox/Panoramic' was not found.");
                    return;
                }

                skyboxMaterial = new Material(skyboxShader)
                {
                    name = "AOI360_RuntimePanoramicSkybox"
                };

                ownsRuntimeMaterial = true;

                if (logVideoEvents)
                {
                    Debug.Log("[VideoPlayback] Created runtime Skybox/Panoramic material.");
                }
            }
        }

        private void ApplySkyboxOutput()
        {
            if (!forceSkyboxOutput)
            {
                return;
            }

            if (skyboxMaterial == null || targetTexture == null)
            {
                Debug.LogWarning(
                    $"[VideoPlayback] Cannot apply skybox output. " +
                    $"skyboxMaterial={(skyboxMaterial != null ? skyboxMaterial.name : "NULL")}, " +
                    $"targetTexture={(targetTexture != null ? targetTexture.name : "NULL")}"
                );
                return;
            }

            skyboxMaterial.SetTexture("_MainTex", targetTexture);

            if (skyboxMaterial.HasProperty("_ImageType"))
            {
                skyboxMaterial.SetFloat("_ImageType", 0f);
            }

            if (skyboxMaterial.HasProperty("_Mapping"))
            {
                skyboxMaterial.SetFloat("_Mapping", 1f);
            }

            if (skyboxMaterial.HasProperty("_Rotation"))
            {
                skyboxMaterial.SetFloat("_Rotation", 0f);
            }

            ForceLatitudeLongitudeLayout();

            RenderSettings.skybox = skyboxMaterial;
            DynamicGI.UpdateEnvironment();

            if (logVideoEvents)
            {
                Debug.Log($"[VideoPlayback] Skybox applied with texture '{targetTexture.name}'.");
            }
        }

        private void ResolveImmersiveOutputReferences()
        {
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

        private void EnsureImmersiveSphereOutput()
        {
            if (!useImmersiveSphereOutput || targetTexture == null)
            {
                return;
            }

            ResolveImmersiveOutputReferences();

            if (runtimeVideoSphereMaterial == null)
            {
                Shader shader = Shader.Find("AOI360/Equirectangular Video");
                if (shader == null)
                {
                    Debug.LogWarning("[VideoPlayback] Shader 'AOI360/Equirectangular Video' was not found.");
                    return;
                }

                runtimeVideoSphereMaterial = new Material(shader)
                {
                    name = "Runtime_EquirectangularVideo360"
                };
            }

            if (runtimeVideoSphere != null)
            {
                RefreshImmersiveSphereMaterial(forceRefresh: true);
                return;
            }

            runtimeVideoSphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            runtimeVideoSphere.name = RuntimeVideoSphereName;
            runtimeVideoSphere.transform.SetParent(sphereCenter, false);
            runtimeVideoSphere.transform.localPosition = Vector3.zero;
            runtimeVideoSphere.transform.localRotation = Quaternion.identity;
            runtimeVideoSphere.transform.localScale = Vector3.one * (RuntimeVideoSphereRadius * 2f);

            Collider sphereCollider = runtimeVideoSphere.GetComponent<Collider>();
            if (sphereCollider != null)
            {
                Destroy(sphereCollider);
            }

            MeshRenderer sphereRenderer = runtimeVideoSphere.GetComponent<MeshRenderer>();
            if (sphereRenderer != null)
            {
                sphereRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                sphereRenderer.receiveShadows = false;
                sphereRenderer.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
                sphereRenderer.lightProbeUsage = UnityEngine.Rendering.LightProbeUsage.Off;
                sphereRenderer.reflectionProbeUsage = UnityEngine.Rendering.ReflectionProbeUsage.Off;
                sphereRenderer.material = runtimeVideoSphereMaterial;
            }

            MeshFilter meshFilter = runtimeVideoSphere.GetComponent<MeshFilter>();
            if (meshFilter != null && meshFilter.sharedMesh != null)
            {
                meshFilter.sharedMesh = CreateInvertedSphereMesh(meshFilter.sharedMesh);
            }

            RefreshImmersiveSphereMaterial(forceRefresh: true);

            if (logVideoEvents)
            {
                Debug.Log("[VideoPlayback] Created runtime 360 video sphere output.");
            }
        }

        private Mesh CreateInvertedSphereMesh(Mesh sourceMesh)
        {
            Mesh invertedMesh = Instantiate(sourceMesh);
            invertedMesh.name = $"{sourceMesh.name}_VideoInverted";

            int[] triangles = invertedMesh.triangles;
            for (int i = 0; i < triangles.Length; i += 3)
            {
                int temp = triangles[i];
                triangles[i] = triangles[i + 1];
                triangles[i + 1] = temp;
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

        private void RefreshImmersiveSphereMaterial(bool forceRefresh)
        {
            if (runtimeVideoSphereMaterial == null || targetTexture == null)
            {
                return;
            }

            if (!forceRefresh && !HasImmersiveProjectionChanged())
            {
                return;
            }

            runtimeVideoSphereMaterial.SetTexture("_MainTex", targetTexture);
            runtimeVideoSphereMaterial.SetColor("_Tint", Color.white);
            runtimeVideoSphereMaterial.SetFloat("_YawOffsetDegrees", sphericalMapper != null ? sphericalMapper.YawOffsetDegrees : 0f);
            runtimeVideoSphereMaterial.SetFloat("_VerticalOffsetDegrees", sphericalMapper != null ? sphericalMapper.VerticalOffsetDegrees : 0f);
            runtimeVideoSphereMaterial.SetFloat("_FlipHorizontal", sphericalMapper != null && sphericalMapper.FlipHorizontally ? 1f : 0f);
            runtimeVideoSphereMaterial.SetFloat("_FlipVertical", sphericalMapper != null && sphericalMapper.FlipVertically ? 1f : 0f);
            CacheImmersiveProjectionState();
        }

        private bool HasImmersiveProjectionChanged()
        {
            if (sphericalMapper == null)
            {
                return lastHorizontalFlip.HasValue || lastVerticalFlip.HasValue;
            }

            return !Mathf.Approximately(lastYawOffsetDegrees, sphericalMapper.YawOffsetDegrees) ||
                   !Mathf.Approximately(lastVerticalOffsetDegrees, sphericalMapper.VerticalOffsetDegrees) ||
                   lastHorizontalFlip != sphericalMapper.FlipHorizontally ||
                   lastVerticalFlip != sphericalMapper.FlipVertically;
        }

        private void CacheImmersiveProjectionState()
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

        private void HandlePrepareCompleted(VideoPlayer source)
        {
            isPrepared = true;
            hasPreparationFailed = false;
            lastPrepareErrorMessage = string.Empty;
            hasReachedPlaybackEnd = false;
            ApplySkyboxOutput();

            if (logVideoEvents)
            {
                Debug.Log(
                    $"[VideoPlayback] Video prepared correctly. " +
                    $"width={source.width}, height={source.height}, frameCount={source.frameCount}, duration={source.length:0.00}s"
                );
            }

            bool shouldAutoPlay = (playOnStart || playRequestedBeforePrepare) && !ExperimentSessionState.IsPlaybackStartLocked;
            if (shouldAutoPlay)
            {
                playRequestedBeforePrepare = false;
                PlayVideo();
            }
        }

        private void HandleErrorReceived(VideoPlayer source, string message)
        {
            hasPreparationFailed = true;
            lastPrepareErrorMessage = string.IsNullOrWhiteSpace(message) ? "Unknown video error." : message;
            playRequestedBeforePrepare = false;
            Debug.LogError($"[VideoPlayback] Video error: {lastPrepareErrorMessage}");
        }

        private void HandleLoopPointReached(VideoPlayer source)
        {
            hasReachedPlaybackEnd = !source.isLooping;

            if (!logVideoEvents)
            {
                return;
            }

            if (source.isLooping)
            {
                Debug.Log("[VideoPlayback] The video reached the end and will continue looping.");
                return;
            }

            Debug.Log("[VideoPlayback] The video reached the end and playback stopped.");
        }

        private void ApplySelectedStimulusOverride()
        {
            if (!ExperimentSessionState.HasSelectedStimulus)
            {
                return;
            }

            ExperimentStimulusDefinition stimulus = ExperimentSessionState.SelectedStimulus;
            if (stimulus == null)
            {
                return;
            }

            if (!string.IsNullOrWhiteSpace(stimulus.VideoFileName))
            {
                videoFileName = stimulus.VideoFileName;
            }

            runtimeSelectedVideoPath = stimulus.VideoAbsolutePath ?? string.Empty;

            if (logVideoEvents)
            {
                Debug.Log(
                    $"[VideoPlayback] Selected stimulus override -> videoFileName={videoFileName}, " +
                    $"runtimeSelectedVideoPath={runtimeSelectedVideoPath}"
                );
            }
        }

        private string ResolveVideoPath()
        {
            if (!string.IsNullOrWhiteSpace(runtimeSelectedVideoPath))
            {
                return runtimeSelectedVideoPath;
            }

            return Path.Combine(Application.streamingAssetsPath, "Videos", videoFileName);
        }

        public bool BeginPrepareIfNeeded()
        {
            if (videoPlayer == null)
            {
                return false;
            }

            if (isPrepared || hasPreparationStarted)
            {
                return isPrepared || videoPlayer.isPrepared;
            }

            ApplySelectedStimulusOverride();

            string videoPath = ResolveVideoPath();
            activeVideoPath = videoPath;
            hasReachedPlaybackEnd = false;

            if (!File.Exists(videoPath))
            {
                hasPreparationFailed = true;
                lastPrepareErrorMessage = $"Video file not found: {videoPath}";
                Debug.LogError($"[VideoPlayback] {lastPrepareErrorMessage}");
                return false;
            }

            videoPlayer.source = VideoSource.Url;
            videoPlayer.url = videoPath;
            hasPreparationStarted = true;
            hasPreparationFailed = false;
            lastPrepareErrorMessage = string.Empty;
            ClearOutputToBlack();
            ApplySkyboxOutput();

            if (logVideoEvents)
            {
                Debug.Log($"[VideoPlayback] Preparing video from: {videoPath}");
            }

            videoPlayer.Prepare();
            return true;
        }

        public void PlayVideo()
        {
            if (videoPlayer == null)
            {
                Debug.LogWarning("[VideoPlayback] PlayVideo ignored: VideoPlayer is null.");
                return;
            }

            if (!isPrepared && videoPlayer.isPrepared)
            {
                isPrepared = true;
            }

            if (!isPrepared)
            {
                if (hasPreparationFailed)
                {
                    Debug.LogWarning(
                        $"[VideoPlayback] PlayVideo ignored because preparation failed: {lastPrepareErrorMessage}"
                    );
                    return;
                }

                playRequestedBeforePrepare = true;
                BeginPrepareIfNeeded();

                if (logVideoEvents)
                {
                    Debug.Log("[VideoPlayback] Play requested before preparation completed. Queuing start.");
                }

                return;
            }

            ApplySkyboxOutput();
            playRequestedBeforePrepare = false;
            hasReachedPlaybackEnd = false;
            videoPlayer.Play();

            if (logVideoEvents)
            {
                Debug.Log(
                    $"[VideoPlayback] Playback started. " +
                    $"isPlaying={videoPlayer.isPlaying}, frame={videoPlayer.frame}, time={videoPlayer.time:0.00}"
                );
            }
        }

        public void PauseVideo()
        {
            if (videoPlayer != null)
            {
                videoPlayer.Pause();

                if (logVideoEvents)
                {
                    Debug.Log("[VideoPlayback] Playback paused.");
                }
            }
        }

        public void StopVideo()
        {
            if (videoPlayer != null)
            {
                videoPlayer.Stop();
                playRequestedBeforePrepare = false;
                hasReachedPlaybackEnd = false;
                ClearOutputToBlack();
                ApplySkyboxOutput();

                if (logVideoEvents)
                {
                    Debug.Log("[VideoPlayback] Playback stopped.");
                }
            }
        }

        public void SetLoop(bool value)
        {
            loop = value;

            if (videoPlayer != null)
            {
                videoPlayer.isLooping = loop;
            }
        }

        private void ForceLatitudeLongitudeLayout()
        {
            if (skyboxMaterial == null)
            {
                return;
            }

            skyboxMaterial.DisableKeyword(SixFramesLayoutKeyword);
            skyboxMaterial.EnableKeyword(LatitudeLongitudeLayoutKeyword);

            bool mirrorOnBack = skyboxMaterial.HasProperty("_MirrorOnBack") &&
                                skyboxMaterial.GetFloat("_MirrorOnBack") > 0.5f;

            if (mirrorOnBack)
            {
                skyboxMaterial.EnableKeyword(MirrorOnBackKeyword);
            }
            else
            {
                skyboxMaterial.DisableKeyword(MirrorOnBackKeyword);
            }
        }

        private void ClearOutputToBlack()
        {
            if (targetTexture == null)
            {
                return;
            }

            if (!targetTexture.IsCreated())
            {
                targetTexture.Create();
            }

            RenderTexture previousActive = RenderTexture.active;
            RenderTexture.active = targetTexture;
            GL.Clear(true, true, Color.black);
            RenderTexture.active = previousActive;
        }
    }
}
