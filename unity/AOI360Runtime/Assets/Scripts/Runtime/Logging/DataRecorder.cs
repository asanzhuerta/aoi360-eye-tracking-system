using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using AOI360.Runtime.AOI;
using AOI360.Runtime.Experiment;
using AOI360.Runtime.Mapping;
using AOI360.Runtime.Video;
using EyeGaze.Runtime.Core;
using EyeGaze.Runtime.Modules;
using UnityEngine;

namespace AOI360.Runtime.Logging
{
    public class DataRecorder : MonoBehaviour
    {
        // DataRecorder persists the fixation-based contract consumed by the
        // analytics stage. It records only committed fixation steps so the CSV
        // remains aligned with the current Phase 0 / Phase 2 runtime design.
        [Header("References")]
        [SerializeField] private VideoPlayback videoPlayback;
        [SerializeField] private SphericalMapper sphericalMapper;
        [SerializeField] private AOILookup aoiLookup;
        [SerializeField] private EyeGazeSystem eyeGazeSystem;
        [SerializeField] private EyeGazeDebugVisualizer debugVisualizer;

        [Header("Recording")]
        [SerializeField] private bool recordOnStart = true;
        [SerializeField] private bool waitUntilVideoPrepared = true;
        [SerializeField] private bool autoExportOnDisable = true;
        [SerializeField] private string participantId = "P001";
        [SerializeField] private string sessionId = "S001";
        [SerializeField] private string videoId = "sample360";
        [SerializeField] private string outputFileName = "phase0_gaze_log.csv";

        [Header("Debug")]
        [SerializeField] private bool logRecordingState = true;
        [SerializeField] private bool logEveryNFrames = false;
        [SerializeField] private int frameLogInterval = 60;

        private readonly List<string> rows = new();
        private bool isRecording = false;
        private float sessionStartTime;
        private int lastExportedFixationSequence;
        private bool hasExportedCurrentRows;

        public bool IsRecording => isRecording;
        public string LastExportPath { get; private set; } = string.Empty;

        private void Start()
        {
            rows.Clear();
            rows.Add(BuildHeader());
            hasExportedCurrentRows = false;
            LastExportPath = string.Empty;
            ResolveReferences();

            if (recordOnStart)
            {
                TryStartRecording();
            }
        }

        private void Update()
        {
            ResolveReferences();

            if (recordOnStart && !isRecording)
            {
                TryStartRecording();
            }

            if (!isRecording || sphericalMapper == null || aoiLookup == null || eyeGazeSystem == null)
            {
                return;
            }

            if (debugVisualizer == null || !debugVisualizer.HasCommittedFixation)
            {
                return;
            }

            if (debugVisualizer.LatestCommittedFixationSequence == lastExportedFixationSequence)
            {
                return;
            }

            // Phase 0 exports one row per committed fixation step instead of one row per frame.
            // This keeps the dataset aligned with the current experimental prototype and debug view.
            lastExportedFixationSequence = debugVisualizer.LatestCommittedFixationSequence;

            long frameIndex = videoPlayback != null ? videoPlayback.CurrentFrame : -1;
            Vector3 origin = eyeGazeSystem.LastValidPosition;
            bool isTracked = eyeGazeSystem.HasValidGazePose;
            Vector3 dir = sphericalMapper.CurrentDirection;
            Vector2 uv = debugVisualizer.LatestCommittedFixationUv;
            float az = sphericalMapper.CurrentAzimuthRad;
            float el = sphericalMapper.CurrentElevationRad;
            int aoiId = debugVisualizer.LatestCommittedFixationAoiId;
            float aoiConfidence = debugVisualizer.LatestCommittedFixationConfidence;
            float leftPupil = eyeGazeSystem.LastLeftPupilDiameter;
            float rightPupil = eyeGazeSystem.LastRightPupilDiameter;
            float timestampMs = debugVisualizer.LatestCommittedFixationTimestampMs - (sessionStartTime * 1000f);
            timestampMs = Mathf.Round(timestampMs / 250f) * 250f;

            string row = string.Join(",",
                Escape(participantId),
                Escape(sessionId),
                Escape(ResolveVideoId()),
                timestampMs.ToString("F3", CultureInfo.InvariantCulture),
                frameIndex.ToString(CultureInfo.InvariantCulture),
                origin.x.ToString("F6", CultureInfo.InvariantCulture),
                origin.y.ToString("F6", CultureInfo.InvariantCulture),
                origin.z.ToString("F6", CultureInfo.InvariantCulture),
                dir.x.ToString("F6", CultureInfo.InvariantCulture),
                dir.y.ToString("F6", CultureInfo.InvariantCulture),
                dir.z.ToString("F6", CultureInfo.InvariantCulture),
                az.ToString("F6", CultureInfo.InvariantCulture),
                el.ToString("F6", CultureInfo.InvariantCulture),
                uv.x.ToString("F6", CultureInfo.InvariantCulture),
                uv.y.ToString("F6", CultureInfo.InvariantCulture),
                aoiId.ToString(CultureInfo.InvariantCulture),
                aoiConfidence.ToString("F4", CultureInfo.InvariantCulture),
                FormatOptionalFloat(leftPupil),
                FormatOptionalFloat(rightPupil),
                isTracked ? "1" : "0"
            );

            rows.Add(row);

            if (logEveryNFrames && Time.frameCount % Mathf.Max(1, frameLogInterval) == 0)
            {
                Debug.Log(
                    $"[DataRecorder] fixation={lastExportedFixationSequence} | frame={frameIndex} | " +
                    $"tracked={isTracked} | origin=({origin.x:F3}, {origin.y:F3}, {origin.z:F3}) | " +
                    $"uv=({uv.x:F3}, {uv.y:F3}) | aoi={aoiId} | conf={aoiConfidence:F2}"
                );
            }
        }

        private void OnDisable()
        {
            if (autoExportOnDisable && rows.Count > 1 && !hasExportedCurrentRows)
            {
                ExportCsv();
            }
        }

        public void StartRecording()
        {
            ResolveReferences();
            sessionStartTime = Time.time;
            isRecording = true;
            lastExportedFixationSequence = 0;
            hasExportedCurrentRows = false;
            LastExportPath = string.Empty;

            if (logRecordingState)
            {
                Debug.Log("[DataRecorder] Recording started.");
            }
        }

        public void StopRecording()
        {
            isRecording = false;

            if (logRecordingState)
            {
                Debug.Log("[DataRecorder] Recording stopped.");
            }
        }

        public void ExportCsv(bool allowHeaderOnly = false)
        {
            if (rows.Count == 0)
            {
                rows.Add(BuildHeader());
            }

            if (!allowHeaderOnly && rows.Count <= 1)
            {
                return;
            }

            if (hasExportedCurrentRows)
            {
                return;
            }

            // Prefer the repository export folder so Unity runtime logs land
            // next to the Python pipeline artefacts and analytics can consume
            // them without a manual copy step. Packaged builds still fall back
            // to persistentDataPath when the repo root cannot be resolved.
            string folderPath = ResolveExportFolderPath();
            Directory.CreateDirectory(folderPath);

            string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            string fileName = $"{Path.GetFileNameWithoutExtension(outputFileName)}_{timestamp}.csv";
            string filePath = Path.Combine(folderPath, fileName);

            // Export once per session shutdown so the runtime flow can stop safely
            // without duplicating rows on repeated disable/destroy paths.
            File.WriteAllText(filePath, BuildCsvContent(), Encoding.UTF8);
            LastExportPath = filePath;
            hasExportedCurrentRows = true;
            Debug.Log($"[DataRecorder] CSV exported to: {filePath}");
        }

        private static string ResolveExportFolderPath()
        {
            if (ExperimentStimulusCatalog.TryResolveRepositoryRoot(out string repositoryRoot))
            {
                return Path.Combine(repositoryRoot, "data", "exports", "csv");
            }

            return Path.Combine(Application.persistentDataPath, "Exports");
        }

        private void TryStartRecording()
        {
            ResolveReferences();

            if (isRecording)
            {
                return;
            }

            if (sphericalMapper == null || aoiLookup == null)
            {
                if (logRecordingState)
                {
                    Debug.LogWarning("[DataRecorder] Missing references. Recording not started.");
                }
                return;
            }

            if (debugVisualizer == null)
            {
                debugVisualizer = FindFirstObjectByType<EyeGazeDebugVisualizer>();
            }

            if (waitUntilVideoPrepared && videoPlayback != null && !videoPlayback.IsPrepared)
            {
                return;
            }

            if (ExperimentSessionState.IsPlaybackStartLocked)
            {
                return;
            }

            StartRecording();
        }

        private void ResolveReferences()
        {
            if (videoPlayback == null)
            {
                videoPlayback = FindFirstObjectByType<VideoPlayback>();
            }

            if (sphericalMapper == null)
            {
                sphericalMapper = FindFirstObjectByType<SphericalMapper>();
            }

            if (aoiLookup == null)
            {
                aoiLookup = FindFirstObjectByType<AOILookup>();
            }

            if (eyeGazeSystem == null)
            {
                eyeGazeSystem = FindFirstObjectByType<EyeGazeSystem>();
            }

            if (debugVisualizer == null)
            {
                debugVisualizer = FindFirstObjectByType<EyeGazeDebugVisualizer>();
            }
        }

        private string BuildHeader()
        {
            return "participant_id,session_id,video_id,timestamp_ms,frame_index,origin_x,origin_y,origin_z,direction_x,direction_y,direction_z,azimuth_rad,elevation_rad,uv_x,uv_y,aoi_id,aoi_confidence,left_pupil_diameter,right_pupil_diameter,is_valid";
        }

        private string BuildCsvContent()
        {
            StringBuilder sb = new();

            for (int i = 0; i < rows.Count; i++)
            {
                sb.AppendLine(rows[i]);
            }

            return sb.ToString();
        }

        private string ResolveVideoId()
        {
            if (videoPlayback != null && !string.IsNullOrWhiteSpace(videoPlayback.VideoStem))
            {
                return videoPlayback.VideoStem;
            }

            return videoId;
        }

        private string Escape(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "";
            }

            if (value.Contains(",") || value.Contains("\"") || value.Contains("\n"))
            {
                return $"\"{value.Replace("\"", "\"\"")}\"";
            }

            return value;
        }

        private string FormatOptionalFloat(float value)
        {
            return value >= 0f
                ? value.ToString("F4", CultureInfo.InvariantCulture)
                : "";
        }
    }
}
