using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.UI;
using UnityEngine.InputSystem.XR;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace AOI360.Runtime.Experiment
{
    [DefaultExecutionOrder(-250)]
    public class ExperimentSelectionSceneController : MonoBehaviour
    {
        private const string TargetSceneName = "SampleScene";
        private const string PlaybackSceneName = "Phase0_360Playback_VR";
        private const string RuntimeObjectName = "ExperimentSelectionSceneController_Runtime";

        private readonly List<GameObject> dynamicUiObjects = new();

        private Canvas rootCanvas;
        private RectTransform listContentRoot;
        private TextMeshProUGUI statusText;
        private TextMeshProUGUI sourceSummaryText;
        private Camera presentationCamera;
        private bool isLoadingSelection;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void EnsureController()
        {
            Scene activeScene = SceneManager.GetActiveScene();
            if (activeScene.name != TargetSceneName)
            {
                return;
            }

            if (FindFirstObjectByType<ExperimentSelectionSceneController>() != null)
            {
                return;
            }

            GameObject runtimeObject = new GameObject(RuntimeObjectName);
            runtimeObject.AddComponent<ExperimentSelectionSceneController>();
        }

        private void Awake()
        {
            if (SceneManager.GetActiveScene().name != TargetSceneName)
            {
                enabled = false;
                return;
            }

            ExperimentSessionState.Clear();
            PreparePointerForSelection();
            EnsureEventSystem();
            presentationCamera = ResolvePresentationCamera();
            EnsureTrackedVrCamera(presentationCamera);
            BuildRuntimeUi();
            PopulateStimulusList();
        }

        private void OnDestroy()
        {
            for (int i = 0; i < dynamicUiObjects.Count; i++)
            {
                GameObject gameObject = dynamicUiObjects[i];
                if (gameObject != null)
                {
                    Destroy(gameObject);
                }
            }

            dynamicUiObjects.Clear();
        }

        private void EnsureEventSystem()
        {
            EventSystem eventSystem = FindFirstObjectByType<EventSystem>();
            InputSystemUIInputModule inputModule = null;

            if (eventSystem == null)
            {
                GameObject eventSystemObject = new GameObject("EventSystem");
                eventSystem = eventSystemObject.AddComponent<EventSystem>();
                inputModule = eventSystemObject.AddComponent<InputSystemUIInputModule>();
                dynamicUiObjects.Add(eventSystemObject);
            }
            else
            {
                inputModule = eventSystem.GetComponent<InputSystemUIInputModule>();
            }

            if (inputModule == null)
            {
                inputModule = eventSystem.gameObject.AddComponent<InputSystemUIInputModule>();
            }

            if (inputModule.actionsAsset == null)
            {
                inputModule.AssignDefaultActions();
            }

            inputModule.deselectOnBackgroundClick = true;
            eventSystem.sendNavigationEvents = true;
        }

        private static void PreparePointerForSelection()
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
        }

        private void BuildRuntimeUi()
        {
            GameObject canvasObject = new GameObject(
                "ExperimentSelectionCanvas",
                typeof(Canvas),
                typeof(CanvasScaler),
                typeof(GraphicRaycaster)
            );
            dynamicUiObjects.Add(canvasObject);

            rootCanvas = canvasObject.GetComponent<Canvas>();
            rootCanvas.sortingOrder = 1000;

            CanvasScaler scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1600f, 900f);
            scaler.matchWidthOrHeight = 0.5f;

            RectTransform canvasRect = canvasObject.GetComponent<RectTransform>();
            ConfigurePresentationCanvas(canvasObject, canvasRect);

            RectTransform background = ExperimentRuntimeUi.CreateUiObject(
                "Background",
                canvasRect,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );
            Image backgroundImage = ExperimentRuntimeUi.AddPanelImage(background, new Color(0.06f, 0.07f, 0.1f, 0.96f));
            backgroundImage.raycastTarget = false;

            RectTransform modal = ExperimentRuntimeUi.CreateUiObject(
                "Modal",
                background,
                new Vector2(0.5f, 0.5f),
                new Vector2(0.5f, 0.5f)
            );
            modal.sizeDelta = new Vector2(1080f, 760f);
            modal.anchoredPosition = Vector2.zero;
            Image modalImage = ExperimentRuntimeUi.AddPanelImage(modal, new Color(0.13f, 0.15f, 0.2f, 0.98f));
            modalImage.raycastTarget = false;

            Outline outline = modal.gameObject.AddComponent<Outline>();
            outline.effectColor = new Color(0.27f, 0.36f, 0.5f, 0.65f);
            outline.effectDistance = new Vector2(1f, -1f);

            TextMeshProUGUI titleText = ExperimentRuntimeUi.CreateText(
                "Title",
                modal,
                "Selecciona el vídeo del experimento",
                40f,
                FontStyles.Bold,
                TextAlignmentOptions.MidlineLeft,
                Color.white
            );
            RectTransform titleRect = titleText.rectTransform;
            titleRect.anchorMin = new Vector2(0f, 1f);
            titleRect.anchorMax = new Vector2(1f, 1f);
            titleRect.pivot = new Vector2(0.5f, 1f);
            titleRect.sizeDelta = new Vector2(0f, 86f);
            titleRect.anchoredPosition = new Vector2(0f, -12f);
            titleText.raycastTarget = false;

            TextMeshProUGUI subtitleText = ExperimentRuntimeUi.CreateText(
                "Subtitle",
                modal,
                "Se muestran solo los estímulos que tienen vídeo y AOIs listos. El catálogo prioriza `data/` y usa `StreamingAssets` como respaldo.",
                22f,
                FontStyles.Normal,
                TextAlignmentOptions.TopLeft,
                new Color(0.82f, 0.87f, 0.96f, 0.92f)
            );
            RectTransform subtitleRect = subtitleText.rectTransform;
            subtitleRect.anchorMin = new Vector2(0f, 1f);
            subtitleRect.anchorMax = new Vector2(1f, 1f);
            subtitleRect.pivot = new Vector2(0.5f, 1f);
            subtitleRect.sizeDelta = new Vector2(0f, 86f);
            subtitleRect.anchoredPosition = new Vector2(0f, -92f);
            subtitleText.raycastTarget = false;

            RectTransform listPanel = ExperimentRuntimeUi.CreateUiObject(
                "ListPanel",
                modal,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );
            listPanel.offsetMin = new Vector2(36f, 110f);
            listPanel.offsetMax = new Vector2(-36f, -188f);
            Image listPanelImage = ExperimentRuntimeUi.AddPanelImage(listPanel, new Color(0.08f, 0.09f, 0.13f, 0.98f));
            listPanelImage.raycastTarget = false;

            ScrollRect scrollRect = listPanel.gameObject.AddComponent<ScrollRect>();
            scrollRect.horizontal = false;
            scrollRect.vertical = true;
            scrollRect.scrollSensitivity = 32f;

            RectTransform viewport = ExperimentRuntimeUi.CreateUiObject(
                "Viewport",
                listPanel,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );
            viewport.offsetMin = new Vector2(16f, 16f);
            viewport.offsetMax = new Vector2(-16f, -16f);
            Image viewportImage = ExperimentRuntimeUi.AddPanelImage(viewport, new Color(0f, 0f, 0f, 0f));
            viewportImage.raycastTarget = false;
            Mask viewportMask = viewport.gameObject.AddComponent<Mask>();
            viewportMask.showMaskGraphic = false;

            listContentRoot = ExperimentRuntimeUi.CreateUiObject(
                "Content",
                viewport,
                new Vector2(0f, 1f),
                new Vector2(1f, 1f)
            );
            listContentRoot.pivot = new Vector2(0.5f, 1f);
            listContentRoot.anchoredPosition = Vector2.zero;
            listContentRoot.sizeDelta = new Vector2(0f, 0f);

            VerticalLayoutGroup layoutGroup = listContentRoot.gameObject.AddComponent<VerticalLayoutGroup>();
            layoutGroup.padding = new RectOffset(0, 0, 0, 0);
            layoutGroup.spacing = 14f;
            layoutGroup.childControlWidth = true;
            layoutGroup.childControlHeight = true;
            layoutGroup.childForceExpandWidth = true;
            layoutGroup.childForceExpandHeight = false;

            ContentSizeFitter contentSizeFitter = listContentRoot.gameObject.AddComponent<ContentSizeFitter>();
            contentSizeFitter.horizontalFit = ContentSizeFitter.FitMode.Unconstrained;
            contentSizeFitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            scrollRect.viewport = viewport;
            scrollRect.content = listContentRoot;
            scrollRect.movementType = ScrollRect.MovementType.Clamped;

            sourceSummaryText = ExperimentRuntimeUi.CreateText(
                "SourceSummary",
                modal,
                string.Empty,
                20f,
                FontStyles.Normal,
                TextAlignmentOptions.BottomLeft,
                new Color(0.78f, 0.84f, 0.93f, 0.95f)
            );
            RectTransform sourceSummaryRect = sourceSummaryText.rectTransform;
            sourceSummaryRect.anchorMin = new Vector2(0f, 0f);
            sourceSummaryRect.anchorMax = new Vector2(1f, 0f);
            sourceSummaryRect.pivot = new Vector2(0.5f, 0f);
            sourceSummaryRect.sizeDelta = new Vector2(0f, 76f);
            sourceSummaryRect.anchoredPosition = new Vector2(0f, 92f);
            sourceSummaryText.raycastTarget = false;

            statusText = ExperimentRuntimeUi.CreateText(
                "Status",
                modal,
                "Esperando selección…",
                22f,
                FontStyles.Bold,
                TextAlignmentOptions.BottomLeft,
                new Color(0.96f, 0.82f, 0.48f, 1f)
            );
            RectTransform statusRect = statusText.rectTransform;
            statusRect.anchorMin = new Vector2(0f, 0f);
            statusRect.anchorMax = new Vector2(1f, 0f);
            statusRect.pivot = new Vector2(0.5f, 0f);
            statusRect.sizeDelta = new Vector2(0f, 76f);
            statusRect.anchoredPosition = new Vector2(0f, 24f);
            statusText.raycastTarget = false;

            Button refreshButton = ExperimentRuntimeUi.CreateButton(
                "RefreshButton",
                modal,
                new Color(0.2f, 0.34f, 0.54f, 0.96f)
            );
            RectTransform refreshRect = refreshButton.GetComponent<RectTransform>();
            refreshRect.anchorMin = new Vector2(1f, 0f);
            refreshRect.anchorMax = new Vector2(1f, 0f);
            refreshRect.pivot = new Vector2(1f, 0f);
            refreshRect.sizeDelta = new Vector2(196f, 56f);
            refreshRect.anchoredPosition = new Vector2(-32f, 28f);

            TextMeshProUGUI refreshLabel = ExperimentRuntimeUi.CreateText(
                "Label",
                refreshButton.transform,
                "Recargar lista",
                20f,
                FontStyles.Bold,
                TextAlignmentOptions.Center,
                Color.white
            );
            refreshLabel.raycastTarget = false;
            refreshButton.onClick.AddListener(PopulateStimulusList);
        }

        private void ConfigurePresentationCanvas(GameObject canvasObject, RectTransform canvasRect)
        {
            GraphicRaycaster graphicRaycaster = canvasObject.GetComponent<GraphicRaycaster>();
            graphicRaycaster.ignoreReversedGraphics = true;

            if (presentationCamera == null)
            {
                rootCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
                return;
            }

            rootCanvas.renderMode = RenderMode.WorldSpace;
            rootCanvas.worldCamera = presentationCamera;

            if (canvasObject.GetComponent<TrackedDeviceRaycaster>() == null)
            {
                canvasObject.AddComponent<TrackedDeviceRaycaster>();
            }

            canvasRect.SetParent(presentationCamera.transform, false);
            canvasRect.anchorMin = new Vector2(0.5f, 0.5f);
            canvasRect.anchorMax = new Vector2(0.5f, 0.5f);
            canvasRect.pivot = new Vector2(0.5f, 0.5f);
            canvasRect.sizeDelta = new Vector2(1600f, 900f);
            canvasRect.localPosition = new Vector3(0f, -0.04f, 2.35f);
            canvasRect.localRotation = Quaternion.identity;
            canvasRect.localScale = Vector3.one * 0.00145f;
        }

        private static Camera ResolvePresentationCamera()
        {
            return Camera.main ?? FindFirstObjectByType<Camera>();
        }

        private static void EnsureTrackedVrCamera(Camera camera)
        {
            if (camera == null)
            {
                return;
            }

            if (camera.GetComponent<UnityEngine.SpatialTracking.TrackedPoseDriver>() != null)
            {
                return;
            }

            if (camera.GetComponent<TrackedPoseDriver>() != null)
            {
                return;
            }

            if (InputSystem.GetDevice<XRHMD>() == null)
            {
                return;
            }

            TrackedPoseDriver trackedPoseDriver = camera.gameObject.AddComponent<TrackedPoseDriver>();
            trackedPoseDriver.trackingType = TrackedPoseDriver.TrackingType.RotationAndPosition;
            trackedPoseDriver.updateType = TrackedPoseDriver.UpdateType.UpdateAndBeforeRender;
            trackedPoseDriver.ignoreTrackingState = true;
            trackedPoseDriver.positionInput = new InputActionProperty(
                new InputAction(
                    name: "SelectionHmdPosition",
                    type: InputActionType.PassThrough,
                    binding: "<XRHMD>/centerEyePosition",
                    expectedControlType: "Vector3"
                )
            );
            trackedPoseDriver.rotationInput = new InputActionProperty(
                new InputAction(
                    name: "SelectionHmdRotation",
                    type: InputActionType.PassThrough,
                    binding: "<XRHMD>/centerEyeRotation",
                    expectedControlType: "Quaternion"
                )
            );
        }

        private void PopulateStimulusList()
        {
            if (listContentRoot == null)
            {
                return;
            }

            for (int i = listContentRoot.childCount - 1; i >= 0; i--)
            {
                Destroy(listContentRoot.GetChild(i).gameObject);
            }

            IReadOnlyList<ExperimentStimulusDefinition> stimuli = ExperimentStimulusCatalog.DiscoverAvailableStimuli();
            int repositoryCount = 0;
            int streamingCount = 0;

            for (int i = 0; i < stimuli.Count; i++)
            {
                ExperimentStimulusDefinition stimulus = stimuli[i];
                if (stimulus.SourceKind == ExperimentStimulusSourceKind.RepositoryData)
                {
                    repositoryCount++;
                }
                else
                {
                    streamingCount++;
                }

                CreateStimulusButton(stimulus);
            }

            if (sourceSummaryText != null)
            {
                sourceSummaryText.text = stimuli.Count > 0
                    ? $"Estímulos disponibles: {stimuli.Count} | repo: {repositoryCount} | mirror: {streamingCount}"
                    : "No se ha encontrado ningún estímulo listo.";
            }

            if (statusText != null)
            {
                statusText.text = stimuli.Count > 0
                    ? "Selecciona un vídeo para abrir la escena VR y lanzar la cuenta atrás."
                    : "No hay vídeos listos. Revisa `data/input_videos` y `data/processed`, o sincroniza `StreamingAssets`.";
            }

            if (stimuli.Count == 0)
            {
                RectTransform emptyState = ExperimentRuntimeUi.CreateUiObject(
                    "EmptyState",
                    listContentRoot,
                    new Vector2(0f, 0f),
                    new Vector2(1f, 0f)
                );
                emptyState.anchorMin = new Vector2(0f, 1f);
                emptyState.anchorMax = new Vector2(1f, 1f);
                emptyState.pivot = new Vector2(0.5f, 1f);
                emptyState.sizeDelta = new Vector2(0f, 180f);
                LayoutElement emptyLayout = emptyState.gameObject.AddComponent<LayoutElement>();
                emptyLayout.preferredHeight = 180f;
                ExperimentRuntimeUi.AddPanelImage(emptyState, new Color(0.16f, 0.11f, 0.11f, 0.95f));

                TextMeshProUGUI emptyText = ExperimentRuntimeUi.CreateText(
                    "EmptyLabel",
                    emptyState,
                    "No hay nada seleccionable todavía.\n\nGenera un vídeo preprocesado con la pipeline y, si vas a usar build o `StreamingAssets`, ejecuta la sincronización desde `Tools/AOI`.",
                    22f,
                    FontStyles.Normal,
                    TextAlignmentOptions.Center,
                    new Color(1f, 0.9f, 0.86f, 1f)
                );
                emptyText.raycastTarget = false;
            }

            Canvas.ForceUpdateCanvases();
            LayoutRebuilder.ForceRebuildLayoutImmediate(listContentRoot);
        }

        private void CreateStimulusButton(ExperimentStimulusDefinition stimulus)
        {
            Button button = ExperimentRuntimeUi.CreateButton(
                $"StimulusButton_{stimulus.SequenceName}",
                listContentRoot,
                new Color(0.16f, 0.2f, 0.28f, 0.98f)
            );
            RectTransform buttonRect = button.GetComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0f, 1f);
            buttonRect.anchorMax = new Vector2(1f, 1f);
            buttonRect.pivot = new Vector2(0.5f, 1f);
            buttonRect.sizeDelta = new Vector2(0f, 94f);

            LayoutElement layoutElement = button.gameObject.AddComponent<LayoutElement>();
            layoutElement.preferredHeight = 94f;
            layoutElement.minHeight = 94f;

            VerticalLayoutGroup layoutGroup = button.gameObject.AddComponent<VerticalLayoutGroup>();
            layoutGroup.padding = new RectOffset(24, 24, 16, 16);
            layoutGroup.spacing = 4f;
            layoutGroup.childControlWidth = true;
            layoutGroup.childControlHeight = false;
            layoutGroup.childForceExpandWidth = true;
            layoutGroup.childForceExpandHeight = false;

            TextMeshProUGUI title = ExperimentRuntimeUi.CreateText(
                "Title",
                button.transform,
                stimulus.DisplayName,
                28f,
                FontStyles.Bold,
                TextAlignmentOptions.Left,
                Color.white
            );
            title.raycastTarget = false;
            LayoutElement titleLayout = title.gameObject.AddComponent<LayoutElement>();
            titleLayout.preferredHeight = 34f;

            string detailText =
                $"{stimulus.VideoFileName} | secuencia: {stimulus.SequenceName} | origen: {stimulus.SourceLabel}";
            TextMeshProUGUI details = ExperimentRuntimeUi.CreateText(
                "Details",
                button.transform,
                detailText,
                18f,
                FontStyles.Normal,
                TextAlignmentOptions.Left,
                new Color(0.82f, 0.88f, 0.96f, 0.96f)
            );
            details.raycastTarget = false;
            LayoutElement detailsLayout = details.gameObject.AddComponent<LayoutElement>();
            detailsLayout.preferredHeight = 24f;

            button.onClick.AddListener(() => SelectStimulus(stimulus));
        }

        private void SelectStimulus(ExperimentStimulusDefinition stimulus)
        {
            if (isLoadingSelection)
            {
                return;
            }

            isLoadingSelection = true;
            ExperimentSessionState.SetSelectedStimulus(stimulus, lockPlaybackStart: true, countdownSeconds: 5f);

            if (statusText != null)
            {
                statusText.text = $"Abriendo experimento para: {stimulus.DisplayName}";
            }

            SceneManager.LoadScene(PlaybackSceneName);
        }
    }
}
