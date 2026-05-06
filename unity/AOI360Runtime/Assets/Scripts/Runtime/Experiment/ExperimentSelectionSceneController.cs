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
        private static readonly string[] TargetSceneNames = { "Initial_Scene", "SampleScene" };
        private static readonly string[] PlaybackSceneCandidates =
        {
            "Phase0_360Playback_VR_sampleRIG",
            "Phase0_360Playback_VR"
        };

        private const string RuntimeObjectName = "ExperimentSelectionSceneController_Runtime";

        [Header("Scene UI")]
        [SerializeField] private bool preferSceneUi = true;
        [SerializeField] private Canvas sceneCanvas;
        [SerializeField] private RectTransform sceneListContentRoot;
        [SerializeField] private Button sceneStimulusButtonTemplate;
        [SerializeField] private TextMeshProUGUI sceneStatusText;
        [SerializeField] private TextMeshProUGUI sceneSourceSummaryText;
        [SerializeField] private Button sceneRefreshButton;

        private readonly List<GameObject> dynamicUiObjects = new();

        private Canvas rootCanvas;
        private RectTransform listContentRoot;
        private TextMeshProUGUI statusText;
        private TextMeshProUGUI sourceSummaryText;
        private Camera presentationCamera;
        private bool isLoadingSelection;
        private InputActionAsset runtimeUiActionsAsset;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void EnsureController()
        {
            Scene activeScene = SceneManager.GetActiveScene();
            if (!IsSelectionScene(activeScene.name))
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
            if (!IsSelectionScene(SceneManager.GetActiveScene().name))
            {
                enabled = false;
                return;
            }

            ExperimentSessionState.Clear();
            PreparePointerForSelection();
            EnsureEventSystem();
            presentationCamera = ResolvePresentationCamera();
            EnsureTrackedVrCamera(presentationCamera);
            ResolveSceneUiReferences();

            if (!TryUseSceneUi())
            {
                BuildRuntimeUi();
            }

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

            if (runtimeUiActionsAsset != null)
            {
                runtimeUiActionsAsset.Disable();
                Destroy(runtimeUiActionsAsset);
                runtimeUiActionsAsset = null;
            }
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

            ConfigureEventSystemInput(inputModule);
            inputModule.deselectOnBackgroundClick = true;
            inputModule.pointerBehavior = UIPointerBehavior.SingleMouseOrPenButMultiTouchAndTrack;
            eventSystem.sendNavigationEvents = true;
        }

        private void ConfigureEventSystemInput(InputSystemUIInputModule inputModule)
        {
            if (inputModule == null)
            {
                return;
            }

            if (runtimeUiActionsAsset == null)
            {
                runtimeUiActionsAsset = BuildRuntimeUiActionsAsset();
            }

            InputActionMap uiMap = runtimeUiActionsAsset.FindActionMap("RuntimeUI", throwIfNotFound: true);

            inputModule.actionsAsset = runtimeUiActionsAsset;
            inputModule.point = InputActionReference.Create(uiMap.FindAction("Point", throwIfNotFound: true));
            inputModule.leftClick = InputActionReference.Create(uiMap.FindAction("LeftClick", throwIfNotFound: true));
            inputModule.middleClick = InputActionReference.Create(uiMap.FindAction("MiddleClick", throwIfNotFound: true));
            inputModule.rightClick = InputActionReference.Create(uiMap.FindAction("RightClick", throwIfNotFound: true));
            inputModule.scrollWheel = InputActionReference.Create(uiMap.FindAction("ScrollWheel", throwIfNotFound: true));
            inputModule.move = InputActionReference.Create(uiMap.FindAction("Move", throwIfNotFound: true));
            inputModule.submit = InputActionReference.Create(uiMap.FindAction("Submit", throwIfNotFound: true));
            inputModule.cancel = InputActionReference.Create(uiMap.FindAction("Cancel", throwIfNotFound: true));
            inputModule.trackedDevicePosition = InputActionReference.Create(
                uiMap.FindAction("TrackedDevicePosition", throwIfNotFound: true)
            );
            inputModule.trackedDeviceOrientation = InputActionReference.Create(
                uiMap.FindAction("TrackedDeviceOrientation", throwIfNotFound: true)
            );

            runtimeUiActionsAsset.Enable();
        }

        private static InputActionAsset BuildRuntimeUiActionsAsset()
        {
            InputActionAsset asset = ScriptableObject.CreateInstance<InputActionAsset>();
            asset.name = "RuntimeSelectionUiActions";

            InputActionMap map = new InputActionMap("RuntimeUI");

            InputAction pointAction = map.AddAction(
                "Point",
                InputActionType.PassThrough
            );
            pointAction.expectedControlType = "Vector2";
            pointAction.AddBinding("<Mouse>/position");

            InputAction leftClickAction = map.AddAction(
                "LeftClick",
                InputActionType.PassThrough
            );
            leftClickAction.expectedControlType = "Button";
            leftClickAction.AddBinding("<Mouse>/leftButton");
            leftClickAction.AddBinding("<XRController>/triggerPressed");
            leftClickAction.AddBinding("<XRController>{LeftHand}/triggerPressed");
            leftClickAction.AddBinding("<XRController>{RightHand}/triggerPressed");

            InputAction middleClickAction = map.AddAction(
                "MiddleClick",
                InputActionType.PassThrough
            );
            middleClickAction.expectedControlType = "Button";
            middleClickAction.AddBinding("<Mouse>/middleButton");

            InputAction rightClickAction = map.AddAction(
                "RightClick",
                InputActionType.PassThrough
            );
            rightClickAction.expectedControlType = "Button";
            rightClickAction.AddBinding("<Mouse>/rightButton");

            InputAction scrollWheelAction = map.AddAction(
                "ScrollWheel",
                InputActionType.PassThrough
            );
            scrollWheelAction.expectedControlType = "Vector2";
            scrollWheelAction.AddBinding("<Mouse>/scroll");

            InputAction moveAction = map.AddAction(
                "Move",
                InputActionType.PassThrough
            );
            moveAction.expectedControlType = "Vector2";
            AddMoveBindings(moveAction);

            InputAction submitAction = map.AddAction(
                "Submit",
                InputActionType.Button
            );
            submitAction.expectedControlType = "Button";
            submitAction.AddBinding("<Keyboard>/enter");
            submitAction.AddBinding("<Keyboard>/numpadEnter");
            submitAction.AddBinding("<Gamepad>/buttonSouth");

            InputAction cancelAction = map.AddAction(
                "Cancel",
                InputActionType.Button
            );
            cancelAction.expectedControlType = "Button";
            cancelAction.AddBinding("<Keyboard>/escape");
            cancelAction.AddBinding("<Gamepad>/buttonEast");

            InputAction trackedDevicePositionAction = map.AddAction(
                "TrackedDevicePosition",
                InputActionType.PassThrough
            );
            trackedDevicePositionAction.expectedControlType = "Vector3";
            trackedDevicePositionAction.AddBinding("<XRController>/pointerPosition");
            trackedDevicePositionAction.AddBinding("<XRController>{LeftHand}/pointerPosition");
            trackedDevicePositionAction.AddBinding("<XRController>{RightHand}/pointerPosition");
            trackedDevicePositionAction.AddBinding("<TrackedDevice>/devicePosition");

            InputAction trackedDeviceOrientationAction = map.AddAction(
                "TrackedDeviceOrientation",
                InputActionType.PassThrough
            );
            trackedDeviceOrientationAction.expectedControlType = "Quaternion";
            trackedDeviceOrientationAction.AddBinding("<XRController>/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>{LeftHand}/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>{RightHand}/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<TrackedDevice>/deviceRotation");

            asset.AddActionMap(map);
            return asset;
        }

        private static void AddMoveBindings(InputAction moveAction)
        {
            if (moveAction == null)
            {
                return;
            }

            moveAction.AddCompositeBinding("2DVector")
                .With("Up", "<Keyboard>/w")
                .With("Up", "<Keyboard>/upArrow")
                .With("Down", "<Keyboard>/s")
                .With("Down", "<Keyboard>/downArrow")
                .With("Left", "<Keyboard>/a")
                .With("Left", "<Keyboard>/leftArrow")
                .With("Right", "<Keyboard>/d")
                .With("Right", "<Keyboard>/rightArrow");

            moveAction.AddCompositeBinding("2DVector")
                .With("Up", "<Gamepad>/leftStick/up")
                .With("Down", "<Gamepad>/leftStick/down")
                .With("Left", "<Gamepad>/leftStick/left")
                .With("Right", "<Gamepad>/leftStick/right");

            moveAction.AddCompositeBinding("2DVector")
                .With("Up", "<Gamepad>/dpad/up")
                .With("Down", "<Gamepad>/dpad/down")
                .With("Left", "<Gamepad>/dpad/left")
                .With("Right", "<Gamepad>/dpad/right");
        }

        private bool TryUseSceneUi()
        {
            if (!preferSceneUi || sceneCanvas == null || sceneListContentRoot == null)
            {
                return false;
            }

            rootCanvas = sceneCanvas;
            listContentRoot = sceneListContentRoot;
            statusText = sceneStatusText;
            sourceSummaryText = sceneSourceSummaryText;

            GraphicRaycaster graphicRaycaster = sceneCanvas.GetComponent<GraphicRaycaster>();
            if (graphicRaycaster == null)
            {
                graphicRaycaster = sceneCanvas.gameObject.AddComponent<GraphicRaycaster>();
            }

            graphicRaycaster.ignoreReversedGraphics = true;

            if (sceneCanvas.renderMode == RenderMode.WorldSpace)
            {
                if (sceneCanvas.worldCamera == null)
                {
                    sceneCanvas.worldCamera = presentationCamera;
                }

                if (sceneCanvas.GetComponent<TrackedDeviceRaycaster>() == null)
                {
                    sceneCanvas.gameObject.AddComponent<TrackedDeviceRaycaster>();
                }
            }

            if (sceneStimulusButtonTemplate != null)
            {
                sceneStimulusButtonTemplate.gameObject.SetActive(false);
            }

            if (sceneRefreshButton != null)
            {
                sceneRefreshButton.onClick.RemoveListener(PopulateStimulusList);
                sceneRefreshButton.onClick.AddListener(PopulateStimulusList);
            }

            return true;
        }

        private void ResolveSceneUiReferences()
        {
            if (sceneCanvas == null)
            {
                GameObject sceneCanvasObject = GameObject.Find("ExperimentSelectionCanvas");
                if (sceneCanvasObject != null)
                {
                    sceneCanvas = sceneCanvasObject.GetComponent<Canvas>();
                }
            }
        }

        private static void PreparePointerForSelection()
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
        }

        private void BuildRuntimeUi()
        {
            GameObject canvasObject;
            bool preserveSceneWorldPlacement = sceneCanvas != null && sceneCanvas.renderMode == RenderMode.WorldSpace;

            if (sceneCanvas != null)
            {
                canvasObject = sceneCanvas.gameObject;
                rootCanvas = sceneCanvas;
                EnsureCanvasSupportComponents(canvasObject);
            }
            else
            {
                canvasObject = new GameObject(
                    "ExperimentSelectionCanvas",
                    typeof(Canvas),
                    typeof(CanvasScaler),
                    typeof(GraphicRaycaster)
                );

                dynamicUiObjects.Add(canvasObject);
                rootCanvas = canvasObject.GetComponent<Canvas>();
            }

            rootCanvas.sortingOrder = 1000;

            CanvasScaler scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1600f, 900f);
            scaler.matchWidthOrHeight = 0.5f;

            RectTransform canvasRect = canvasObject.GetComponent<RectTransform>();
            if (preserveSceneWorldPlacement)
            {
                rootCanvas.renderMode = RenderMode.WorldSpace;
                rootCanvas.worldCamera = presentationCamera;

                if (canvasObject.GetComponent<TrackedDeviceRaycaster>() == null)
                {
                    canvasObject.AddComponent<TrackedDeviceRaycaster>();
                }
            }
            else
            {
                ConfigurePresentationCanvas(canvasObject, canvasRect);
            }

            RectTransform background = ExperimentRuntimeUi.CreateUiObject(
                "Background",
                canvasRect,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );

            Image backgroundImage = ExperimentRuntimeUi.AddPanelImage(
                background,
                new Color(0.06f, 0.07f, 0.1f, 0.96f)
            );
            backgroundImage.raycastTarget = false;

            RectTransform modal = ExperimentRuntimeUi.CreateUiObject(
                "Modal",
                background,
                new Vector2(0.5f, 0.5f),
                new Vector2(0.5f, 0.5f)
            );

            modal.sizeDelta = new Vector2(1080f, 760f);
            modal.anchoredPosition = Vector2.zero;

            Image modalImage = ExperimentRuntimeUi.AddPanelImage(
                modal,
                new Color(0.13f, 0.15f, 0.2f, 0.98f)
            );
            modalImage.raycastTarget = false;

            Outline outline = modal.gameObject.AddComponent<Outline>();
            outline.effectColor = new Color(0.27f, 0.36f, 0.5f, 0.65f);
            outline.effectDistance = new Vector2(1f, -1f);

            TextMeshProUGUI titleText = ExperimentRuntimeUi.CreateText(
                "Title",
                modal,
                "Selecciona el video del experimento",
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
                "Se muestran solo los estimulos que tienen video y AOIs listos. El catalogo prioriza `data/` y usa `StreamingAssets` como respaldo.",
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

            Image listPanelImage = ExperimentRuntimeUi.AddPanelImage(
                listPanel,
                new Color(0.08f, 0.09f, 0.13f, 0.98f)
            );
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

            Image viewportImage = ExperimentRuntimeUi.AddPanelImage(
                viewport,
                new Color(0f, 0f, 0f, 0f)
            );
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
            listContentRoot.sizeDelta = Vector2.zero;

            VerticalLayoutGroup layoutGroup = listContentRoot.gameObject.AddComponent<VerticalLayoutGroup>();
            layoutGroup.padding = new RectOffset(0, 0, 0, 0);
            layoutGroup.spacing = 14f;
            layoutGroup.childAlignment = TextAnchor.UpperCenter;
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
                "Esperando seleccion...",
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

        private static void EnsureCanvasSupportComponents(GameObject canvasObject)
        {
            if (canvasObject == null)
            {
                return;
            }

            if (canvasObject.GetComponent<Canvas>() == null)
            {
                canvasObject.AddComponent<Canvas>();
            }

            if (canvasObject.GetComponent<CanvasScaler>() == null)
            {
                canvasObject.AddComponent<CanvasScaler>();
            }

            if (canvasObject.GetComponent<GraphicRaycaster>() == null)
            {
                canvasObject.AddComponent<GraphicRaycaster>();
            }
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

            Transform cameraTransform = presentationCamera.transform;
            Vector3 anchoredPosition = cameraTransform.position
                                       + (cameraTransform.forward * 2.45f)
                                       + (cameraTransform.up * 0.24f);

            canvasRect.anchorMin = new Vector2(0.5f, 0.5f);
            canvasRect.anchorMax = new Vector2(0.5f, 0.5f);
            canvasRect.pivot = new Vector2(0.5f, 0.5f);
            canvasRect.sizeDelta = new Vector2(1600f, 900f);
            canvasRect.position = anchoredPosition;
            canvasRect.rotation = cameraTransform.rotation;
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

            InputAction positionAction = new InputAction(
                name: "SelectionHmdPosition",
                type: InputActionType.PassThrough,
                binding: "<XRHMD>/centerEyePosition"
            );
            positionAction.expectedControlType = "Vector3";

            InputAction rotationAction = new InputAction(
                name: "SelectionHmdRotation",
                type: InputActionType.PassThrough,
                binding: "<XRHMD>/centerEyeRotation"
            );
            rotationAction.expectedControlType = "Quaternion";

            trackedPoseDriver.positionInput = new InputActionProperty(positionAction);
            trackedPoseDriver.rotationInput = new InputActionProperty(rotationAction);
        }

        private void PopulateStimulusList()
        {
            if (listContentRoot == null)
            {
                return;
            }

            for (int i = listContentRoot.childCount - 1; i >= 0; i--)
            {
                Transform child = listContentRoot.GetChild(i);
                if (sceneStimulusButtonTemplate != null && child == sceneStimulusButtonTemplate.transform)
                {
                    continue;
                }

                Destroy(child.gameObject);
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
                    ? $"Estimulos disponibles: {stimuli.Count} | repo: {repositoryCount} | mirror: {streamingCount}"
                    : "No se ha encontrado ningun estimulo listo.";
            }

            if (statusText != null)
            {
                statusText.text = stimuli.Count > 0
                    ? "Selecciona un video para abrir la escena VR y lanzar la cuenta atras."
                    : "No hay videos listos. Revisa `data/input_videos` y `data/processed`, o sincroniza `StreamingAssets`.";
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

                ExperimentRuntimeUi.AddPanelImage(
                    emptyState,
                    new Color(0.16f, 0.11f, 0.11f, 0.95f)
                );

                TextMeshProUGUI emptyText = ExperimentRuntimeUi.CreateText(
                    "EmptyLabel",
                    emptyState,
                    "No hay nada seleccionable todavia.\n\nGenera un video preprocesado con la pipeline y, si vas a usar build o `StreamingAssets`, ejecuta la sincronizacion desde `Tools/AOI`.",
                    22f,
                    FontStyles.Normal,
                    TextAlignmentOptions.Center,
                    new Color(1f, 0.9f, 0.86f, 1f)
                );

                emptyText.raycastTarget = false;
            }

            Canvas.ForceUpdateCanvases();
            LayoutRebuilder.ForceRebuildLayoutImmediate(listContentRoot);

            RectTransform parentRect = listContentRoot.parent as RectTransform;
            if (parentRect != null)
            {
                LayoutRebuilder.ForceRebuildLayoutImmediate(parentRect);
            }
        }

        private void CreateStimulusButton(ExperimentStimulusDefinition stimulus)
        {
            Button button = CreateStimulusButtonInstance(stimulus);
            if (button == null)
            {
                return;
            }

            button.onClick.RemoveAllListeners();
            button.onClick.AddListener(() => SelectStimulus(stimulus));

            if (sceneStimulusButtonTemplate != null)
            {
                ApplyTemplateButtonText(button, stimulus);
                return;
            }

            RectTransform buttonRect = button.GetComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0f, 1f);
            buttonRect.anchorMax = new Vector2(1f, 1f);
            buttonRect.pivot = new Vector2(0.5f, 1f);
            buttonRect.sizeDelta = new Vector2(0f, 104f);

            LayoutElement layoutElement = button.gameObject.AddComponent<LayoutElement>();
            layoutElement.preferredHeight = 104f;
            layoutElement.minHeight = 104f;

            Outline outline = button.gameObject.AddComponent<Outline>();
            outline.effectColor = new Color(0.44f, 0.58f, 0.79f, 0.2f);
            outline.effectDistance = new Vector2(1f, -1f);

            TextMeshProUGUI title = CreateButtonText(
                button.transform,
                "Title",
                stimulus.DisplayName,
                28f,
                FontStyles.Bold,
                TextAlignmentOptions.Left,
                Color.white,
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 1f),
                new Vector2(0f, 38f),
                new Vector2(0f, -10f),
                new Vector4(24f, 8f, 24f, 0f),
                false
            );

            title.raycastTarget = false;
            title.overflowMode = TextOverflowModes.Ellipsis;

            string detailText =
                $"{stimulus.VideoFileName} | secuencia: {stimulus.SequenceName} | origen: {stimulus.SourceLabel}";

            TextMeshProUGUI details = CreateButtonText(
                button.transform,
                "Details",
                detailText,
                18f,
                FontStyles.Normal,
                TextAlignmentOptions.Left,
                new Color(0.82f, 0.88f, 0.96f, 0.96f),
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 1f),
                new Vector2(0f, 34f),
                new Vector2(0f, -48f),
                new Vector4(24f, 4f, 24f, 8f),
                false
            );

            details.raycastTarget = false;
            details.overflowMode = TextOverflowModes.Ellipsis;
        }

        private Button CreateStimulusButtonInstance(ExperimentStimulusDefinition stimulus)
        {
            if (sceneStimulusButtonTemplate != null)
            {
                Button buttonInstance = Instantiate(sceneStimulusButtonTemplate, listContentRoot);
                buttonInstance.name = $"StimulusButton_{stimulus.SequenceName}";
                buttonInstance.gameObject.SetActive(true);
                return buttonInstance;
            }

            return ExperimentRuntimeUi.CreateButton(
                $"StimulusButton_{stimulus.SequenceName}",
                listContentRoot,
                new Color(0.16f, 0.2f, 0.28f, 0.98f)
            );
        }

        private void ApplyTemplateButtonText(Button button, ExperimentStimulusDefinition stimulus)
        {
            string detailText =
                $"{stimulus.VideoFileName} | secuencia: {stimulus.SequenceName} | origen: {stimulus.SourceLabel}";

            TextMeshProUGUI title = FindNamedText(button.transform, "Title");
            TextMeshProUGUI details = FindNamedText(button.transform, "Details");

            TextMeshProUGUI[] allTexts = button.GetComponentsInChildren<TextMeshProUGUI>(true);

            if (title == null && allTexts.Length > 0)
            {
                title = allTexts[0];
            }

            if (details == null && allTexts.Length > 1)
            {
                details = allTexts[1];
            }

            if (title != null)
            {
                title.text = stimulus.DisplayName;
                title.raycastTarget = false;
            }

            if (details != null)
            {
                details.text = detailText;
                details.raycastTarget = false;
            }
        }

        private static TextMeshProUGUI FindNamedText(Transform root, string childName)
        {
            if (root == null || string.IsNullOrWhiteSpace(childName))
            {
                return null;
            }

            TextMeshProUGUI[] allTexts = root.GetComponentsInChildren<TextMeshProUGUI>(true);
            for (int i = 0; i < allTexts.Length; i++)
            {
                TextMeshProUGUI text = allTexts[i];
                if (text != null && string.Equals(text.name, childName, System.StringComparison.OrdinalIgnoreCase))
                {
                    return text;
                }
            }

            return null;
        }

        private static TextMeshProUGUI CreateButtonText(
            Transform parent,
            string name,
            string text,
            float fontSize,
            FontStyles fontStyle,
            TextAlignmentOptions alignment,
            Color color,
            Vector2 anchorMin,
            Vector2 anchorMax,
            Vector2 pivot,
            Vector2 sizeDelta,
            Vector2 anchoredPosition,
            Vector4 margin,
            bool wrapText
        )
        {
            TextMeshProUGUI textComponent = ExperimentRuntimeUi.CreateText(
                name,
                parent,
                text,
                fontSize,
                fontStyle,
                alignment,
                color
            );

            RectTransform rectTransform = textComponent.rectTransform;
            rectTransform.anchorMin = anchorMin;
            rectTransform.anchorMax = anchorMax;
            rectTransform.pivot = pivot;
            rectTransform.sizeDelta = sizeDelta;
            rectTransform.anchoredPosition = anchoredPosition;

            textComponent.margin = margin;
            textComponent.enableWordWrapping = wrapText;

            return textComponent;
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

            SceneManager.LoadScene(ResolvePlaybackSceneName());
        }

        private static bool IsSelectionScene(string sceneName)
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

        private static string ResolvePlaybackSceneName()
        {
            for (int i = 0; i < PlaybackSceneCandidates.Length; i++)
            {
                string candidate = PlaybackSceneCandidates[i];
                if (Application.CanStreamedLevelBeLoaded(candidate))
                {
                    return candidate;
                }
            }

            return PlaybackSceneCandidates[0];
        }
    }
}