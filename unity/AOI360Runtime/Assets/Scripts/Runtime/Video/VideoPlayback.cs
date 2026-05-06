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

        [Header("Debug")]
        [SerializeField] private bool logVideoEvents = true;

        [Header("Performance")]
        [SerializeField] private bool allowFrameDrop = true;

        private VideoPlayer videoPlayer;
        private bool isPrepared;
        private string runtimeSelectedVideoPath = string.Empty;
        private string activeVideoPath = string.Empty;

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

            if (skyboxMaterial != null && targetTexture != null)
            {
                skyboxMaterial.SetTexture("_MainTex", targetTexture);
                RenderSettings.skybox = skyboxMaterial;
                DynamicGI.UpdateEnvironment();
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

            if (Application.isEditor && logVideoEvents)
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
                videoPlayer.Play();

                if (Application.isEditor && logVideoEvents)
                {
                    Debug.Log("[VideoPlayback] Reproducción iniciada.");
                }
            }
        }

        private void OnDestroy()
        {
            if (videoPlayer == null)
            {
                return;
            }

            videoPlayer.prepareCompleted -= HandlePrepareCompleted;
            videoPlayer.errorReceived -= HandleErrorReceived;
            videoPlayer.loopPointReached -= HandleLoopPointReached;
        }

        private void HandlePrepareCompleted(VideoPlayer source)
        {
            isPrepared = true;

            if (Application.isEditor && logVideoEvents)
            {
                Debug.Log("[VideoPlayback] Vídeo preparado correctamente.");
            }
        }

        private void HandleErrorReceived(VideoPlayer source, string message)
        {
            Debug.LogError($"[VideoPlayback] Error reproduciendo vídeo: {message}");
        }

        private void HandleLoopPointReached(VideoPlayer source)
        {
            if (Application.isEditor && logVideoEvents)
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
            if (videoPlayer != null && isPrepared)
            {
                videoPlayer.Play();
            }
        }

        public void PauseVideo()
        {
            if (videoPlayer != null)
            {
                videoPlayer.Pause();
            }
        }

        public void StopVideo()
        {
            if (videoPlayer != null)
            {
                videoPlayer.Stop();
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
