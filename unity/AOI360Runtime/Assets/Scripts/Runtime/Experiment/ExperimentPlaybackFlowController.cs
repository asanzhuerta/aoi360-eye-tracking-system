using System.Collections;
using AOI360.Runtime.AOI;
using AOI360.Runtime.Logging;
using AOI360.Runtime.Video;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace AOI360.Runtime.Experiment
{
    [DefaultExecutionOrder(-170)]
    public class ExperimentPlaybackFlowController : MonoBehaviour
    {
        private static readonly string[] TargetSceneNames =
        {
            "Phase0_360Playback_VR_sampleRIG",
            "Phase0_360Playback_VR"
        };
        private const string RuntimeObjectName = "ExperimentPlaybackFlowController_Runtime";

        [Header("Scene References")]
        [SerializeField] private VideoPlayback sceneVideoPlayback;
        [SerializeField] private AOISequenceRuntimeLoader sceneAoiSequenceRuntimeLoader;
        [SerializeField] private DataRecorder sceneDataRecorder;

        [Header("Scene Overlay")]
        [SerializeField] private Canvas sceneOverlayCanvas;
        [SerializeField] private TextMeshProUGUI sceneTitleText;
        [SerializeField] private TextMeshProUGUI sceneCountdownText;
        [SerializeField] private TextMeshProUGUI sceneSubtitleText;

        private VideoPlayback videoPlayback;
        private AOISequenceRuntimeLoader aoiSequenceRuntimeLoader;
        private DataRecorder dataRecorder;

        private Canvas overlayCanvas;
        private TextMeshProUGUI titleText;
        private TextMeshProUGUI countdownText;
        private TextMeshProUGUI subtitleText;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void EnsureController()
        {
            Scene activeScene = SceneManager.GetActiveScene();
            if (!IsTargetScene(activeScene.name))
            {
                return;
            }

            if (FindFirstObjectByType<ExperimentPlaybackFlowController>() != null)
            {
                return;
            }

            GameObject runtimeObject = new GameObject(RuntimeObjectName);
            runtimeObject.AddComponent<ExperimentPlaybackFlowController>();
        }

        private void Awake()
        {
            if (!IsTargetScene(SceneManager.GetActiveScene().name))
            {
                enabled = false;
                return;
            }
        }

        private IEnumerator Start()
        {
            if (!ExperimentSessionState.HasSelectedStimulus)
            {
                yield break;
            }

            ResolveReferences();
            BuildOverlay();

            ExperimentStimulusDefinition stimulus = ExperimentSessionState.SelectedStimulus;
            SetOverlayState(
                title: "Preparando experimento",
                countdown: "…",
                subtitle: $"Cargando {stimulus.DisplayName} y su secuencia AOI"
            );

            while (videoPlayback == null)
            {
                ResolveReferences();
                yield return null;
            }

            float loadingStartedAt = Time.realtimeSinceStartup;
            float maxAoiWaitSeconds = 3f;

            while (!videoPlayback.IsPrepared)
            {
                ResolveReferences();

                SetOverlayState(
                    title: "Preparando experimento",
                    countdown: "…",
                    subtitle: $"Preparando vídeo: {stimulus.DisplayName}"
                );

                yield return null;
            }

            while (aoiSequenceRuntimeLoader != null && !aoiSequenceRuntimeLoader.IsSequenceLoaded)
            {
                ResolveReferences();

                float elapsed = Time.realtimeSinceStartup - loadingStartedAt;
                if (elapsed >= maxAoiWaitSeconds)
                {
                    Debug.LogWarning(
                        $"[ExperimentPlaybackFlowController] AOI sequence not ready after {maxAoiWaitSeconds:0.0}s. " +
                        "Starting video anyway so playback is not blocked."
                    );
                    break;
                }

                SetOverlayState(
                    title: "Preparando experimento",
                    countdown: "…",
                    subtitle: $"Vídeo listo, esperando AOIs: {stimulus.DisplayName}"
                );

                yield return null;
            }

            float remainingSeconds = Mathf.Max(0f, ExperimentSessionState.CountdownSeconds);
            while (remainingSeconds > 0f)
            {
                int visibleSeconds = Mathf.Max(1, Mathf.CeilToInt(remainingSeconds));
                SetOverlayState(
                    title: "El experimento comienza en",
                    countdown: visibleSeconds.ToString(),
                    subtitle: stimulus.VideoFileName
                );

                remainingSeconds -= Time.unscaledDeltaTime;
                yield return null;
            }

            ExperimentSessionState.UnlockPlaybackStart();

            Debug.Log("[ExperimentPlaybackFlowController] Countdown finished. Starting video playback.");
            videoPlayback.PlayVideo();

            if (dataRecorder != null && !dataRecorder.IsRecording)
            {
                dataRecorder.StartRecording();
            }

            DestroyOverlay();
        }

        private void ResolveReferences()
        {
            if (videoPlayback == null && sceneVideoPlayback != null)
            {
                videoPlayback = sceneVideoPlayback;
            }

            if (videoPlayback == null)
            {
                videoPlayback = FindFirstObjectByType<VideoPlayback>();
            }

            if (aoiSequenceRuntimeLoader == null && sceneAoiSequenceRuntimeLoader != null)
            {
                aoiSequenceRuntimeLoader = sceneAoiSequenceRuntimeLoader;
            }

            if (aoiSequenceRuntimeLoader == null)
            {
                aoiSequenceRuntimeLoader = FindFirstObjectByType<AOISequenceRuntimeLoader>();
            }

            if (dataRecorder == null && sceneDataRecorder != null)
            {
                dataRecorder = sceneDataRecorder;
            }

            if (dataRecorder == null)
            {
                dataRecorder = FindFirstObjectByType<DataRecorder>();
            }
        }

        private void BuildOverlay()
        {
            if (overlayCanvas != null)
            {
                return;
            }

            if (sceneOverlayCanvas != null)
            {
                overlayCanvas = sceneOverlayCanvas;
                overlayCanvas.gameObject.SetActive(true);
                if (overlayCanvas.renderMode == RenderMode.WorldSpace && overlayCanvas.worldCamera == null)
                {
                    overlayCanvas.worldCamera = ResolvePresentationCamera();
                }

                titleText = sceneTitleText;
                countdownText = sceneCountdownText;
                subtitleText = sceneSubtitleText;
                return;
            }

            GameObject canvasObject = new GameObject(
                "ExperimentCountdownCanvas",
                typeof(Canvas),
                typeof(CanvasScaler),
                typeof(GraphicRaycaster)
            );

            overlayCanvas = canvasObject.GetComponent<Canvas>();
            overlayCanvas.sortingOrder = 1200;

            CanvasScaler scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1600f, 900f);
            scaler.matchWidthOrHeight = 0.5f;
            scaler.dynamicPixelsPerUnit = 16f;

            RectTransform canvasRect = canvasObject.GetComponent<RectTransform>();
            ConfigureOverlayCanvas(canvasRect);

            RectTransform blocker = ExperimentRuntimeUi.CreateUiObject(
                "Blocker",
                canvasRect,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );
            ExperimentRuntimeUi.AddPanelImage(blocker, new Color(0f, 0f, 0f, 0.78f));

            RectTransform panel = ExperimentRuntimeUi.CreateUiObject(
                "Panel",
                blocker,
                new Vector2(0.5f, 0.5f),
                new Vector2(0.5f, 0.5f)
            );
            panel.sizeDelta = new Vector2(760f, 420f);
            panel.anchoredPosition = Vector2.zero;
            ExperimentRuntimeUi.AddPanelImage(panel, new Color(0.09f, 0.11f, 0.16f, 0.98f));

            titleText = ExperimentRuntimeUi.CreateText(
                "Title",
                panel,
                "Preparando experimento",
                34f,
                FontStyles.Bold,
                TextAlignmentOptions.Center,
                Color.white
            );
            RectTransform titleRect = titleText.rectTransform;
            titleRect.anchorMin = new Vector2(0f, 1f);
            titleRect.anchorMax = new Vector2(1f, 1f);
            titleRect.pivot = new Vector2(0.5f, 1f);
            titleRect.sizeDelta = new Vector2(0f, 88f);
            titleRect.anchoredPosition = new Vector2(0f, -24f);
            titleText.raycastTarget = false;

            countdownText = ExperimentRuntimeUi.CreateText(
                "Countdown",
                panel,
                "…",
                122f,
                FontStyles.Bold,
                TextAlignmentOptions.Center,
                new Color(0.97f, 0.83f, 0.48f, 1f)
            );
            RectTransform countdownRect = countdownText.rectTransform;
            countdownRect.anchorMin = new Vector2(0f, 0.5f);
            countdownRect.anchorMax = new Vector2(1f, 0.5f);
            countdownRect.pivot = new Vector2(0.5f, 0.5f);
            countdownRect.sizeDelta = new Vector2(0f, 160f);
            countdownRect.anchoredPosition = new Vector2(0f, 12f);
            countdownText.raycastTarget = false;

            subtitleText = ExperimentRuntimeUi.CreateText(
                "Subtitle",
                panel,
                string.Empty,
                24f,
                FontStyles.Normal,
                TextAlignmentOptions.Center,
                new Color(0.82f, 0.88f, 0.96f, 0.95f)
            );
            RectTransform subtitleRect = subtitleText.rectTransform;
            subtitleRect.anchorMin = new Vector2(0f, 0f);
            subtitleRect.anchorMax = new Vector2(1f, 0f);
            subtitleRect.pivot = new Vector2(0.5f, 0f);
            subtitleRect.sizeDelta = new Vector2(0f, 96f);
            subtitleRect.anchoredPosition = new Vector2(0f, 28f);
            subtitleText.raycastTarget = false;
        }

        private void SetOverlayState(string title, string countdown, string subtitle)
        {
            if (titleText != null)
            {
                titleText.text = title;
            }

            if (countdownText != null)
            {
                countdownText.text = countdown;
            }

            if (subtitleText != null)
            {
                subtitleText.text = subtitle;
            }
        }

        private void DestroyOverlay()
        {
            if (overlayCanvas != null)
            {
                if (overlayCanvas == sceneOverlayCanvas)
                {
                    overlayCanvas.gameObject.SetActive(false);
                }
                else
                {
                    Destroy(overlayCanvas.gameObject);
                }

                overlayCanvas = null;
            }
        }

        private void ConfigureOverlayCanvas(RectTransform canvasRect)
        {
            Camera presentationCamera = ResolvePresentationCamera();
            if (presentationCamera == null)
            {
                overlayCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
                return;
            }

            overlayCanvas.renderMode = RenderMode.WorldSpace;
            overlayCanvas.worldCamera = presentationCamera;

            canvasRect.SetParent(presentationCamera.transform, false);
            canvasRect.anchorMin = new Vector2(0.5f, 0.5f);
            canvasRect.anchorMax = new Vector2(0.5f, 0.5f);
            canvasRect.pivot = new Vector2(0.5f, 0.5f);
            canvasRect.sizeDelta = new Vector2(1400f, 900f);
            canvasRect.localPosition = new Vector3(0f, 0f, 1.45f);
            canvasRect.localRotation = Quaternion.identity;
            canvasRect.localScale = Vector3.one * 0.00115f;
        }

        private static Camera ResolvePresentationCamera()
        {
            Camera mainCamera = Camera.main;
            if (mainCamera != null && mainCamera.gameObject.activeInHierarchy)
            {
                return mainCamera;
            }

            return FindFirstObjectByType<Camera>();
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
    }
}
