using System;
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
        // This controller rebuilds the selection UI at runtime so the headset menu
        // always reflects the latest preprocessed stimuli available on disk.
        private static readonly string[] TargetSceneNames = { "Initial_Scene" };
        private static readonly bool IncludeStreamingAssetsMirror = false;

        private static readonly string[] PlaybackSceneCandidates =
        {
            "Phase2_360Playback_VR_sampleRIG"
        };

        private const string RuntimeObjectName = "ExperimentSelectionSceneController_Runtime";
        private const string RuntimeCanvasName = "ExperimentSelectionCanvas_Runtime";
        private const float UiReferencePixelsPerUnit = 100f;
        private const float UiDynamicPixelsPerUnit = 96f;
        private const float SelectionCanvasWorldDepthMeters = 2.6f;
        private const float SelectionCanvasScale = 0.0015f;
        private const float SelectionCanvasMinimumHeightMeters = 1.24f;
        private const float SelectionCanvasHeightOffsetMeters = -0.08f;

        private const float StimulusButtonHeight = 86f;
        private const float StimulusButtonSpacing = 10f;
        private const float StimulusButtonTopPadding = 6f;
        private const float SettingsValueFieldWidth = 176f;
        private const float SettingsValueFieldRightOffset = 92f;
        private const float SettingsValueButtonSpacing = 78f;

        private enum SelectionTab
        {
            Videos = 0,
            Settings = 1
        }

        [Header("Scene UI")]
        [SerializeField] private bool preferSceneUi = false;
        [SerializeField] private Canvas sceneCanvas;
        [SerializeField] private RectTransform sceneListContentRoot;
        [SerializeField] private Button sceneStimulusButtonTemplate;
        [SerializeField] private TextMeshProUGUI sceneStatusText;
        [SerializeField] private TextMeshProUGUI sceneSourceSummaryText;
        [SerializeField] private Button sceneRefreshButton;

        private readonly List<GameObject> dynamicUiObjects = new();
        private readonly List<Button> stimulusButtons = new();

        private Canvas rootCanvas;
        private RectTransform rootCanvasRect;
        private RectTransform listContentRoot;
        private RectTransform videosTabContentRoot;
        private RectTransform settingsTabContentRoot;
        private TextMeshProUGUI statusText;
        private TextMeshProUGUI sourceSummaryText;
        private TextMeshProUGUI videosTabButtonLabel;
        private TextMeshProUGUI settingsTabButtonLabel;
        private TextMeshProUGUI countdownSecondsValueText;
        private TextMeshProUGUI videoVolumeValueText;
        private TextMeshProUGUI countdownBeepStateText;
        private TextMeshProUGUI countdownBeepVolumeValueText;
        private Button videosTabButton;
        private Button settingsTabButton;
        private Camera presentationCamera;
        private bool isLoadingSelection;
        private bool hasCachedCanvasTransform;
        private InputActionAsset runtimeUiActionsAsset;
        private Button firstStimulusButton;
        private Vector3 cachedCanvasWorldPosition;
        private static bool sceneHookRegistered;
        private InputAction debugTrackedPositionAction;
        private InputAction debugTrackedRotationAction;
        private InputAction debugClickAction;
        private float nextInputDebugLogTime;
        private SelectionTab activeTab = SelectionTab.Videos;

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
            if (!IsSelectionScene(scene.name))
            {
                return;
            }

            if (FindControllerInScene(scene) != null)
            {
                return;
            }

            GameObject runtimeObject = new GameObject(RuntimeObjectName);
            runtimeObject.AddComponent<ExperimentSelectionSceneController>();
        }

        private static ExperimentSelectionSceneController FindControllerInScene(Scene scene)
        {
            if (!scene.isLoaded)
            {
                return null;
            }

            GameObject[] rootObjects = scene.GetRootGameObjects();
            for (int i = 0; i < rootObjects.Length; i++)
            {
                ExperimentSelectionSceneController controller =
                    rootObjects[i].GetComponentInChildren<ExperimentSelectionSceneController>(true);

                if (controller != null)
                {
                    return controller;
                }
            }

            return null;
        }

        private void Awake()
        {
            if (!IsSelectionScene(SceneManager.GetActiveScene().name))
            {
                enabled = false;
                return;
            }

            Debug.Log($"[ExperimentSelectionSceneController] Awake in scene '{SceneManager.GetActiveScene().name}'.");

            ExperimentSessionState.Clear();
            PreparePointerForSelection();

            presentationCamera = ResolvePresentationCamera();
            EnsureTrackedVrCamera(presentationCamera);

            EnsureEventSystem();
            ResolveSceneUiReferences();

            if (preferSceneUi && TryUseSceneUi())
            {
                Debug.Log("[ExperimentSelectionSceneController] Using scene-authored UI.");
            }
            else
            {
                Debug.Log("[ExperimentSelectionSceneController] Building clean runtime VR UI.");
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
            stimulusButtons.Clear();

            if (runtimeUiActionsAsset != null)
            {
                runtimeUiActionsAsset.Disable();
                Destroy(runtimeUiActionsAsset);
                runtimeUiActionsAsset = null;
            }
        }

        private void LateUpdate()
        {
            MaintainPresentationCanvasTransform();
            DebugRuntimeVrInput();
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

                StandaloneInputModule standaloneInputModule = eventSystem.GetComponent<StandaloneInputModule>();
                if (standaloneInputModule != null)
                {
                    Destroy(standaloneInputModule);
                }
            }

            if (inputModule == null)
            {
                inputModule = eventSystem.gameObject.AddComponent<InputSystemUIInputModule>();
            }

            ConfigureEventSystemInput(inputModule);

            inputModule.deselectOnBackgroundClick = true;
            inputModule.pointerBehavior = UIPointerBehavior.SingleMouseOrPenButMultiTouchAndTrack;

            eventSystem.sendNavigationEvents = false;
            eventSystem.SetSelectedGameObject(null);

            Debug.Log("[ExperimentSelectionSceneController] EventSystem configured for Input System + XR tracked device UI.");
        }

        private void ConfigureEventSystemInput(InputSystemUIInputModule inputModule)
        {
            if (inputModule == null)
            {
                return;
            }

            // En esta escena queremos forzar una configuración conocida.
            // No asumimos que el EventSystem de la escena ya tenga acciones XR correctas.

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
            debugTrackedPositionAction = uiMap.FindAction("TrackedDevicePosition", throwIfNotFound: true);
            debugTrackedRotationAction = uiMap.FindAction("TrackedDeviceOrientation", throwIfNotFound: true);
            debugClickAction = uiMap.FindAction("LeftClick", throwIfNotFound: true);
        }

        private static bool HasSceneTrackedDeviceInput(InputSystemUIInputModule inputModule)
        {
            if (inputModule == null || inputModule.actionsAsset == null)
            {
                return false;
            }

            return inputModule.leftClick != null &&
                   inputModule.leftClick.action != null &&
                   inputModule.trackedDevicePosition != null &&
                   inputModule.trackedDevicePosition.action != null &&
                   inputModule.trackedDeviceOrientation != null &&
                   inputModule.trackedDeviceOrientation.action != null;
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
            pointAction.AddBinding("<Pen>/position");
            pointAction.AddBinding("<Touchscreen>/primaryTouch/position");

            InputAction leftClickAction = map.AddAction(
                "LeftClick",
                InputActionType.PassThrough
            );
            leftClickAction.expectedControlType = "Button";
            AddClickBindings(leftClickAction);

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
            AddSubmitBindings(submitAction);

            InputAction cancelAction = map.AddAction(
                "Cancel",
                InputActionType.Button
            );
            cancelAction.expectedControlType = "Button";
            cancelAction.AddBinding("<Keyboard>/escape");
            cancelAction.AddBinding("<Gamepad>/buttonEast");
            cancelAction.AddBinding("<XRController>{LeftHand}/secondaryButton");
            cancelAction.AddBinding("<XRController>{RightHand}/secondaryButton");

            InputAction trackedDevicePositionAction = map.AddAction(
                "TrackedDevicePosition",
                InputActionType.PassThrough
            );
            trackedDevicePositionAction.expectedControlType = "Vector3";

            // XR genérico.
            trackedDevicePositionAction.AddBinding("<XRController>{RightHand}/devicePosition");
            trackedDevicePositionAction.AddBinding("<XRController>{LeftHand}/devicePosition");

            // OpenXR explícito.
            trackedDevicePositionAction.AddBinding("<OpenXRController>{RightHand}/devicePosition");
            trackedDevicePositionAction.AddBinding("<OpenXRController>{LeftHand}/devicePosition");

            // Fallback tracked.
            trackedDevicePositionAction.AddBinding("<TrackedDevice>{RightHand}/devicePosition");
            trackedDevicePositionAction.AddBinding("<TrackedDevice>{LeftHand}/devicePosition");

            // Algunos layouts exponen pointerPosition en vez de devicePosition.
            trackedDevicePositionAction.AddBinding("<XRController>{RightHand}/pointerPosition");
            trackedDevicePositionAction.AddBinding("<XRController>{LeftHand}/pointerPosition");
            trackedDevicePositionAction.AddBinding("<OpenXRController>{RightHand}/pointerPosition");
            trackedDevicePositionAction.AddBinding("<OpenXRController>{LeftHand}/pointerPosition");

            InputAction trackedDeviceOrientationAction = map.AddAction(
                "TrackedDeviceOrientation",
                InputActionType.PassThrough
            );
            trackedDeviceOrientationAction.expectedControlType = "Quaternion";

            // XR genérico.
            trackedDeviceOrientationAction.AddBinding("<XRController>{RightHand}/deviceRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>{LeftHand}/deviceRotation");

            // OpenXR explícito.
            trackedDeviceOrientationAction.AddBinding("<OpenXRController>{RightHand}/deviceRotation");
            trackedDeviceOrientationAction.AddBinding("<OpenXRController>{LeftHand}/deviceRotation");

            // Fallback tracked.
            trackedDeviceOrientationAction.AddBinding("<TrackedDevice>{RightHand}/deviceRotation");
            trackedDeviceOrientationAction.AddBinding("<TrackedDevice>{LeftHand}/deviceRotation");

            // Algunos layouts exponen pointerRotation en vez de deviceRotation.
            trackedDeviceOrientationAction.AddBinding("<XRController>{RightHand}/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>{LeftHand}/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<OpenXRController>{RightHand}/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<OpenXRController>{LeftHand}/pointerRotation");

            asset.AddActionMap(map);
            return asset;
        }

        private static void AddClickBindings(InputAction clickAction)
        {
            if (clickAction == null)
            {
                return;
            }

            clickAction.AddBinding("<Mouse>/leftButton");
            clickAction.AddBinding("<Touchscreen>/primaryTouch/press");

            // Right hand.
            clickAction.AddBinding("<XRController>{RightHand}/triggerPressed");
            clickAction.AddBinding("<XRController>{RightHand}/trigger").WithInteraction("Press");
            clickAction.AddBinding("<XRController>{RightHand}/primaryButton");

            clickAction.AddBinding("<OpenXRController>{RightHand}/triggerPressed");
            clickAction.AddBinding("<OpenXRController>{RightHand}/trigger").WithInteraction("Press");
            clickAction.AddBinding("<OpenXRController>{RightHand}/primaryButton");

            // Left hand.
            clickAction.AddBinding("<XRController>{LeftHand}/triggerPressed");
            clickAction.AddBinding("<XRController>{LeftHand}/trigger").WithInteraction("Press");
            clickAction.AddBinding("<XRController>{LeftHand}/primaryButton");

            clickAction.AddBinding("<OpenXRController>{LeftHand}/triggerPressed");
            clickAction.AddBinding("<OpenXRController>{LeftHand}/trigger").WithInteraction("Press");
            clickAction.AddBinding("<OpenXRController>{LeftHand}/primaryButton");
        }

        private static void AddSubmitBindings(InputAction submitAction)
        {
            if (submitAction == null)
            {
                return;
            }

            submitAction.AddBinding("<Keyboard>/enter");
            submitAction.AddBinding("<Keyboard>/numpadEnter");
            submitAction.AddBinding("<Gamepad>/buttonSouth");
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

            RectTransform canvasRect = sceneCanvas.GetComponent<RectTransform>();
            ConfigurePresentationCanvas(sceneCanvas.gameObject, canvasRect);

            CanvasScaler canvasScaler = sceneCanvas.GetComponent<CanvasScaler>();
            if (canvasScaler != null)
            {
                canvasScaler.referencePixelsPerUnit = UiReferencePixelsPerUnit;
                canvasScaler.dynamicPixelsPerUnit = Mathf.Max(canvasScaler.dynamicPixelsPerUnit, UiDynamicPixelsPerUnit);
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

            EnsureCanvasRaycasters(sceneCanvas.gameObject);

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
            CanvasScaler scaler;

            if (sceneCanvas != null)
            {
                canvasObject = sceneCanvas.gameObject;
                rootCanvas = sceneCanvas;
                scaler = canvasObject.GetComponent<CanvasScaler>();

                if (scaler == null)
                {
                    scaler = canvasObject.AddComponent<CanvasScaler>();
                }
            }
            else
            {
                GameObject existingRuntimeCanvas = GameObject.Find(RuntimeCanvasName);
                if (existingRuntimeCanvas != null)
                {
                    Destroy(existingRuntimeCanvas);
                }

                canvasObject = new GameObject(
                    RuntimeCanvasName,
                    typeof(Canvas),
                    typeof(CanvasScaler),
                    typeof(GraphicRaycaster)
                );

                dynamicUiObjects.Add(canvasObject);
                rootCanvas = canvasObject.GetComponent<Canvas>();
                scaler = canvasObject.GetComponent<CanvasScaler>();
            }

            rootCanvas.sortingOrder = 5000;
            rootCanvas.overrideSorting = true;

            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1400f, 800f);
            scaler.referencePixelsPerUnit = UiReferencePixelsPerUnit;
            scaler.matchWidthOrHeight = 0.5f;
            scaler.dynamicPixelsPerUnit = UiDynamicPixelsPerUnit;

            rootCanvasRect = canvasObject.GetComponent<RectTransform>();
            ConfigurePresentationCanvas(canvasObject, rootCanvasRect);
            EnsureCanvasRaycasters(canvasObject);

            RectTransform background = ExperimentRuntimeUi.CreateUiObject(
                "Background",
                rootCanvasRect,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );

            Image backgroundImage = ExperimentRuntimeUi.AddPanelImage(
                background,
                new Color(0.04f, 0.05f, 0.07f, 0.96f)
            );
            backgroundImage.raycastTarget = false;

            RectTransform modal = ExperimentRuntimeUi.CreateUiObject(
                "Modal",
                background,
                new Vector2(0.5f, 0.5f),
                new Vector2(0.5f, 0.5f)
            );

            modal.sizeDelta = new Vector2(1080f, 820f);
            modal.anchoredPosition = Vector2.zero;

            Image modalImage = ExperimentRuntimeUi.AddPanelImage(
                modal,
                new Color(0.12f, 0.14f, 0.19f, 0.98f)
            );
            modalImage.raycastTarget = false;

            Outline outline = modal.gameObject.AddComponent<Outline>();
            outline.effectColor = new Color(0.3f, 0.45f, 0.75f, 0.85f);
            outline.effectDistance = new Vector2(2f, -2f);

            TextMeshProUGUI titleText = ExperimentRuntimeUi.CreateText(
                "Title",
                modal,
                "Selecciona el video del experimento",
                34f,
                FontStyles.Bold,
                TextAlignmentOptions.MidlineLeft,
                Color.white
            );

            RectTransform titleRect = titleText.rectTransform;
            titleRect.anchorMin = new Vector2(0f, 1f);
            titleRect.anchorMax = new Vector2(1f, 1f);
            titleRect.pivot = new Vector2(0.5f, 1f);
            titleRect.sizeDelta = new Vector2(0f, 72f);
            titleRect.anchoredPosition = new Vector2(0f, -10f);
            titleText.raycastTarget = false;

            TextMeshProUGUI subtitleText = ExperimentRuntimeUi.CreateText(
                "Subtitle",
                modal,
                "Elige un estimulo procesado. Todos los botones abren la misma escena VR base y cambian el video y los AOIs. Usa el laser del mando derecho y el gatillo para confirmar.",
                19f,
                FontStyles.Normal,
                TextAlignmentOptions.TopLeft,
                new Color(0.82f, 0.87f, 0.96f, 0.92f)
            );

            RectTransform subtitleRect = subtitleText.rectTransform;
            subtitleRect.anchorMin = new Vector2(0f, 1f);
            subtitleRect.anchorMax = new Vector2(1f, 1f);
            subtitleRect.pivot = new Vector2(0.5f, 1f);
            subtitleRect.sizeDelta = new Vector2(0f, 58f);
            subtitleRect.anchoredPosition = new Vector2(0f, -76f);
            subtitleText.raycastTarget = false;

            RectTransform tabBar = ExperimentRuntimeUi.CreateUiObject(
                "TabBar",
                modal,
                new Vector2(0f, 1f),
                new Vector2(1f, 1f)
            );
            tabBar.pivot = new Vector2(0.5f, 1f);
            tabBar.sizeDelta = new Vector2(0f, 56f);
            tabBar.anchoredPosition = new Vector2(0f, -148f);

            videosTabButton = CreateTabButton(
                tabBar,
                "VideosTabButton",
                "Videos",
                new Vector2(22f, -2f),
                () => SetActiveTab(SelectionTab.Videos),
                out videosTabButtonLabel
            );

            settingsTabButton = CreateTabButton(
                tabBar,
                "SettingsTabButton",
                "Configuracion",
                new Vector2(246f, -2f),
                () => SetActiveTab(SelectionTab.Settings),
                out settingsTabButtonLabel
            );

            RectTransform contentPanel = ExperimentRuntimeUi.CreateUiObject(
                "ContentPanel",
                modal,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );

            contentPanel.offsetMin = new Vector2(40f, 118f);
            contentPanel.offsetMax = new Vector2(-40f, -200f);

            Image contentPanelImage = ExperimentRuntimeUi.AddPanelImage(
                contentPanel,
                new Color(0.05f, 0.06f, 0.09f, 0.98f)
            );
            contentPanelImage.raycastTarget = false;

            videosTabContentRoot = ExperimentRuntimeUi.CreateUiObject(
                "VideosTabContent",
                contentPanel,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );
            videosTabContentRoot.offsetMin = new Vector2(16f, 16f);
            videosTabContentRoot.offsetMax = new Vector2(-16f, -16f);

            listContentRoot = ExperimentRuntimeUi.CreateUiObject(
                "VideoListContent",
                videosTabContentRoot,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );
            listContentRoot.offsetMin = Vector2.zero;
            listContentRoot.offsetMax = Vector2.zero;
            listContentRoot.pivot = new Vector2(0.5f, 0.5f);
            listContentRoot.anchoredPosition = Vector2.zero;
            listContentRoot.sizeDelta = Vector2.zero;

            settingsTabContentRoot = ExperimentRuntimeUi.CreateUiObject(
                "SettingsTabContent",
                contentPanel,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );
            settingsTabContentRoot.offsetMin = new Vector2(16f, 16f);
            settingsTabContentRoot.offsetMax = new Vector2(-16f, -16f);

            BuildSettingsTab(settingsTabContentRoot);
            SetActiveTab(SelectionTab.Videos);
            RefreshRuntimeSettingsUi();

            Debug.Log("[ExperimentSelectionSceneController] Runtime tabs created for videos and configuration.");

            sourceSummaryText = ExperimentRuntimeUi.CreateText(
                "SourceSummary",
                modal,
                string.Empty,
                18f,
                FontStyles.Normal,
                TextAlignmentOptions.BottomLeft,
                new Color(0.78f, 0.84f, 0.93f, 0.95f)
            );

            RectTransform sourceSummaryRect = sourceSummaryText.rectTransform;
            sourceSummaryRect.anchorMin = new Vector2(0f, 0f);
            sourceSummaryRect.anchorMax = new Vector2(1f, 0f);
            sourceSummaryRect.pivot = new Vector2(0.5f, 0f);
            sourceSummaryRect.sizeDelta = new Vector2(0f, 40f);
            sourceSummaryRect.anchoredPosition = new Vector2(0f, 70f);
            sourceSummaryText.raycastTarget = false;

            statusText = ExperimentRuntimeUi.CreateText(
                "Status",
                modal,
                "Esperando seleccion...",
                20f,
                FontStyles.Bold,
                TextAlignmentOptions.BottomLeft,
                new Color(0.96f, 0.82f, 0.48f, 1f)
            );

            RectTransform statusRect = statusText.rectTransform;
            statusRect.anchorMin = new Vector2(0f, 0f);
            statusRect.anchorMax = new Vector2(1f, 0f);
            statusRect.pivot = new Vector2(0.5f, 0f);
            statusRect.sizeDelta = new Vector2(0f, 46f);
            statusRect.anchoredPosition = new Vector2(0f, 16f);
            statusText.raycastTarget = false;
        }

        private Button CreateTabButton(
            Transform parent,
            string name,
            string label,
            Vector2 anchoredPosition,
            UnityEngine.Events.UnityAction onClick,
            out TextMeshProUGUI labelText
        )
        {
            Button button = ExperimentRuntimeUi.CreateButton(
                name,
                parent,
                new Color(0.22f, 0.27f, 0.36f, 1f)
            );

            RectTransform buttonRect = button.GetComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0f, 1f);
            buttonRect.anchorMax = new Vector2(0f, 1f);
            buttonRect.pivot = new Vector2(0f, 1f);
            buttonRect.sizeDelta = new Vector2(208f, 44f);
            buttonRect.anchoredPosition = anchoredPosition;

            button.onClick.RemoveAllListeners();
            button.onClick.AddListener(onClick);

            labelText = CreateButtonText(
                button.transform,
                "Label",
                label,
                18f,
                FontStyles.Bold,
                TextAlignmentOptions.Center,
                Color.white,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 0.5f),
                Vector2.zero,
                Vector2.zero,
                new Vector4(8f, 8f, 8f, 8f),
                false
            );
            labelText.raycastTarget = false;
            return button;
        }

        private void BuildSettingsTab(RectTransform parent)
        {
            if (parent == null)
            {
                return;
            }

            RectTransform infoPanel = ExperimentRuntimeUi.CreateUiObject(
                "SettingsInfoPanel",
                parent,
                new Vector2(0f, 1f),
                new Vector2(1f, 1f)
            );
            infoPanel.pivot = new Vector2(0.5f, 1f);
            infoPanel.sizeDelta = new Vector2(0f, 90f);
            infoPanel.anchoredPosition = Vector2.zero;
            ExperimentRuntimeUi.AddPanelImage(
                infoPanel,
                new Color(0.11f, 0.16f, 0.24f, 0.94f)
            ).raycastTarget = false;

            TextMeshProUGUI infoText = ExperimentRuntimeUi.CreateText(
                "SettingsInfoText",
                infoPanel,
                "Configura el tiempo de espera, el volumen del video y el pitido de la cuenta atras. Estos ajustes se guardan localmente en este equipo.",
                18f,
                FontStyles.Normal,
                TextAlignmentOptions.MidlineLeft,
                new Color(0.9f, 0.94f, 0.99f, 0.96f)
            );
            infoText.rectTransform.offsetMin = new Vector2(18f, 8f);
            infoText.rectTransform.offsetMax = new Vector2(-18f, -8f);
            infoText.raycastTarget = false;

            RectTransform rowsRoot = ExperimentRuntimeUi.CreateUiObject(
                "SettingsRows",
                parent,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );
            rowsRoot.offsetMin = new Vector2(0f, 58f);
            rowsRoot.offsetMax = new Vector2(0f, -108f);

            countdownSecondsValueText = CreateStepperSettingRow(
                rowsRoot,
                rowIndex: 0,
                title: "Tiempo hasta lanzar el video",
                subtitle: "Define cuantos segundos dura la cuenta atras antes de que comience el estimulo.",
                onDecrease: () => AdjustCountdownSeconds(-1f),
                onIncrease: () => AdjustCountdownSeconds(1f)
            );

            videoVolumeValueText = CreateStepperSettingRow(
                rowsRoot,
                rowIndex: 1,
                title: "Volumen del video",
                subtitle: "Controla el sonido del estimulo durante la reproduccion en la escena VR.",
                onDecrease: () => AdjustVideoVolume(-0.1f),
                onIncrease: () => AdjustVideoVolume(0.1f)
            );

            countdownBeepStateText = CreateToggleSettingRow(
                rowsRoot,
                rowIndex: 2,
                title: "Pitido de cuenta atras",
                subtitle: "Activa o desactiva el beep que suena en cada segundo visible de la cuenta atras.",
                onToggle: ToggleCountdownBeep
            );

            countdownBeepVolumeValueText = CreateStepperSettingRow(
                rowsRoot,
                rowIndex: 3,
                title: "Volumen del pitido",
                subtitle: "Ajusta la intensidad del beep de cuenta atras sin afectar al volumen del video.",
                onDecrease: () => AdjustCountdownBeepVolume(-0.1f),
                onIncrease: () => AdjustCountdownBeepVolume(0.1f)
            );

            TextMeshProUGUI footerText = ExperimentRuntimeUi.CreateText(
                "SettingsFooter",
                parent,
                "El video seleccionado usara estos valores al abrir la escena de experimento.",
                16f,
                FontStyles.Italic,
                TextAlignmentOptions.BottomLeft,
                new Color(0.8f, 0.86f, 0.95f, 0.92f)
            );
            RectTransform footerRect = footerText.rectTransform;
            footerRect.anchorMin = new Vector2(0f, 0f);
            footerRect.anchorMax = new Vector2(1f, 0f);
            footerRect.pivot = new Vector2(0.5f, 0f);
            footerRect.sizeDelta = new Vector2(0f, 42f);
            footerRect.anchoredPosition = new Vector2(0f, 8f);
            footerText.raycastTarget = false;
        }

        private TextMeshProUGUI CreateStepperSettingRow(
            Transform parent,
            int rowIndex,
            string title,
            string subtitle,
            UnityEngine.Events.UnityAction onDecrease,
            UnityEngine.Events.UnityAction onIncrease
        )
        {
            RectTransform row = CreateSettingsRowContainer(parent, $"StepperRow_{rowIndex}", rowIndex);

            TextMeshProUGUI titleText = ExperimentRuntimeUi.CreateText(
                "Title",
                row,
                title,
                21f,
                FontStyles.Bold,
                TextAlignmentOptions.TopLeft,
                Color.white
            );
            titleText.rectTransform.offsetMin = new Vector2(18f, 46f);
            titleText.rectTransform.offsetMax = new Vector2(-300f, -10f);
            titleText.raycastTarget = false;

            TextMeshProUGUI subtitleText = ExperimentRuntimeUi.CreateText(
                "Subtitle",
                row,
                subtitle,
                15f,
                FontStyles.Normal,
                TextAlignmentOptions.BottomLeft,
                new Color(0.8f, 0.86f, 0.95f, 0.94f)
            );
            subtitleText.rectTransform.offsetMin = new Vector2(18f, 10f);
            subtitleText.rectTransform.offsetMax = new Vector2(-300f, -42f);
            subtitleText.raycastTarget = false;

            TextMeshProUGUI valueText = ExperimentRuntimeUi.CreateText(
                "Value",
                row,
                string.Empty,
                19f,
                FontStyles.Bold,
                TextAlignmentOptions.Center,
                new Color(1f, 0.94f, 0.74f, 1f)
            );
            RectTransform valueRect = valueText.rectTransform;
            valueRect.anchorMin = new Vector2(1f, 0.5f);
            valueRect.anchorMax = new Vector2(1f, 0.5f);
            valueRect.pivot = new Vector2(1f, 0.5f);
            valueRect.sizeDelta = new Vector2(SettingsValueFieldWidth, 34f);
            valueRect.anchoredPosition = new Vector2(-SettingsValueFieldRightOffset, 8f);
            valueText.raycastTarget = false;
            valueText.horizontalAlignment = HorizontalAlignmentOptions.Center;
            valueText.verticalAlignment = VerticalAlignmentOptions.Middle;

            CreateCompactActionButton(
                row,
                "DecreaseButton",
                "-",
                new Vector2(
                    -(SettingsValueFieldRightOffset + SettingsValueButtonSpacing),
                    8f
                ),
                onDecrease
            );

            CreateCompactActionButton(
                row,
                "IncreaseButton",
                "+",
                new Vector2(
                    -(SettingsValueFieldRightOffset - SettingsValueButtonSpacing),
                    8f
                ),
                onIncrease
            );

            return valueText;
        }

        private TextMeshProUGUI CreateToggleSettingRow(
            Transform parent,
            int rowIndex,
            string title,
            string subtitle,
            UnityEngine.Events.UnityAction onToggle
        )
        {
            RectTransform row = CreateSettingsRowContainer(parent, $"ToggleRow_{rowIndex}", rowIndex);

            TextMeshProUGUI titleText = ExperimentRuntimeUi.CreateText(
                "Title",
                row,
                title,
                21f,
                FontStyles.Bold,
                TextAlignmentOptions.TopLeft,
                Color.white
            );
            titleText.rectTransform.offsetMin = new Vector2(18f, 46f);
            titleText.rectTransform.offsetMax = new Vector2(-300f, -10f);
            titleText.raycastTarget = false;

            TextMeshProUGUI subtitleText = ExperimentRuntimeUi.CreateText(
                "Subtitle",
                row,
                subtitle,
                15f,
                FontStyles.Normal,
                TextAlignmentOptions.BottomLeft,
                new Color(0.8f, 0.86f, 0.95f, 0.94f)
            );
            subtitleText.rectTransform.offsetMin = new Vector2(18f, 10f);
            subtitleText.rectTransform.offsetMax = new Vector2(-300f, -42f);
            subtitleText.raycastTarget = false;

            Button toggleButton = ExperimentRuntimeUi.CreateButton(
                "ToggleButton",
                row,
                new Color(0.23f, 0.35f, 0.22f, 1f)
            );
            RectTransform toggleRect = toggleButton.GetComponent<RectTransform>();
            toggleRect.anchorMin = new Vector2(1f, 0.5f);
            toggleRect.anchorMax = new Vector2(1f, 0.5f);
            toggleRect.pivot = new Vector2(1f, 0.5f);
            toggleRect.sizeDelta = new Vector2(218f, 46f);
            toggleRect.anchoredPosition = new Vector2(-18f, 8f);
            toggleButton.onClick.RemoveAllListeners();
            toggleButton.onClick.AddListener(onToggle);

            TextMeshProUGUI stateText = CreateButtonText(
                toggleButton.transform,
                "StateLabel",
                string.Empty,
                18f,
                FontStyles.Bold,
                TextAlignmentOptions.Center,
                Color.white,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 0.5f),
                Vector2.zero,
                Vector2.zero,
                new Vector4(8f, 8f, 8f, 8f),
                false
            );
            stateText.raycastTarget = false;
            return stateText;
        }

        private RectTransform CreateSettingsRowContainer(Transform parent, string name, int rowIndex)
        {
            RectTransform row = ExperimentRuntimeUi.CreateUiObject(
                name,
                parent,
                new Vector2(0f, 1f),
                new Vector2(1f, 1f)
            );
            row.pivot = new Vector2(0.5f, 1f);
            row.sizeDelta = new Vector2(0f, 94f);
            row.anchoredPosition = new Vector2(0f, -(rowIndex * 108f));
            ExperimentRuntimeUi.AddPanelImage(
                row,
                new Color(0.11f, 0.13f, 0.18f, 0.98f)
            ).raycastTarget = false;
            return row;
        }

        private Button CreateCompactActionButton(
            Transform parent,
            string name,
            string label,
            Vector2 anchoredPosition,
            UnityEngine.Events.UnityAction onClick
        )
        {
            Button button = ExperimentRuntimeUi.CreateButton(
                name,
                parent,
                new Color(0.95f, 0.45f, 0.05f, 1f)
            );
            RectTransform buttonRect = button.GetComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(1f, 0.5f);
            buttonRect.anchorMax = new Vector2(1f, 0.5f);
            buttonRect.pivot = new Vector2(1f, 0.5f);
            buttonRect.sizeDelta = new Vector2(58f, 44f);
            buttonRect.anchoredPosition = anchoredPosition;
            button.onClick.RemoveAllListeners();
            button.onClick.AddListener(onClick);

            TextMeshProUGUI buttonLabel = CreateButtonText(
                button.transform,
                "ButtonLabel",
                label,
                24f,
                FontStyles.Bold,
                TextAlignmentOptions.Center,
                Color.white,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 0.5f),
                Vector2.zero,
                Vector2.zero,
                new Vector4(8f, 8f, 8f, 8f),
                false
            );
            buttonLabel.raycastTarget = false;
            return button;
        }

        private void SetActiveTab(SelectionTab tab)
        {
            activeTab = tab;

            if (videosTabContentRoot != null)
            {
                videosTabContentRoot.gameObject.SetActive(tab == SelectionTab.Videos);
            }

            if (settingsTabContentRoot != null)
            {
                settingsTabContentRoot.gameObject.SetActive(tab == SelectionTab.Settings);
            }

            UpdateTabButtonStyle(
                videosTabButton,
                videosTabButtonLabel,
                tab == SelectionTab.Videos
            );
            UpdateTabButtonStyle(
                settingsTabButton,
                settingsTabButtonLabel,
                tab == SelectionTab.Settings
            );
        }

        private static void UpdateTabButtonStyle(Button button, TextMeshProUGUI label, bool isActive)
        {
            if (button == null)
            {
                return;
            }

            Image buttonImage = button.targetGraphic as Image;
            if (buttonImage != null)
            {
                buttonImage.color = isActive
                    ? new Color(0.95f, 0.45f, 0.05f, 1f)
                    : new Color(0.22f, 0.27f, 0.36f, 1f);
            }

            if (label != null)
            {
                label.color = isActive
                    ? Color.white
                    : new Color(0.83f, 0.88f, 0.96f, 0.98f);
            }
        }

        private void RefreshRuntimeSettingsUi()
        {
            if (countdownSecondsValueText != null)
            {
                countdownSecondsValueText.text = $"{ExperimentRuntimeSettings.CountdownSeconds:0} s";
            }

            if (videoVolumeValueText != null)
            {
                videoVolumeValueText.text = $"{Mathf.RoundToInt(ExperimentRuntimeSettings.VideoVolume * 100f)}%";
            }

            if (countdownBeepStateText != null)
            {
                countdownBeepStateText.text = ExperimentRuntimeSettings.CountdownBeepEnabled
                    ? "Activado"
                    : "Desactivado";
            }

            if (countdownBeepVolumeValueText != null)
            {
                countdownBeepVolumeValueText.text =
                    $"{Mathf.RoundToInt(ExperimentRuntimeSettings.CountdownBeepVolume * 100f)}%";
                countdownBeepVolumeValueText.color = ExperimentRuntimeSettings.CountdownBeepEnabled
                    ? new Color(1f, 0.94f, 0.74f, 1f)
                    : new Color(0.66f, 0.71f, 0.79f, 0.92f);
            }
        }

        private void AdjustCountdownSeconds(float delta)
        {
            ExperimentRuntimeSettings.SetCountdownSeconds(
                ExperimentRuntimeSettings.CountdownSeconds + delta
            );
            RefreshRuntimeSettingsUi();
        }

        private void AdjustVideoVolume(float delta)
        {
            ExperimentRuntimeSettings.SetVideoVolume(
                ExperimentRuntimeSettings.VideoVolume + delta
            );
            RefreshRuntimeSettingsUi();
        }

        private void ToggleCountdownBeep()
        {
            ExperimentRuntimeSettings.SetCountdownBeepEnabled(
                !ExperimentRuntimeSettings.CountdownBeepEnabled
            );
            RefreshRuntimeSettingsUi();
        }

        private void AdjustCountdownBeepVolume(float delta)
        {
            ExperimentRuntimeSettings.SetCountdownBeepVolume(
                ExperimentRuntimeSettings.CountdownBeepVolume + delta
            );
            RefreshRuntimeSettingsUi();
        }

        private void ConfigurePresentationCanvas(GameObject canvasObject, RectTransform canvasRect)
        {
            GraphicRaycaster graphicRaycaster = canvasObject.GetComponent<GraphicRaycaster>();
            if (graphicRaycaster == null)
            {
                graphicRaycaster = canvasObject.AddComponent<GraphicRaycaster>();
            }

            graphicRaycaster.ignoreReversedGraphics = true;

            if (presentationCamera == null)
            {
                Debug.LogWarning("[ExperimentSelectionSceneController] No presentation camera found. Falling back to ScreenSpaceOverlay.");
                rootCanvas.renderMode = RenderMode.ScreenSpaceOverlay;
                return;
            }

            rootCanvasRect = canvasRect;
            rootCanvas.renderMode = RenderMode.WorldSpace;
            rootCanvas.worldCamera = presentationCamera;
            rootCanvas.sortingOrder = 5000;
            rootCanvas.overrideSorting = true;

            EnsureCanvasRaycasters(canvasObject);

            canvasRect.anchorMin = new Vector2(0.5f, 0.5f);
            canvasRect.anchorMax = new Vector2(0.5f, 0.5f);
            canvasRect.pivot = new Vector2(0.5f, 0.5f);
            canvasRect.sizeDelta = new Vector2(1400f, 800f);

            cachedCanvasWorldPosition = ResolveSelectionCanvasWorldPosition(presentationCamera);
            hasCachedCanvasTransform = true;

            canvasRect.position = cachedCanvasWorldPosition;
            canvasRect.rotation = Quaternion.identity;
            canvasRect.localScale = Vector3.one * SelectionCanvasScale;

            Debug.Log(
                $"[ExperimentSelectionSceneController] Selection canvas fixed in scene space from camera '{presentationCamera.name}' " +
                $"at world position {canvasRect.position}, " +
                $"rotation {canvasRect.rotation.eulerAngles}, " +
                $"scale ({canvasRect.localScale.x:F5}, {canvasRect.localScale.y:F5}, {canvasRect.localScale.z:F5})."
            );
        }

        private void MaintainPresentationCanvasTransform()
        {
            if (!hasCachedCanvasTransform || rootCanvas == null || rootCanvasRect == null)
            {
                return;
            }

            if (rootCanvas.renderMode != RenderMode.WorldSpace)
            {
                return;
            }

            rootCanvasRect.position = cachedCanvasWorldPosition;
            rootCanvasRect.rotation = Quaternion.identity;
            rootCanvasRect.localScale = Vector3.one * SelectionCanvasScale;
        }

        private static Vector3 ResolveSelectionCanvasWorldPosition(Camera camera)
        {
            float currentCameraHeight = camera != null ? camera.transform.position.y : 0f;
            float anchoredHeight = Mathf.Max(
                SelectionCanvasMinimumHeightMeters,
                currentCameraHeight + SelectionCanvasHeightOffsetMeters
            );

            return new Vector3(0f, anchoredHeight, SelectionCanvasWorldDepthMeters);
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

        private static void EnsureTrackedVrCamera(Camera camera)
        {
            if (camera == null)
            {
                return;
            }

            if (HierarchyHasTrackedPoseDriver(camera.transform))
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

        private static bool HierarchyHasTrackedPoseDriver(Transform current)
        {
            while (current != null)
            {
                if (current.GetComponent<UnityEngine.SpatialTracking.TrackedPoseDriver>() != null)
                {
                    return true;
                }

                if (current.GetComponent<TrackedPoseDriver>() != null)
                {
                    return true;
                }

                current = current.parent;
            }

            return false;
        }

        private void PopulateStimulusList()
        {
            if (listContentRoot == null)
            {
                Debug.LogWarning("[ExperimentSelectionSceneController] Cannot populate list: listContentRoot is null.");
                return;
            }

            for (int i = listContentRoot.childCount - 1; i >= 0; i--)
            {
                Transform child = listContentRoot.GetChild(i);
                child.SetParent(null, false);
                Destroy(child.gameObject);
            }

            stimulusButtons.Clear();
            firstStimulusButton = null;

            List<ExperimentStimulusDefinition> stimuli = DiscoverAvailableStimuli();

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

                CreateStimulusButton(stimulus, i);
            }

            ConfigureButtonNavigation();

            if (sourceSummaryText != null)
            {
                sourceSummaryText.text = stimuli.Count > 0
                    ? IncludeStreamingAssetsMirror
                        ? $"Estimulos disponibles: {stimuli.Count} | repo: {repositoryCount} | mirror: {streamingCount}"
                        : $"Estimulos disponibles: {stimuli.Count} | repo: {repositoryCount}"
                    : "No se ha encontrado ningun estimulo listo.";
            }

            if (statusText != null)
            {
                statusText.text = stimuli.Count > 0
                    ? "Selecciona un video para abrir la escena VR base y lanzar la cuenta atras."
                    : "No hay videos listos. Revisa `data/input_videos` y `data/processed`.";
            }

            if (stimuli.Count == 0)
            {
                RectTransform emptyState = ExperimentRuntimeUi.CreateUiObject(
                    "EmptyState",
                    listContentRoot,
                    new Vector2(0f, 1f),
                    new Vector2(1f, 1f)
                );

                emptyState.pivot = new Vector2(0.5f, 1f);
                emptyState.offsetMin = new Vector2(0f, -180f);
                emptyState.offsetMax = new Vector2(0f, 0f);

                ExperimentRuntimeUi.AddPanelImage(
                    emptyState,
                    new Color(0.16f, 0.11f, 0.11f, 0.95f)
                );

                TextMeshProUGUI emptyText = ExperimentRuntimeUi.CreateText(
                    "EmptyLabel",
                    emptyState,
                    "No hay nada seleccionable todavia.\n\nGenera un video preprocesado con la pipeline.",
                    22f,
                    FontStyles.Normal,
                    TextAlignmentOptions.Center,
                    new Color(1f, 0.9f, 0.86f, 1f)
                );

                emptyText.raycastTarget = false;
            }

            Canvas.ForceUpdateCanvases();
            LayoutRebuilder.ForceRebuildLayoutImmediate(listContentRoot);

            Debug.Log(
                $"[ExperimentSelectionSceneController] PopulateStimulusList completed. " +
                $"Stimuli: {stimuli.Count}, content children: {listContentRoot.childCount}"
            );

            if (EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(null);
            }
        }

        private void CreateStimulusButton(ExperimentStimulusDefinition stimulus, int index)
        {
            Button button = CreateStimulusButtonInstance(stimulus);
            if (button == null)
            {
                Debug.LogWarning($"[ExperimentSelectionSceneController] Could not create button for stimulus: {stimulus.DisplayName}");
                return;
            }

            button.onClick.RemoveAllListeners();
            button.onClick.AddListener(() => SelectStimulus(stimulus));
            button.interactable = true;

            stimulusButtons.Add(button);

            if (firstStimulusButton == null)
            {
                firstStimulusButton = button;
            }

            RectTransform buttonRect = button.GetComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0f, 1f);
            buttonRect.anchorMax = new Vector2(1f, 1f);
            buttonRect.pivot = new Vector2(0.5f, 1f);

            float y = -StimulusButtonTopPadding - (index * (StimulusButtonHeight + StimulusButtonSpacing));

            buttonRect.offsetMin = new Vector2(0f, y - StimulusButtonHeight);
            buttonRect.offsetMax = new Vector2(0f, y);

            Debug.Log(
                $"[ExperimentSelectionSceneController] Button rect placed: {button.name} " +
                $"offsetMin={buttonRect.offsetMin}, offsetMax={buttonRect.offsetMax}"
            );

            Outline outline = button.gameObject.AddComponent<Outline>();
            outline.effectColor = new Color(1f, 0.9f, 0.35f, 0.9f);
            outline.effectDistance = new Vector2(2f, -2f);

            TextMeshProUGUI title = CreateButtonText(
                button.transform,
                "Title",
                stimulus.DisplayName,
                24f,
                FontStyles.Bold,
                TextAlignmentOptions.Left,
                Color.white,
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 1f),
                new Vector2(0f, 34f),
                new Vector2(0f, -6f),
                new Vector4(20f, 6f, 20f, 0f),
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
                15f,
                FontStyles.Normal,
                TextAlignmentOptions.Left,
                new Color(1f, 0.95f, 0.82f, 0.98f),
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 1f),
                new Vector2(0f, 28f),
                new Vector2(0f, -40f),
                new Vector4(20f, 4f, 20f, 8f),
                false
            );

            details.raycastTarget = false;
            details.overflowMode = TextOverflowModes.Ellipsis;
        }

        private Button CreateStimulusButtonInstance(ExperimentStimulusDefinition stimulus)
        {
            if (sceneStimulusButtonTemplate != null && preferSceneUi)
            {
                Button buttonInstance = Instantiate(sceneStimulusButtonTemplate, listContentRoot);
                buttonInstance.name = $"StimulusButton_{stimulus.SequenceName}";
                buttonInstance.gameObject.SetActive(true);
                return buttonInstance;
            }

            return ExperimentRuntimeUi.CreateButton(
                $"StimulusButton_{stimulus.SequenceName}",
                listContentRoot,
                new Color(0.95f, 0.45f, 0.05f, 1f)
            );
        }

        private void ConfigureButtonNavigation()
        {
            for (int i = 0; i < stimulusButtons.Count; i++)
            {
                Button current = stimulusButtons[i];

                Navigation navigation = new Navigation
                {
                    mode = Navigation.Mode.None
                };

                current.navigation = navigation;
            }
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
            textComponent.textWrappingMode = wrapText ? TextWrappingModes.Normal : TextWrappingModes.NoWrap;

            return textComponent;
        }

        private void SelectStimulus(ExperimentStimulusDefinition stimulus)
        {
            if (isLoadingSelection)
            {
                return;
            }

            isLoadingSelection = true;

            Debug.Log(
                $"[ExperimentSelectionSceneController] Selected stimulus: {stimulus.DisplayName} | " +
                $"video={stimulus.VideoFileName} | sequence={stimulus.SequenceName} | " +
                $"scene={ResolvePlaybackSceneName()}"
            );

            ExperimentSessionState.SetSelectedStimulus(
                stimulus,
                lockPlaybackStart: true,
                countdownSeconds: ExperimentRuntimeSettings.CountdownSeconds,
                videoVolume: ExperimentRuntimeSettings.VideoVolume,
                countdownBeepEnabled: ExperimentRuntimeSettings.CountdownBeepEnabled,
                countdownBeepVolume: ExperimentRuntimeSettings.CountdownBeepVolume
            );

            if (statusText != null)
            {
                statusText.text = $"Abriendo escena VR base para: {stimulus.DisplayName}";
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

        private static List<ExperimentStimulusDefinition> DiscoverAvailableStimuli()
        {
            return ExperimentStimulusCatalog.DiscoverAvailableStimuli(
                includeStreamingAssetsMirror: IncludeStreamingAssetsMirror
            );
        }

        private void EnsureCanvasRaycasters(GameObject canvasObject)
        {
            if (canvasObject == null)
            {
                return;
            }

            GraphicRaycaster graphicRaycaster = canvasObject.GetComponent<GraphicRaycaster>();
            if (graphicRaycaster == null)
            {
                graphicRaycaster = canvasObject.AddComponent<GraphicRaycaster>();
            }

            graphicRaycaster.enabled = true;
            graphicRaycaster.ignoreReversedGraphics = false;

            TrackedDeviceRaycaster trackedDeviceRaycaster = canvasObject.GetComponent<TrackedDeviceRaycaster>();
            if (trackedDeviceRaycaster == null)
            {
                trackedDeviceRaycaster = canvasObject.AddComponent<TrackedDeviceRaycaster>();
            }

            trackedDeviceRaycaster.enabled = true;
            trackedDeviceRaycaster.checkFor2DOcclusion = false;
            trackedDeviceRaycaster.checkFor3DOcclusion = false;
        }

        private void DebugRuntimeVrInput()
        {
            if (Time.unscaledTime < nextInputDebugLogTime)
            {
                return;
            }

            nextInputDebugLogTime = Time.unscaledTime + 1f;

            if (debugTrackedPositionAction == null ||
                debugTrackedRotationAction == null ||
                debugClickAction == null)
            {
                return;
            }

            Vector3 position = debugTrackedPositionAction.ReadValue<Vector3>();
            Quaternion rotation = debugTrackedRotationAction.ReadValue<Quaternion>();
            float click = debugClickAction.ReadValue<float>();

            Debug.Log(
                $"[ExperimentSelectionSceneController] XR UI input | " +
                $"pos={position:F3} | " +
                $"rot=({rotation.x:F3}, {rotation.y:F3}, {rotation.z:F3}, {rotation.w:F3}) | " +
                $"click={click:F2} | " +
                $"posControl={debugTrackedPositionAction.activeControl?.path ?? "none"} | " +
                $"rotControl={debugTrackedRotationAction.activeControl?.path ?? "none"} | " +
                $"clickControl={debugClickAction.activeControl?.path ?? "none"}"
            );
        }

    }

}
