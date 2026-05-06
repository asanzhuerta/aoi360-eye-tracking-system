using UnityEngine;

namespace AOI360.Runtime.Mapping
{
    public class SphericalMapper : MonoBehaviour
    {
        [Header("Gaze source")]
        [SerializeField] private Transform gazeDirectionSource;

        [Header("Fallback")]
        [SerializeField] private bool allowFallbackToTransformSource = true;

        [Header("Projection Calibration")]
        [SerializeField] private float yawOffsetDegrees = 180f;
        [SerializeField] private float verticalOffsetDegrees = 0f;
        [SerializeField] private bool flipHorizontally = false;
        [SerializeField] private bool flipVertically = true;

        [Header("Debug")]
        [SerializeField] private bool logValues = true;
        [SerializeField] private int logEveryNFrames = 30;

        private bool hasExternalGazeDirection = false;
        private Vector3 externalGazeDirection = Vector3.forward;

        public bool HasValidDirection { get; private set; }
        public Vector3 CurrentDirection { get; private set; }
        public float CurrentAzimuthRad { get; private set; }
        public float CurrentElevationRad { get; private set; }
        public Vector2 CurrentUV { get; private set; }
        public float YawOffsetDegrees => yawOffsetDegrees;
        public float VerticalOffsetDegrees => verticalOffsetDegrees;
        public bool FlipHorizontally => flipHorizontally;
        public bool FlipVertically => flipVertically;

        private void Update()
        {
            if (!TryGetCurrentDirection(out Vector3 dir))
            {
                ClearComputedState();
                return;
            }

            CurrentDirection = dir;

            // Azimut: ángulo horizontal respecto al eje Z
            float azimuth = Mathf.Atan2(dir.x, dir.z);

            // Elevación: ángulo vertical
            float elevation = Mathf.Asin(Mathf.Clamp(dir.y, -1f, 1f));

            // Conversión a UV equirectangular
            float u = (azimuth + Mathf.PI) / (2f * Mathf.PI);
            float adjustedElevation = elevation + (verticalOffsetDegrees * Mathf.Deg2Rad);
            float v = 0.5f - (adjustedElevation / Mathf.PI);

            u = Mathf.Repeat(u + (yawOffsetDegrees / 360f), 1f);
            if (flipHorizontally)
            {
                u = 1f - u;
            }

            if (flipVertically)
            {
                v = 1f - v;
            }

            CurrentAzimuthRad = azimuth;
            CurrentElevationRad = elevation;
            CurrentUV = new Vector2(Mathf.Repeat(u, 1f), Mathf.Clamp01(v));
            HasValidDirection = true;

            if (Application.isEditor && logValues && Time.frameCount % Mathf.Max(1, logEveryNFrames) == 0)
            {
                Debug.Log(
                    $"[SphericalMapper] dir={CurrentDirection} | az={CurrentAzimuthRad:F3} rad | " +
                    $"el={CurrentElevationRad:F3} rad | uv=({CurrentUV.x:F3}, {CurrentUV.y:F3})"
                );
            }
        }

        public void SetGazeDirectionSource(Transform source)
        {
            gazeDirectionSource = source;
        }

        public void SetExternalGazeDirection(Vector3 direction, bool isValid)
        {
            if (!isValid || direction.sqrMagnitude <= 0.000001f)
            {
                hasExternalGazeDirection = false;
                return;
            }

            externalGazeDirection = direction.normalized;
            hasExternalGazeDirection = true;
        }

        public void SetProjectionCalibration(
            float yawDegrees,
            float verticalDegrees,
            bool horizontalFlip,
            bool verticalFlip)
        {
            yawOffsetDegrees = yawDegrees;
            verticalOffsetDegrees = verticalDegrees;
            flipHorizontally = horizontalFlip;
            flipVertically = verticalFlip;
        }

        public void ClearExternalGazeDirection()
        {
            hasExternalGazeDirection = false;
        }

        private bool TryGetCurrentDirection(out Vector3 direction)
        {
            // Prioridad 1: dirección externa proveniente del eye tracking real
            if (hasExternalGazeDirection)
            {
                direction = externalGazeDirection;
                return true;
            }

            // Prioridad 2: fallback temporal usando la cámara / transform de referencia
            Transform fallbackSource = gazeDirectionSource;
            if (fallbackSource == null || !fallbackSource.gameObject.activeInHierarchy)
            {
                Camera fallbackCamera = Camera.main ?? FindFirstObjectByType<Camera>();
                if (fallbackCamera != null)
                {
                    fallbackSource = fallbackCamera.transform;
                    gazeDirectionSource = fallbackSource;
                }
            }

            if (allowFallbackToTransformSource && fallbackSource != null)
            {
                Vector3 fallbackDirection = fallbackSource.forward;

                if (fallbackDirection.sqrMagnitude > 0.000001f)
                {
                    direction = fallbackDirection.normalized;
                    return true;
                }
            }

            direction = Vector3.zero;
            return false;
        }

        private void ClearComputedState()
        {
            HasValidDirection = false;
            CurrentDirection = Vector3.zero;
            CurrentAzimuthRad = 0f;
            CurrentElevationRad = 0f;
            CurrentUV = Vector2.zero;
        }
    }
}
