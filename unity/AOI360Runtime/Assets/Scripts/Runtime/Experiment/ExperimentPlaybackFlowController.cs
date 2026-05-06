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
        private const string TargetSceneName = "Phase0_360Playback_VR";
        private const string RuntimeObjectName = "ExperimentPlaybackFlowController_Runtime";

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
            if (activeScene.name != TargetSceneName)
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
            if (SceneManager.GetActiveScene().name != TargetSceneName)
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

            while (!videoPlayback.IsPrepared || (aoiSequenceRuntimeLoader != null && !aoiSequenceRuntimeLoader.IsSequenceLoaded))
            {
                ResolveReferences();

                string loadingText = videoPlayback.IsPrepared
                    ? "Vídeo listo, esperando AOIs"
                    : "Preparando vídeo";

                SetOverlayState(
                    title: "Preparando experimento",
                    countdown: "…",
                    subtitle: $"{loadingText}: {stimulus.DisplayName}"
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
            videoPlayback.PlayVideo();

            if (dataRecorder != null && !dataRecorder.IsRecording)
            {
                dataRecorder.StartRecording();
            }

            DestroyOverlay();
        }

        private void ResolveReferences()
        {
            if (videoPlayback == null)
            {
                videoPlayback = FindFirstObjectByType<VideoPlayback>();
            }

            if (aoiSequenceRuntimeLoader == null)
            {
                aoiSequenceRuntimeLoader = FindFirstObjectByType<AOISequenceRuntimeLoader>();
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

            GameObject canvasObject = new GameObject(
                "ExperimentCountdownCanvas",
                typeof(Canvas),
                typeof(CanvasScaler),
                typeof(GraphicRaycaster)
            );

            overlayCanvas = canvasObject.GetComponent<Canvas>();
            overlayCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
            overlayCanvas.sortingOrder = 1200;

            CanvasScaler scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1600f, 900f);
            scaler.matchWidthOrHeight = 0.5f;

            RectTransform canvasRect = canvasObject.GetComponent<RectTransform>();

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
                Destroy(overlayCanvas.gameObject);
                overlayCanvas = null;
            }
        }
    }
}
