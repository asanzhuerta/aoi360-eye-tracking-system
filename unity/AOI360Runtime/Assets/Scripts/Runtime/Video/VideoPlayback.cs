using System.Collections;
using System.IO;
using AOI360.Runtime.Experiment;
using UnityEngine;
using UnityEngine.Video;

namespace AOI360.Runtime.Video
{
    [RequireComponent(typeof(VideoPlayer))]
    public class VideoPlayback : MonoBehaviour
    {
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

        [Header("Debug")]
        [SerializeField] private bool logVideoEvents = true;

        [Header("Performance")]
        [SerializeField] private bool allowFrameDrop = true;

        private VideoPlayer videoPlayer;
        private bool isPrepared;
        private string runtimeSelectedVideoPath = string.Empty;
        private string activeVideoPath = string.Empty;
        private bool ownsRuntimeTexture;
        private bool ownsRuntimeMaterial;

        public bool IsPrepared => isPrepared;
        public string VideoFileName => videoFileName;
        public string VideoStem => Path.GetFileNameWithoutExtension(videoFileName);
        public string ActiveVideoPath => activeVideoPath;
        public long CurrentFrame => videoPlayer != null ? videoPlayer.frame : -1;
        public double CurrentTime => videoPlayer != null ? videoPlayer.time : 0d;
        public bool IsPlaying => videoPlayer != null && videoPlayer.isPlaying;

        private void Awake()
        {
            videoPlayer = GetComponent<VideoPlayer>();

            if (videoPlayer == null)
            {
                videoPlayer = gameObject.AddComponent<VideoPlayer>();
            }

            EnsureRuntimeOutput();

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

            ApplySkyboxOutput();

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

        private IEnumerator Start()
        {
            ApplySelectedStimulusOverride();

            string videoPath = ResolveVideoPath();
            activeVideoPath = videoPath;

            if (!File.Exists(videoPath))
            {
                Debug.LogError($"[VideoPlayback] No se encontró el vídeo en: {videoPath}");
                yield break;
            }

            videoPlayer.source = VideoSource.Url;
            videoPlayer.url = videoPath;

            if (logVideoEvents)
            {
                Debug.Log($"[VideoPlayback] Preparando vídeo desde: {videoPath}");
            }

            videoPlayer.Prepare();

            while (!videoPlayer.isPrepared)
            {
                yield return null;
            }

            bool shouldAutoPlay = playOnStart && !ExperimentSessionState.IsPlaybackStartLocked;
            if (shouldAutoPlay)
            {
                PlayVideo();
            }
            else if (logVideoEvents)
            {
                Debug.Log(
                    $"[VideoPlayback] Vídeo preparado pero no se inicia automáticamente. " +
                    $"playOnStart={playOnStart}, locked={ExperimentSessionState.IsPlaybackStartLocked}"
                );
            }
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
                    Debug.LogError("[VideoPlayback] No se encontró el shader 'Skybox/Panoramic'. No puedo crear skybox 360 runtime.");
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
                    $"[VideoPlayback] No se puede aplicar skybox. " +
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
                skyboxMaterial.SetFloat("_Mapping", 0f);
            }

            if (skyboxMaterial.HasProperty("_Rotation"))
            {
                skyboxMaterial.SetFloat("_Rotation", 0f);
            }

            RenderSettings.skybox = skyboxMaterial;
            DynamicGI.UpdateEnvironment();

            if (logVideoEvents)
            {
                Debug.Log($"[VideoPlayback] Skybox applied with texture '{targetTexture.name}'.");
            }
        }

        private void HandlePrepareCompleted(VideoPlayer source)
        {
            isPrepared = true;
            ApplySkyboxOutput();

            if (logVideoEvents)
            {
                Debug.Log(
                    $"[VideoPlayback] Vídeo preparado correctamente. " +
                    $"width={source.width}, height={source.height}, frameCount={source.frameCount}, duration={source.length:0.00}s"
                );
            }
        }

        private void HandleErrorReceived(VideoPlayer source, string message)
        {
            Debug.LogError($"[VideoPlayback] Error reproduciendo vídeo: {message}");
        }

        private void HandleLoopPointReached(VideoPlayer source)
        {
            if (logVideoEvents)
            {
                Debug.Log("[VideoPlayback] El vídeo ha llegado al final y continuará en loop.");
            }
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

        public void PlayVideo()
        {
            if (videoPlayer == null)
            {
                Debug.LogWarning("[VideoPlayback] PlayVideo ignored: VideoPlayer is null.");
                return;
            }

            if (!isPrepared && !videoPlayer.isPrepared)
            {
                Debug.LogWarning("[VideoPlayback] PlayVideo ignored: video is not prepared yet.");
                return;
            }

            ApplySkyboxOutput();
            videoPlayer.Play();

            if (logVideoEvents)
            {
                Debug.Log(
                    $"[VideoPlayback] Reproducción iniciada. " +
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
                    Debug.Log("[VideoPlayback] Reproducción pausada.");
                }
            }
        }

        public void StopVideo()
        {
            if (videoPlayer != null)
            {
                videoPlayer.Stop();

                if (logVideoEvents)
                {
                    Debug.Log("[VideoPlayback] Reproducción detenida.");
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
    }
}