using AOI360.Runtime.AOI;
using AOI360.Runtime.Mapping;
using AOI360.Runtime.Video;
using EyeGaze.Runtime.Core;
using EyeGaze.Runtime.Modules;
using TMPro;
using UnityEngine;

namespace AOI360.Runtime.Modules
{
    public class DebugOverlayUI : MonoBehaviour
    {
        [Header("References")]
        [SerializeField] private VideoPlayback videoPlayback;
        [SerializeField] private SphericalMapper sphericalMapper;
        [SerializeField] private AOILookup aoiLookup;
        [SerializeField] private AOISequenceRuntimeLoader aoiSequenceRuntimeLoader;
        [SerializeField] private EyeGazeSystem eyeGazeSystem;
        [SerializeField] private EyeGazeDebugVisualizer debugVisualizer;

        [Header("UI")]
        [SerializeField] private TextMeshProUGUI debugText;
        [SerializeField] private float refreshIntervalSeconds = 0.1f;

        private float nextRefreshTime;

        private void Update()
        {
            if (debugText == null || sphericalMapper == null || aoiLookup == null)
            {
                return;
            }

            if (Time.unscaledTime < nextRefreshTime)
            {
                return;
            }

            nextRefreshTime = Time.unscaledTime + Mathf.Max(0.02f, refreshIntervalSeconds);

            if (debugVisualizer == null)
            {
                debugVisualizer = FindFirstObjectByType<EyeGazeDebugVisualizer>();
            }

            if (eyeGazeSystem == null)
            {
                eyeGazeSystem = FindFirstObjectByType<EyeGazeSystem>();
            }

            if (aoiSequenceRuntimeLoader == null)
            {
                aoiSequenceRuntimeLoader = FindFirstObjectByType<AOISequenceRuntimeLoader>();
            }

            long frameIndex = videoPlayback != null ? videoPlayback.CurrentFrame : -1;
            double videoTime = videoPlayback != null ? videoPlayback.CurrentTime : 0d;

            Vector2 uv = sphericalMapper.CurrentUV;
            float yawOffset = sphericalMapper.YawOffsetDegrees;
            float verticalOffset = sphericalMapper.VerticalOffsetDegrees;
            int aoiId = aoiLookup.CurrentAOIId;
            float confidence = aoiLookup.CurrentAOIConfidence;
            int fixationSteps = debugVisualizer != null ? debugVisualizer.ActiveFixationCommitCount : 0;
            string aoiName = string.IsNullOrWhiteSpace(aoiLookup.CurrentAOIName) ? "-" : aoiLookup.CurrentAOIName;
            string aoiCategory = string.IsNullOrWhiteSpace(aoiLookup.CurrentAOICategory) ? "-" : aoiLookup.CurrentAOICategory;
            string trackingSource = eyeGazeSystem != null ? eyeGazeSystem.CurrentTrackingSource : "-";
            string leftPupil = eyeGazeSystem != null && eyeGazeSystem.LastLeftPupilDiameter >= 0f
                ? eyeGazeSystem.LastLeftPupilDiameter.ToString("F3")
                : "-";
            string rightPupil = eyeGazeSystem != null && eyeGazeSystem.LastRightPupilDiameter >= 0f
                ? eyeGazeSystem.LastRightPupilDiameter.ToString("F3")
                : "-";
            string sequenceFolder = aoiSequenceRuntimeLoader != null && !string.IsNullOrWhiteSpace(aoiSequenceRuntimeLoader.ActiveSequenceFolder)
                ? aoiSequenceRuntimeLoader.ActiveSequenceFolder
                : "-";
            int keyframeFrame = aoiSequenceRuntimeLoader != null ? aoiSequenceRuntimeLoader.CurrentKeyframeFrameIndex : -1;
            string mapFile = aoiSequenceRuntimeLoader != null && !string.IsNullOrWhiteSpace(aoiSequenceRuntimeLoader.CurrentMapFile)
                ? aoiSequenceRuntimeLoader.CurrentMapFile
                : aoiLookup.CurrentTextureName;
            int sequenceAoiCount = aoiSequenceRuntimeLoader != null ? aoiSequenceRuntimeLoader.GlobalAoiCount : 0;
            int keyframeAoiCount = aoiSequenceRuntimeLoader != null ? aoiSequenceRuntimeLoader.CurrentKeyframeAoiCount : 0;

            debugText.text =
                $"Frame: {frameIndex}\n" +
                $"Video Time: {videoTime:F3}\n" +
                $"UV: ({uv.x:F3}, {uv.y:F3})\n" +
                $"Projection: yaw={yawOffset:F1} | vOff={verticalOffset:F1} | fh={(sphericalMapper.FlipHorizontally ? 1 : 0)} | fv={(sphericalMapper.FlipVertically ? 1 : 0)}\n" +
                $"Tracking Source: {trackingSource}\n" +
                $"AOI Seq: {sequenceFolder}\n" +
                $"AOI Keyframe: {keyframeFrame}\n" +
                $"AOI Map: {mapFile}\n" +
                $"AOI ID: {aoiId}\n" +
                $"AOI Name: {aoiName}\n" +
                $"AOI Category: {aoiCategory}\n" +
                $"AOI Conf: {confidence:F2}\n" +
                $"AOI Mode: {aoiLookup.ActiveEncodingLabel}\n" +
                $"AOIs Global/Frame: {sequenceAoiCount} / {keyframeAoiCount}\n" +
                $"Pupils L/R: {leftPupil} / {rightPupil}\n" +
                $"Fixation Steps: {fixationSteps}";
        }
    }
}
