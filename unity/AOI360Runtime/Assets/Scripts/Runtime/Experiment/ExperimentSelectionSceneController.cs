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
            "Phase0_360Playback_VR_sampleRIG"
        };

        private const string RuntimeObjectName = "ExperimentSelectionSceneController_Runtime";
        private const string RuntimeCanvasName = "ExperimentSelectionCanvas_Runtime";
        private const float UiReferencePixelsPerUnit = 100f;
        private const float UiDynamicPixelsPerUnit = 96f;
        private const float SelectionCanvasWorldDepthMeters = 2.6f;
        private const float SelectionCanvasScale = 0.0015f;
        private const float SelectionCanvasMinimumHeightMeters = 1.55f;
        private const float SelectionCanvasHeightOffsetMeters = 0.18f;

        private const float StimulusButtonHeight = 112f;
        private const float StimulusButtonSpacing = 18f;
        private const float StimulusButtonTopPadding = 8f;

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
        private TextMeshProUGUI statusText;
        private TextMeshProUGUI sourceSummaryText;
        private Camera presentationCamera;
        private bool isLoadingSelection;
        private bool hasCachedCanvasTransform;
        private InputActionAsset runtimeUiActionsAsset;
        private Button firstStimulusButton;
        private Vector3 cachedCanvasWorldPosition;
        private static bool sceneHookRegistered;

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

            eventSystem.sendNavigationEvents = true;

            Debug.Log("[ExperimentSelectionSceneController] EventSystem configured for Input System + XR tracked device UI.");
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
            trackedDevicePositionAction.AddBinding("<XRController>/devicePosition");
            trackedDevicePositionAction.AddBinding("<XRController>{LeftHand}/devicePosition");
            trackedDevicePositionAction.AddBinding("<XRController>{RightHand}/devicePosition");
            trackedDevicePositionAction.AddBinding("<XRController>/pointerPosition");
            trackedDevicePositionAction.AddBinding("<XRController>{LeftHand}/pointerPosition");
            trackedDevicePositionAction.AddBinding("<XRController>{RightHand}/pointerPosition");
            trackedDevicePositionAction.AddBinding("<TrackedDevice>/devicePosition");

            InputAction trackedDeviceOrientationAction = map.AddAction(
                "TrackedDeviceOrientation",
                InputActionType.PassThrough
            );
            trackedDeviceOrientationAction.expectedControlType = "Quaternion";
            trackedDeviceOrientationAction.AddBinding("<XRController>/deviceRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>{LeftHand}/deviceRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>{RightHand}/deviceRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>{LeftHand}/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<XRController>{RightHand}/pointerRotation");
            trackedDeviceOrientationAction.AddBinding("<TrackedDevice>/deviceRotation");

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

            clickAction.AddBinding("<XRController>/triggerPressed");
            clickAction.AddBinding("<XRController>{LeftHand}/triggerPressed");
            clickAction.AddBinding("<XRController>{RightHand}/triggerPressed");

            clickAction.AddBinding("<XRController>{LeftHand}/primaryButton");
            clickAction.AddBinding("<XRController>{RightHand}/primaryButton");

            clickAction.AddBinding("<XRController>{LeftHand}/gripPressed");
            clickAction.AddBinding("<XRController>{RightHand}/gripPressed");

            clickAction.AddBinding("<XRController>{LeftHand}/trigger").WithInteraction("Press");
            clickAction.AddBinding("<XRController>{RightHand}/trigger").WithInteraction("Press");
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

            submitAction.AddBinding("<XRController>/triggerPressed");
            submitAction.AddBinding("<XRController>{LeftHand}/triggerPressed");
            submitAction.AddBinding("<XRController>{RightHand}/triggerPressed");

            submitAction.AddBinding("<XRController>{LeftHand}/primaryButton");
            submitAction.AddBinding("<XRController>{RightHand}/primaryButton");

            submitAction.AddBinding("<XRController>{LeftHand}/gripPressed");
            submitAction.AddBinding("<XRController>{RightHand}/gripPressed");

            submitAction.AddBinding("<XRController>{LeftHand}/trigger").WithInteraction("Press");
            submitAction.AddBinding("<XRController>{RightHand}/trigger").WithInteraction("Press");
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

            moveAction.AddBinding("<XRController>{LeftHand}/thumbstick");
            moveAction.AddBinding("<XRController>{RightHand}/thumbstick");
            moveAction.AddBinding("<XRController>{LeftHand}/primary2DAxis");
            moveAction.AddBinding("<XRController>{RightHand}/primary2DAxis");
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

            modal.sizeDelta = new Vector2(1080f, 700f);
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
                40f,
                FontStyles.Bold,
                TextAlignmentOptions.MidlineLeft,
                Color.white
            );

            RectTransform titleRect = titleText.rectTransform;
            titleRect.anchorMin = new Vector2(0f, 1f);
            titleRect.anchorMax = new Vector2(1f, 1f);
            titleRect.pivot = new Vector2(0.5f, 1f);
            titleRect.sizeDelta = new Vector2(0f, 80f);
            titleRect.anchoredPosition = new Vector2(0f, -10f);
            titleText.raycastTarget = false;

            TextMeshProUGUI subtitleText = ExperimentRuntimeUi.CreateText(
                "Subtitle",
                modal,
                "Elige un estimulo procesado. Todos los botones abren la misma escena VR base y cambian el video y los AOIs. Usa gatillo / Enter / boton principal para confirmar.",
                22f,
                FontStyles.Normal,
                TextAlignmentOptions.TopLeft,
                new Color(0.82f, 0.87f, 0.96f, 0.92f)
            );

            RectTransform subtitleRect = subtitleText.rectTransform;
            subtitleRect.anchorMin = new Vector2(0f, 1f);
            subtitleRect.anchorMax = new Vector2(1f, 1f);
            subtitleRect.pivot = new Vector2(0.5f, 1f);
            subtitleRect.sizeDelta = new Vector2(0f, 70f);
            subtitleRect.anchoredPosition = new Vector2(0f, -84f);
            subtitleText.raycastTarget = false;

            RectTransform listPanel = ExperimentRuntimeUi.CreateUiObject(
                "ListPanel",
                modal,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );

            listPanel.offsetMin = new Vector2(40f, 140f);
            listPanel.offsetMax = new Vector2(-40f, -170f);

            Image listPanelImage = ExperimentRuntimeUi.AddPanelImage(
                listPanel,
                new Color(0.05f, 0.06f, 0.09f, 0.98f)
            );
            listPanelImage.raycastTarget = false;

            listContentRoot = ExperimentRuntimeUi.CreateUiObject(
                "Content",
                listPanel,
                new Vector2(0f, 0f),
                new Vector2(1f, 1f)
            );

            listContentRoot.offsetMin = new Vector2(20f, 20f);
            listContentRoot.offsetMax = new Vector2(-20f, -20f);
            listContentRoot.pivot = new Vector2(0.5f, 0.5f);
            listContentRoot.anchoredPosition = Vector2.zero;
            listContentRoot.sizeDelta = Vector2.zero;

            Debug.Log("[ExperimentSelectionSceneController] Simple visible list content created without ScrollRect/Mask.");

            sourceSummaryText = ExperimentRuntimeUi.CreateText(
                "SourceSummary",
                modal,
                string.Empty,
                22f,
                FontStyles.Normal,
                TextAlignmentOptions.BottomLeft,
                new Color(0.78f, 0.84f, 0.93f, 0.95f)
            );

            RectTransform sourceSummaryRect = sourceSummaryText.rectTransform;
            sourceSummaryRect.anchorMin = new Vector2(0f, 0f);
            sourceSummaryRect.anchorMax = new Vector2(1f, 0f);
            sourceSummaryRect.pivot = new Vector2(0.5f, 0f);
            sourceSummaryRect.sizeDelta = new Vector2(0f, 58f);
            sourceSummaryRect.anchoredPosition = new Vector2(0f, 86f);
            sourceSummaryText.raycastTarget = false;

            statusText = ExperimentRuntimeUi.CreateText(
                "Status",
                modal,
                "Esperando seleccion...",
                24f,
                FontStyles.Bold,
                TextAlignmentOptions.BottomLeft,
                new Color(0.96f, 0.82f, 0.48f, 1f)
            );

            RectTransform statusRect = statusText.rectTransform;
            statusRect.anchorMin = new Vector2(0f, 0f);
            statusRect.anchorMax = new Vector2(1f, 0f);
            statusRect.pivot = new Vector2(0.5f, 0f);
            statusRect.sizeDelta = new Vector2(0f, 70f);
            statusRect.anchoredPosition = new Vector2(0f, 20f);
            statusText.raycastTarget = false;
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

            if (canvasObject.GetComponent<TrackedDeviceRaycaster>() == null)
            {
                canvasObject.AddComponent<TrackedDeviceRaycaster>();
            }

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

                CreateStimulusButton(stimulus, i);
            }

            ConfigureButtonNavigation();

            if (sourceSummaryText != null)
            {
                sourceSummaryText.text = stimuli.Count > 0
                    ? $"Estimulos disponibles: {stimuli.Count} | repo: {repositoryCount} | mirror: {streamingCount}"
                    : "No se ha encontrado ningun estimulo listo.";
            }

            if (statusText != null)
            {
                statusText.text = stimuli.Count > 0
                    ? "Selecciona un video para abrir la escena VR base y lanzar la cuenta atras."
                    : "No hay videos listos. Revisa `data/input_videos` y `data/processed`, o sincroniza `StreamingAssets`.";
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

            if (firstStimulusButton != null && EventSystem.current != null)
            {
                EventSystem.current.SetSelectedGameObject(firstStimulusButton.gameObject);
                Debug.Log($"[ExperimentSelectionSceneController] First selected button: {firstStimulusButton.name}");
            }
            else
            {
                Debug.LogWarning("[ExperimentSelectionSceneController] No first stimulus button selected.");
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
                30f,
                FontStyles.Bold,
                TextAlignmentOptions.Left,
                Color.white,
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 1f),
                new Vector2(0f, 44f),
                new Vector2(0f, -8f),
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
                20f,
                FontStyles.Normal,
                TextAlignmentOptions.Left,
                new Color(1f, 0.95f, 0.82f, 0.98f),
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
                new Vector2(0.5f, 1f),
                new Vector2(0f, 40f),
                new Vector2(0f, -56f),
                new Vector4(24f, 4f, 24f, 8f),
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
                    mode = Navigation.Mode.Explicit,
                    selectOnUp = i > 0 ? stimulusButtons[i - 1] : stimulusButtons[i],
                    selectOnDown = i < stimulusButtons.Count - 1 ? stimulusButtons[i + 1] : stimulusButtons[i],
                    selectOnLeft = current,
                    selectOnRight = current
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

            ExperimentSessionState.SetSelectedStimulus(stimulus, lockPlaybackStart: true, countdownSeconds: 5f);

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
    }
}
