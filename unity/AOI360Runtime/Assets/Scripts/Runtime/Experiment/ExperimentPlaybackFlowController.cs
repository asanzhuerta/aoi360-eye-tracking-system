using System.Collections;
using System.Text;
using AOI360.Runtime.AOI;
using AOI360.Runtime.Logging;
using AOI360.Runtime.Video;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace AOI360.Runtime.Experiment
{
    [DefaultExecutionOrder(-170)]
    public class ExperimentPlaybackFlowController : MonoBehaviour
    {
        private static readonly string[] TargetSceneNames =
        {
            "Phase0_360Playback_VR_sampleRIG"
        };

        private const string RuntimeObjectName = "ExperimentPlaybackFlowController_Runtime";
        private const float MaxVideoWaitAfterCountdownSeconds = 8f;
        private const float MaxAoiPrimeWaitAfterCountdownSeconds = 1.5f;
        private const float OverlayDynamicPixelsPerUnit = 96f;
        private const float OverlayReferencePixelsPerUnit = 100f;
        private const float ReturnToSelectionDelaySeconds = 5f;
        private const string EndExperimentMessage = "Experimento finalizado";
        private const string SelectionSceneName = "Initial_Scene";

        private static bool sceneHookRegistered;

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
        private InputAction endExperimentAction;
        private bool hasExperimentFinished;
        private Coroutine returnToSelectionCoroutine;

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
        private static void EnsureControllerAfterSceneLoad()
        {
            EnsureControllerForScene(SceneManager.GetActiveScene());
        }

        private static void HandleSceneLoaded(Scene scene, LoadSceneMode loadMode)
        {
            EnsureControllerForScene(scene);
        }

        private static void EnsureControllerForScene(Scene scene)
        {
            if (!IsTargetScene(scene.name))
            {
                return;
            }

            if (FindFirstObjectByType<ExperimentPlaybackFlowController>() != null)
            {
                return;
            }

            GameObject runtimeObject = new GameObject(RuntimeObjectName);
            runtimeObject.AddComponent<ExperimentPlaybackFlowController>();
            Debug.Log($"[ExperimentPlaybackFlowController] Runtime controller created for scene '{scene.name}'.");
        }

        private void Awake()
        {
            if (!IsTargetScene(SceneManager.GetActiveScene().name))
            {
                enabled = false;
                return;
            }

            ConfigureEndExperimentAction();
            Debug.Log($"[ExperimentPlaybackFlowController] Awake in scene '{SceneManager.GetActiveScene().name}'.");
        }

        private void Update()
        {
            if (hasExperimentFinished)
            {
                return;
            }

            ResolveReferences();

            if (videoPlayback != null && videoPlayback.HasReachedPlaybackEnd)
            {
                Debug.Log("[ExperimentPlaybackFlowController] Video playback reached its natural end.");
                FinishExperiment();
                return;
            }

            if (endExperimentAction != null && endExperimentAction.WasPressedThisFrame())
            {
                Debug.Log("[ExperimentPlaybackFlowController] End experiment action detected in Update.");
                FinishExperiment();
            }
        }

        private IEnumerator Start()
        {
            if (!ExperimentSessionState.HasSelectedStimulus)
            {
                Debug.LogWarning("[ExperimentPlaybackFlowController] No selected stimulus was found. Countdown flow cancelled.");
                yield break;
            }

            ResolveReferences();
            BuildOverlay();

            ExperimentStimulusDefinition stimulus = ExperimentSessionState.SelectedStimulus;
            float countdownDuration = Mathf.Max(0f, ExperimentSessionState.CountdownSeconds);
            float countdownEndTime = Time.unscaledTime + countdownDuration;
            float postCountdownWaitStartedAt = -1f;
            bool startedWithoutPrimedAoi = false;

            while (true)
            {
                ResolveReferences();
                videoPlayback?.BeginPrepareIfNeeded();

                bool hasVideoPlayback = videoPlayback != null;
                bool videoReady = hasVideoPlayback && videoPlayback.IsPrepared;
                bool videoFailed = hasVideoPlayback && videoPlayback.HasPreparationFailed;
                bool aoiSequenceReady = aoiSequenceRuntimeLoader == null || aoiSequenceRuntimeLoader.IsSequenceLoaded;
                bool aoiPrimeReady = aoiSequenceRuntimeLoader == null || aoiSequenceRuntimeLoader.HasPrimedInitialFrame;
                bool countdownFinished = Time.unscaledTime >= countdownEndTime;

                if (videoFailed)
                {
                    string failureSubtitle = BuildFailureSubtitle(stimulus);
                    SetOverlayState("No se pudo iniciar el experimento", "!", failureSubtitle);
                    Debug.LogError($"[ExperimentPlaybackFlowController] {failureSubtitle}");
                    yield break;
                }

                if (!countdownFinished)
                {
                    int visibleSeconds = Mathf.Max(1, Mathf.CeilToInt(countdownEndTime - Time.unscaledTime));
                    SetOverlayState(
                        title: "El experimento comienza en",
                        countdown: visibleSeconds.ToString(),
                        subtitle: BuildPreparationSubtitle(
                            stimulus,
                            hasVideoPlayback,
                            videoReady,
                            aoiSequenceReady,
                            aoiPrimeReady,
                            waitingAfterCountdown: false
                        )
                    );

                    yield return null;
                    continue;
                }

                if (videoReady && aoiSequenceReady && aoiPrimeReady)
                {
                    break;
                }

                if (postCountdownWaitStartedAt < 0f)
                {
                    postCountdownWaitStartedAt = Time.unscaledTime;
                }

                float postCountdownWait = Time.unscaledTime - postCountdownWaitStartedAt;
                if (videoReady && aoiSequenceReady && !aoiPrimeReady && postCountdownWait >= MaxAoiPrimeWaitAfterCountdownSeconds)
                {
                    startedWithoutPrimedAoi = true;
                    Debug.LogWarning(
                        "[ExperimentPlaybackFlowController] AOI initial frame was not primed in time. " +
                        "Starting playback anyway to avoid blocking the experiment."
                    );
                    break;
                }

                if (!videoReady && postCountdownWait >= MaxVideoWaitAfterCountdownSeconds)
                {
                    string failureSubtitle = BuildFailureSubtitle(stimulus);
                    SetOverlayState("No se pudo iniciar el experimento", "!", failureSubtitle);
                    Debug.LogError($"[ExperimentPlaybackFlowController] Video preparation timed out. {failureSubtitle}");
                    yield break;
                }

                SetOverlayState(
                    title: "Preparando experimento",
                    countdown: "0",
                    subtitle: BuildPreparationSubtitle(
                        stimulus,
                        hasVideoPlayback,
                        videoReady,
                        aoiSequenceReady,
                        aoiPrimeReady,
                        waitingAfterCountdown: true
                    )
                );

                yield return null;
            }

            ExperimentSessionState.UnlockPlaybackStart();

            Debug.Log(
                $"[ExperimentPlaybackFlowController] Countdown finished. Starting video playback. " +
                $"startedWithoutPrimedAoi={startedWithoutPrimedAoi}"
            );

            videoPlayback?.SetLoop(false);
            videoPlayback?.PlayVideo();

            if (dataRecorder != null && !dataRecorder.IsRecording)
            {
                dataRecorder.StartRecording();
            }

            DestroyOverlay();
        }

        private void OnDestroy()
        {
            if (endExperimentAction != null)
            {
                endExperimentAction.performed -= HandleEndExperimentPerformed;
                endExperimentAction.Disable();
                endExperimentAction.Dispose();
                endExperimentAction = null;
            }
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

                CanvasScaler sceneScaler = overlayCanvas.GetComponent<CanvasScaler>();
                if (sceneScaler != null)
                {
                    sceneScaler.referencePixelsPerUnit = OverlayReferencePixelsPerUnit;
                    sceneScaler.dynamicPixelsPerUnit = Mathf.Max(sceneScaler.dynamicPixelsPerUnit, OverlayDynamicPixelsPerUnit);
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
            overlayCanvas.overrideSorting = true;

            CanvasScaler scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1600f, 900f);
            scaler.referencePixelsPerUnit = OverlayReferencePixelsPerUnit;
            scaler.matchWidthOrHeight = 0.5f;
            scaler.dynamicPixelsPerUnit = OverlayDynamicPixelsPerUnit;

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
            panel.sizeDelta = new Vector2(780f, 440f);
            panel.anchoredPosition = Vector2.zero;
            ExperimentRuntimeUi.AddPanelImage(panel, new Color(0.09f, 0.11f, 0.16f, 0.98f));

            titleText = ExperimentRuntimeUi.CreateText(
                "Title",
                panel,
                "Preparando experimento",
                36f,
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
                "...",
                130f,
                FontStyles.Bold,
                TextAlignmentOptions.Center,
                new Color(0.97f, 0.83f, 0.48f, 1f)
            );
            RectTransform countdownRect = countdownText.rectTransform;
            countdownRect.anchorMin = new Vector2(0f, 0.5f);
            countdownRect.anchorMax = new Vector2(1f, 0.5f);
            countdownRect.pivot = new Vector2(0.5f, 0.5f);
            countdownRect.sizeDelta = new Vector2(0f, 170f);
            countdownRect.anchoredPosition = new Vector2(0f, 14f);
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
            subtitleRect.sizeDelta = new Vector2(0f, 104f);
            subtitleRect.anchoredPosition = new Vector2(0f, 28f);
            subtitleText.raycastTarget = false;
        }

        private string BuildPreparationSubtitle(
            ExperimentStimulusDefinition stimulus,
            bool hasVideoPlayback,
            bool videoReady,
            bool aoiSequenceReady,
            bool aoiPrimeReady,
            bool waitingAfterCountdown
        )
        {
            StringBuilder builder = new StringBuilder();

            if (stimulus != null)
            {
                builder.Append(stimulus.DisplayName);

                if (!string.IsNullOrWhiteSpace(stimulus.VideoFileName))
                {
                    builder.Append(" | ");
                    builder.Append(stimulus.VideoFileName);
                }
            }

            if (builder.Length > 0)
            {
                builder.Append(" | ");
            }

            if (!hasVideoPlayback)
            {
                builder.Append("buscando reproductor");
            }
            else if (!videoReady)
            {
                builder.Append(waitingAfterCountdown ? "terminando de preparar video" : "preparando video");
            }
            else
            {
                builder.Append("video listo");
            }

            if (aoiSequenceRuntimeLoader != null)
            {
                builder.Append(" | ");

                if (!aoiSequenceReady)
                {
                    builder.Append("cargando secuencia AOI");
                }
                else if (!aoiPrimeReady)
                {
                    builder.Append("precargando AOI inicial");
                }
                else
                {
                    builder.Append("AOIs listos");
                }
            }

            return builder.ToString();
        }

        private string BuildFailureSubtitle(ExperimentStimulusDefinition stimulus)
        {
            StringBuilder builder = new StringBuilder();

            if (stimulus != null)
            {
                builder.Append(stimulus.DisplayName);
            }
            else
            {
                builder.Append("Stimulus");
            }

            builder.Append(" | ");

            if (videoPlayback == null)
            {
                builder.Append("No se encontro VideoPlayback en la escena.");
            }
            else if (!string.IsNullOrWhiteSpace(videoPlayback.LastPrepareErrorMessage))
            {
                builder.Append(videoPlayback.LastPrepareErrorMessage);
            }
            else
            {
                builder.Append("No se pudo preparar el video.");
            }

            return builder.ToString();
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

        private void ConfigureEndExperimentAction()
        {
            if (endExperimentAction != null)
            {
                return;
            }

            endExperimentAction = new InputAction(
                name: "EndExperiment",
                type: InputActionType.Button
            );
            endExperimentAction.AddBinding("<XRController>{RightHand}/primaryButton");
            endExperimentAction.AddBinding("<XRController>{RightHand}/secondaryButton");
            endExperimentAction.AddBinding("<XRController>{RightHand}/menuButton");
            endExperimentAction.AddBinding("<XRController>/primaryButton");
            endExperimentAction.AddBinding("<XRController>/secondaryButton");
            endExperimentAction.AddBinding("<Joystick>/button0");
            endExperimentAction.AddBinding("<Gamepad>/buttonSouth");
            endExperimentAction.AddBinding("<Keyboard>/escape");
            endExperimentAction.performed += HandleEndExperimentPerformed;
            endExperimentAction.Enable();
        }

        private void HandleEndExperimentPerformed(InputAction.CallbackContext context)
        {
            if (hasExperimentFinished)
            {
                return;
            }

            string controlPath = context.control != null ? context.control.path : "unknown-control";
            Debug.Log($"[ExperimentPlaybackFlowController] End experiment action performed by: {controlPath}");
            FinishExperiment();
        }

        private void FinishExperiment()
        {
            if (hasExperimentFinished)
            {
                return;
            }

            hasExperimentFinished = true;
            ExperimentSessionState.LockPlaybackStart();

            videoPlayback?.StopVideo();

            if (dataRecorder != null)
            {
                if (dataRecorder.IsRecording)
                {
                    dataRecorder.StopRecording();
                }

                dataRecorder.ExportCsv(allowHeaderOnly: true);
            }

            BuildOverlay();
            SetOverlayState(
                EndExperimentMessage,
                string.Empty,
                BuildCompletionSubtitle()
            );

            if (returnToSelectionCoroutine == null)
            {
                returnToSelectionCoroutine = StartCoroutine(ReturnToSelectionAfterDelay());
            }

            Debug.Log("[ExperimentPlaybackFlowController] Experiment finished. Returning to the initial scene shortly.");
        }

        private string BuildCompletionSubtitle()
        {
            if (dataRecorder == null || string.IsNullOrWhiteSpace(dataRecorder.LastExportPath))
            {
                return $"El video se ha detenido y la sesion ha quedado cerrada.\nVolviendo al menu inicial en {ReturnToSelectionDelaySeconds:0} segundos.";
            }

            return $"CSV exportado en: {dataRecorder.LastExportPath}\nVolviendo al menu inicial en {ReturnToSelectionDelaySeconds:0} segundos.";
        }

        private IEnumerator ReturnToSelectionAfterDelay()
        {
            yield return new WaitForSecondsRealtime(ReturnToSelectionDelaySeconds);
            ExperimentSessionState.Clear();
            SceneManager.LoadScene(SelectionSceneName);
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
