using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;

#if UNITY_EDITOR
using UnityEditor;
#endif

namespace AOI360.Runtime.XR
{
    [DefaultExecutionOrder(600)]
    public class RuntimeControllerPoseBridge : MonoBehaviour
    {
        // The bridge recreates controller anchors and pointer rays every time the
        // active scene changes so the menu scene and the playback scene share one
        // consistent XR interaction layout.
        private static readonly string[] TargetSceneNames =
        {
            "Initial_Scene",
            "Phase2_360Playback_VR_sampleRIG"
        };

        private const string RuntimeObjectName = "RuntimeControllerPoseBridge_Runtime";
        private const float PointerLength = 8f;
        private const string LeftControllerPrefabPath =
            "Assets/Samples/VIVE OpenXR Plugin/2.5.0/VIVE OpenXR Samples/Samples/Commons/VRSPrefabs/Controller/Focus3_Left.prefab";
        private const string RightControllerPrefabPath =
            "Assets/Samples/VIVE OpenXR Plugin/2.5.0/VIVE OpenXR Samples/Samples/Commons/VRSPrefabs/Controller/Focus3_Right.prefab";
        private static bool sceneHookRegistered;
        private static readonly Dictionary<int, Material> CompatibleMaterialCache = new();

        private InputAction leftTrackedAction;
        private InputAction leftDevicePositionAction;
        private InputAction leftDeviceRotationAction;
        private InputAction leftPointerPositionAction;
        private InputAction leftPointerRotationAction;

        private InputAction rightTrackedAction;
        private InputAction rightDevicePositionAction;
        private InputAction rightDeviceRotationAction;
        private InputAction rightPointerPositionAction;
        private InputAction rightPointerRotationAction;

        private Transform trackingRoot;
        private Transform leftHandAnchor;
        private Transform rightHandAnchor;
        private Transform leftRayAnchor;
        private Transform rightRayAnchor;

        private GameObject leftBodyVisual;
        private GameObject rightBodyVisual;
        private LineRenderer leftPointerLine;
        private LineRenderer rightPointerLine;

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
        private static void EnsureBridgeAfterSceneLoad()
        {
            EnsureBridgeForScene(SceneManager.GetActiveScene());
        }

        private static void HandleSceneLoaded(Scene scene, LoadSceneMode loadMode)
        {
            EnsureBridgeForScene(scene);
        }

        private static void EnsureBridgeForScene(Scene scene)
        {
            if (!IsTargetScene(scene.name))
            {
                return;
            }

            if (FindBridgeInScene(scene) != null)
            {
                return;
            }

            GameObject runtimeObject = new GameObject(RuntimeObjectName);
            runtimeObject.AddComponent<RuntimeControllerPoseBridge>();
        }

        private static RuntimeControllerPoseBridge FindBridgeInScene(Scene scene)
        {
            if (!scene.isLoaded)
            {
                return null;
            }

            GameObject[] rootObjects = scene.GetRootGameObjects();
            for (int i = 0; i < rootObjects.Length; i++)
            {
                RuntimeControllerPoseBridge bridge =
                    rootObjects[i].GetComponentInChildren<RuntimeControllerPoseBridge>(true);

                if (bridge != null)
                {
                    return bridge;
                }
            }

            return null;
        }

        private void Awake()
        {
            if (!IsTargetScene(SceneManager.GetActiveScene().name))
            {
                enabled = false;
                return;
            }

            CreateActions();
            ResolveAnchors();
            EnsureVisuals();
        }

        private void OnEnable()
        {
            EnableActions();
        }

        private void OnDisable()
        {
            DisableActions();
        }

        private void Update()
        {
            ResolveAnchors();
            EnsureVisuals();

            UpdateController(
                leftTrackedAction,
                leftDevicePositionAction,
                leftDeviceRotationAction,
                leftPointerPositionAction,
                leftPointerRotationAction,
                leftHandAnchor,
                leftRayAnchor,
                leftBodyVisual,
                leftPointerLine
            );

            UpdateController(
                rightTrackedAction,
                rightDevicePositionAction,
                rightDeviceRotationAction,
                rightPointerPositionAction,
                rightPointerRotationAction,
                rightHandAnchor,
                rightRayAnchor,
                rightBodyVisual,
                rightPointerLine
            );
        }

        private void CreateActions()
        {
            leftTrackedAction = CreateButtonAction("<XRController>{LeftHand}/isTracked");
            leftDevicePositionAction = CreatePoseAction("<XRController>{LeftHand}/devicePosition", "Vector3");
            leftDeviceRotationAction = CreatePoseAction("<XRController>{LeftHand}/deviceRotation", "Quaternion");
            leftPointerPositionAction = CreatePoseAction("<XRController>{LeftHand}/pointerPosition", "Vector3");
            leftPointerRotationAction = CreatePoseAction("<XRController>{LeftHand}/pointerRotation", "Quaternion");

            rightTrackedAction = CreateButtonAction("<XRController>{RightHand}/isTracked");
            rightDevicePositionAction = CreatePoseAction("<XRController>{RightHand}/devicePosition", "Vector3");
            rightDeviceRotationAction = CreatePoseAction("<XRController>{RightHand}/deviceRotation", "Quaternion");
            rightPointerPositionAction = CreatePoseAction("<XRController>{RightHand}/pointerPosition", "Vector3");
            rightPointerRotationAction = CreatePoseAction("<XRController>{RightHand}/pointerRotation", "Quaternion");
        }

        private static InputAction CreateButtonAction(string binding)
        {
            return new InputAction(type: InputActionType.Button, binding: binding);
        }

        private static InputAction CreatePoseAction(string binding, string expectedControlType)
        {
            return new InputAction(
                type: InputActionType.PassThrough,
                binding: binding,
                expectedControlType: expectedControlType
            );
        }

        private void EnableActions()
        {
            leftTrackedAction?.Enable();
            leftDevicePositionAction?.Enable();
            leftDeviceRotationAction?.Enable();
            leftPointerPositionAction?.Enable();
            leftPointerRotationAction?.Enable();

            rightTrackedAction?.Enable();
            rightDevicePositionAction?.Enable();
            rightDeviceRotationAction?.Enable();
            rightPointerPositionAction?.Enable();
            rightPointerRotationAction?.Enable();
        }

        private void DisableActions()
        {
            leftTrackedAction?.Disable();
            leftDevicePositionAction?.Disable();
            leftDeviceRotationAction?.Disable();
            leftPointerPositionAction?.Disable();
            leftPointerRotationAction?.Disable();

            rightTrackedAction?.Disable();
            rightDevicePositionAction?.Disable();
            rightDeviceRotationAction?.Disable();
            rightPointerPositionAction?.Disable();
            rightPointerRotationAction?.Disable();
        }

        private void ResolveAnchors()
        {
            trackingRoot = ResolveTrackingRoot();
            if (trackingRoot == null)
            {
                return;
            }

            leftHandAnchor = ResolveOrCreateAnchor("LeftHand", trackingRoot);
            rightHandAnchor = ResolveOrCreateAnchor("RightHand", trackingRoot);
            leftRayAnchor = ResolveOrCreateAnchor("LeftRay", trackingRoot);
            rightRayAnchor = ResolveOrCreateAnchor("RightRay", trackingRoot);
        }

        private Transform ResolveTrackingRoot()
        {
            GameObject viveRayRig = GameObject.Find("VRSRig_withRay");
            if (viveRayRig != null)
            {
                return viveRayRig.transform;
            }

            GameObject viveControllerRig = GameObject.Find("VRSRig_withController");
            if (viveControllerRig != null)
            {
                return viveControllerRig.transform;
            }

            Camera mainCamera = Camera.main;
            if (mainCamera != null)
            {
                Transform parent = mainCamera.transform.parent;
                if (parent != null && parent.parent != null)
                {
                    return parent.parent;
                }

                return parent;
            }

            return null;
        }

        private static Transform ResolveOrCreateAnchor(string name, Transform parent)
        {
            if (parent == null)
            {
                return null;
            }

            Transform existing = FindChildRecursive(parent, name);
            if (existing != null)
            {
                return existing;
            }

            GameObject anchorObject = new GameObject(name);
            Transform anchorTransform = anchorObject.transform;
            anchorTransform.SetParent(parent, false);
            anchorTransform.localPosition = Vector3.zero;
            anchorTransform.localRotation = Quaternion.identity;
            anchorTransform.localScale = Vector3.one;
            return anchorTransform;
        }

        private static Transform FindChildRecursive(Transform parent, string childName)
        {
            if (parent == null)
            {
                return null;
            }

            for (int i = 0; i < parent.childCount; i++)
            {
                Transform child = parent.GetChild(i);
                if (string.Equals(child.name, childName, System.StringComparison.Ordinal))
                {
                    return child;
                }

                Transform nested = FindChildRecursive(child, childName);
                if (nested != null)
                {
                    return nested;
                }
            }

            return null;
        }

        private void EnsureVisuals()
        {
            if (leftHandAnchor != null && leftBodyVisual == null)
            {
                leftBodyVisual = EnsureControllerBodyVisual(
                    "RuntimeLeftControllerBody",
                    leftHandAnchor,
                    LeftControllerPrefabPath,
                    new Color(0.35f, 0.82f, 1f, 1f)
                );
            }

            if (rightHandAnchor != null && rightBodyVisual == null)
            {
                rightBodyVisual = EnsureControllerBodyVisual(
                    "RuntimeRightControllerBody",
                    rightHandAnchor,
                    RightControllerPrefabPath,
                    new Color(1f, 0.82f, 0.35f, 1f)
                );
            }

            if (leftRayAnchor != null && leftPointerLine == null)
            {
                leftPointerLine = CreatePointerLine("RuntimeLeftPointer", leftRayAnchor, new Color(0.35f, 0.82f, 1f, 0.92f));
            }

            if (rightRayAnchor != null && rightPointerLine == null)
            {
                rightPointerLine = CreatePointerLine("RuntimeRightPointer", rightRayAnchor, new Color(1f, 0.82f, 0.35f, 0.92f));
            }
        }

        private static GameObject EnsureControllerBodyVisual(
            string name,
            Transform anchor,
            string prefabPath,
            Color fallbackColor
        )
        {
            if (anchor == null)
            {
                return null;
            }

            Renderer existingRenderer = anchor.GetComponentInChildren<Renderer>(true);
            if (existingRenderer != null)
            {
                Transform visualRoot = ResolveVisualRootUnderAnchor(existingRenderer.transform, anchor);
                GameObject existingVisual = visualRoot != null ? visualRoot.gameObject : existingRenderer.gameObject;
                ApplyCompatibleControllerMaterials(existingVisual, fallbackColor);
                return existingVisual;
            }

            GameObject prefabInstance = TryInstantiateEditorPrefab(name, anchor, prefabPath);
            if (prefabInstance != null)
            {
                ApplyCompatibleControllerMaterials(prefabInstance, fallbackColor);
                return prefabInstance;
            }

            return CreateBodyVisual(name, anchor, fallbackColor);
        }

        private static Transform ResolveVisualRootUnderAnchor(Transform rendererTransform, Transform anchor)
        {
            if (rendererTransform == null || anchor == null)
            {
                return null;
            }

            Transform current = rendererTransform;
            while (current.parent != null && current.parent != anchor)
            {
                current = current.parent;
            }

            return current;
        }

        private static GameObject CreateBodyVisual(string name, Transform parent, Color color)
        {
            GameObject body = GameObject.CreatePrimitive(PrimitiveType.Cube);
            body.name = name;
            body.transform.SetParent(parent, false);
            body.transform.localPosition = new Vector3(0f, -0.012f, 0.06f);
            body.transform.localRotation = Quaternion.identity;
            body.transform.localScale = new Vector3(0.045f, 0.028f, 0.12f);

            Collider bodyCollider = body.GetComponent<Collider>();
            if (bodyCollider != null)
            {
                Object.Destroy(bodyCollider);
            }

            MeshRenderer renderer = body.GetComponent<MeshRenderer>();
            if (renderer != null)
            {
                renderer.sharedMaterial = CreateSharedMaterial(color);
                renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                renderer.receiveShadows = false;
            }

            return body;
        }

        private static LineRenderer CreatePointerLine(string name, Transform parent, Color color)
        {
            GameObject lineObject = new GameObject(name);
            lineObject.transform.SetParent(parent, false);
            lineObject.transform.localPosition = Vector3.zero;
            lineObject.transform.localRotation = Quaternion.identity;
            lineObject.transform.localScale = Vector3.one;

            LineRenderer lineRenderer = lineObject.AddComponent<LineRenderer>();
            lineRenderer.useWorldSpace = false;
            lineRenderer.positionCount = 2;
            lineRenderer.SetPosition(0, Vector3.zero);
            lineRenderer.SetPosition(1, Vector3.forward * PointerLength);
            lineRenderer.startWidth = 0.01f;
            lineRenderer.endWidth = 0.0025f;
            lineRenderer.alignment = LineAlignment.View;
            lineRenderer.numCapVertices = 4;
            lineRenderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            lineRenderer.receiveShadows = false;
            lineRenderer.sharedMaterial = CreateSharedMaterial(color);
            lineRenderer.startColor = color;
            lineRenderer.endColor = new Color(color.r, color.g, color.b, 0.15f);
            return lineRenderer;
        }

        private static Material CreateSharedMaterial(Color color)
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Unlit");
            if (shader == null)
            {
                shader = Shader.Find("Standard");
            }

            if (shader == null)
            {
                shader = Shader.Find("Sprites/Default");
            }

            Material material = new Material(shader);
            material.color = color;
            return material;
        }

        private static void ApplyCompatibleControllerMaterials(GameObject root, Color fallbackColor)
        {
            if (root == null)
            {
                return;
            }

            Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
            for (int i = 0; i < renderers.Length; i++)
            {
                Renderer renderer = renderers[i];
                Material[] sourceMaterials = renderer.sharedMaterials;
                if (sourceMaterials == null || sourceMaterials.Length == 0)
                {
                    continue;
                }

                Material[] compatibleMaterials = new Material[sourceMaterials.Length];
                for (int materialIndex = 0; materialIndex < sourceMaterials.Length; materialIndex++)
                {
                    compatibleMaterials[materialIndex] = CreateCompatibleRuntimeMaterial(
                        sourceMaterials[materialIndex],
                        fallbackColor
                    );
                }

                renderer.sharedMaterials = compatibleMaterials;
                renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                renderer.receiveShadows = false;
            }
        }

        private static Material CreateCompatibleRuntimeMaterial(Material sourceMaterial, Color fallbackColor)
        {
            if (sourceMaterial == null)
            {
                return CreateSharedMaterial(fallbackColor);
            }

            int cacheKey = sourceMaterial.GetInstanceID();
            if (CompatibleMaterialCache.TryGetValue(cacheKey, out Material cachedMaterial) && cachedMaterial != null)
            {
                return cachedMaterial;
            }

            Shader shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null)
            {
                shader = Shader.Find("Universal Render Pipeline/Unlit");
            }

            if (shader == null)
            {
                shader = Shader.Find("Standard");
            }

            Material compatibleMaterial = new Material(shader)
            {
                name = $"{sourceMaterial.name}_RuntimeCompatible"
            };

            Texture baseTexture = sourceMaterial.HasProperty("_BaseMap")
                ? sourceMaterial.GetTexture("_BaseMap")
                : sourceMaterial.HasProperty("_MainTex")
                    ? sourceMaterial.GetTexture("_MainTex")
                    : null;

            Color baseColor = fallbackColor;
            if (sourceMaterial.HasProperty("_BaseColor"))
            {
                baseColor = sourceMaterial.GetColor("_BaseColor");
            }
            else if (sourceMaterial.HasProperty("_Color"))
            {
                baseColor = sourceMaterial.GetColor("_Color");
            }

            if (compatibleMaterial.HasProperty("_BaseMap"))
            {
                compatibleMaterial.SetTexture("_BaseMap", baseTexture);
            }

            if (compatibleMaterial.HasProperty("_MainTex"))
            {
                compatibleMaterial.SetTexture("_MainTex", baseTexture);
            }

            if (compatibleMaterial.HasProperty("_BaseColor"))
            {
                compatibleMaterial.SetColor("_BaseColor", baseColor);
            }

            if (compatibleMaterial.HasProperty("_Color"))
            {
                compatibleMaterial.SetColor("_Color", baseColor);
            }

            bool isTransparentSource = sourceMaterial.renderQueue >= (int)UnityEngine.Rendering.RenderQueue.Transparent;
            if (isTransparentSource && compatibleMaterial.HasProperty("_Surface"))
            {
                compatibleMaterial.SetFloat("_Surface", 1f);
            }

            if (isTransparentSource && compatibleMaterial.HasProperty("_Blend"))
            {
                compatibleMaterial.SetFloat("_Blend", 0f);
            }

            if (isTransparentSource && compatibleMaterial.HasProperty("_SrcBlend"))
            {
                compatibleMaterial.SetFloat("_SrcBlend", (float)UnityEngine.Rendering.BlendMode.SrcAlpha);
            }

            if (isTransparentSource && compatibleMaterial.HasProperty("_DstBlend"))
            {
                compatibleMaterial.SetFloat("_DstBlend", (float)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
            }

            if (isTransparentSource && compatibleMaterial.HasProperty("_ZWrite"))
            {
                compatibleMaterial.SetFloat("_ZWrite", 0f);
            }

            if (isTransparentSource)
            {
                compatibleMaterial.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
                compatibleMaterial.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            }

            CompatibleMaterialCache[cacheKey] = compatibleMaterial;
            return compatibleMaterial;
        }

        private static void UpdateController(
            InputAction trackedAction,
            InputAction devicePositionAction,
            InputAction deviceRotationAction,
            InputAction pointerPositionAction,
            InputAction pointerRotationAction,
            Transform handAnchor,
            Transform rayAnchor,
            GameObject bodyVisual,
            LineRenderer pointerLine
        )
        {
            Vector3 devicePosition = devicePositionAction != null ? devicePositionAction.ReadValue<Vector3>() : Vector3.zero;
            Quaternion deviceRotation = deviceRotationAction != null
                ? deviceRotationAction.ReadValue<Quaternion>()
                : Quaternion.identity;

            Vector3 pointerPosition = pointerPositionAction != null ? pointerPositionAction.ReadValue<Vector3>() : devicePosition;
            Quaternion pointerRotation = pointerRotationAction != null
                ? pointerRotationAction.ReadValue<Quaternion>()
                : deviceRotation;

            bool explicitTracked = trackedAction != null && trackedAction.ReadValue<float>() > 0.5f;
            bool hasPosePosition = devicePosition.sqrMagnitude > 0.0001f || pointerPosition.sqrMagnitude > 0.0001f;
            bool hasPoseRotation = QuaternionLooksValid(deviceRotation) || QuaternionLooksValid(pointerRotation);
            bool isTracked = explicitTracked || (hasPosePosition && hasPoseRotation);

            if (!isTracked)
            {
                if (bodyVisual != null)
                {
                    bodyVisual.SetActive(false);
                }

                if (pointerLine != null)
                {
                    pointerLine.gameObject.SetActive(false);
                }

                return;
            }

            if (!QuaternionLooksValid(deviceRotation))
            {
                deviceRotation = Quaternion.identity;
            }

            if (!QuaternionLooksValid(pointerRotation))
            {
                pointerRotation = deviceRotation;
            }

            if (pointerPosition.sqrMagnitude <= 0.000001f)
            {
                pointerPosition = devicePosition;
            }

            if (handAnchor != null)
            {
                handAnchor.localPosition = devicePosition;
                handAnchor.localRotation = deviceRotation;
            }

            if (rayAnchor != null)
            {
                rayAnchor.localPosition = pointerPosition;
                rayAnchor.localRotation = pointerRotation;
            }

            if (bodyVisual != null)
            {
                bodyVisual.SetActive(true);
            }

            if (pointerLine != null)
            {
                pointerLine.gameObject.SetActive(true);
                pointerLine.SetPosition(0, Vector3.zero);
                pointerLine.SetPosition(1, Vector3.forward * PointerLength);
            }
        }

        private static bool QuaternionLooksValid(Quaternion rotation)
        {
            float magnitude = rotation.x * rotation.x + rotation.y * rotation.y + rotation.z * rotation.z +
                              rotation.w * rotation.w;
            return magnitude > 0.25f && magnitude < 1.75f;
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

#if UNITY_EDITOR
        private static GameObject TryInstantiateEditorPrefab(string name, Transform parent, string prefabPath)
        {
            if (string.IsNullOrWhiteSpace(prefabPath) || parent == null)
            {
                return null;
            }

            GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null)
            {
                return null;
            }

            Object instance = PrefabUtility.InstantiatePrefab(prefab);
            GameObject gameObject = instance as GameObject;
            if (gameObject == null)
            {
                return null;
            }

            gameObject.name = name;
            gameObject.transform.SetParent(parent, false);
            return gameObject;
        }
#else
        private static GameObject TryInstantiateEditorPrefab(string name, Transform parent, string prefabPath)
        {
            return null;
        }
#endif
    }
}
