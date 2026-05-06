using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AOI360.Runtime.Experiment
{
    public enum ExperimentStimulusSourceKind
    {
        RepositoryData = 0,
        StreamingAssets = 1
    }

    [Serializable]
    public sealed class ExperimentStimulusDefinition
    {
        public ExperimentStimulusDefinition(
            string videoId,
            string videoFileName,
            string videoAbsolutePath,
            string sequenceName,
            string manifestAbsolutePath,
            string mapsDirectoryAbsolutePath,
            ExperimentStimulusSourceKind sourceKind,
            string sourceLabel
        )
        {
            VideoId = videoId ?? string.Empty;
            VideoFileName = videoFileName ?? string.Empty;
            VideoAbsolutePath = videoAbsolutePath ?? string.Empty;
            SequenceName = sequenceName ?? string.Empty;
            ManifestAbsolutePath = manifestAbsolutePath ?? string.Empty;
            MapsDirectoryAbsolutePath = mapsDirectoryAbsolutePath ?? string.Empty;
            SourceKind = sourceKind;
            SourceLabel = sourceLabel ?? string.Empty;
        }

        public string VideoId { get; }
        public string VideoFileName { get; }
        public string VideoAbsolutePath { get; }
        public string SequenceName { get; }
        public string ManifestAbsolutePath { get; }
        public string MapsDirectoryAbsolutePath { get; }
        public ExperimentStimulusSourceKind SourceKind { get; }
        public string SourceLabel { get; }

        public string DisplayName => !string.IsNullOrWhiteSpace(VideoId) ? VideoId : SequenceName;
        public bool HasExternalVideoPath => !string.IsNullOrWhiteSpace(VideoAbsolutePath);
        public bool HasManifestPath => !string.IsNullOrWhiteSpace(ManifestAbsolutePath);
        public bool HasMapsDirectory => !string.IsNullOrWhiteSpace(MapsDirectoryAbsolutePath);
    }

    public static class ExperimentStimulusCatalog
    {
        private const string ManifestSuffix = "_aoi_sequence_manifest.json";

        [Serializable]
        private sealed class ManifestVideoDocument
        {
            public string video;
        }

        public static IReadOnlyList<ExperimentStimulusDefinition> DiscoverAvailableStimuli()
        {
            Dictionary<string, ExperimentStimulusDefinition> stimuliByKey = new(StringComparer.OrdinalIgnoreCase);

            AddRepositoryStimuli(stimuliByKey);
            AddStreamingAssetStimuli(stimuliByKey);

            List<ExperimentStimulusDefinition> stimuli = new(stimuliByKey.Values);
            stimuli.Sort((left, right) => string.Compare(left.DisplayName, right.DisplayName, StringComparison.OrdinalIgnoreCase));
            return stimuli;
        }

        public static bool TryReadVideoFileNameFromManifest(string manifestPath, out string videoFileName)
        {
            videoFileName = string.Empty;
            if (string.IsNullOrWhiteSpace(manifestPath) || !File.Exists(manifestPath))
            {
                return false;
            }

            try
            {
                string manifestText = File.ReadAllText(manifestPath);
                ManifestVideoDocument document = JsonUtility.FromJson<ManifestVideoDocument>(manifestText);
                if (document == null || string.IsNullOrWhiteSpace(document.video))
                {
                    return false;
                }

                videoFileName = Path.GetFileName(document.video.Trim());
                return !string.IsNullOrWhiteSpace(videoFileName);
            }
            catch (Exception exception)
            {
                Debug.LogWarning(
                    $"[ExperimentStimulusCatalog] Could not read video name from manifest '{manifestPath}': {exception.Message}"
                );
                return false;
            }
        }

        public static bool TryResolveRepositoryRoot(out string repositoryRoot)
        {
            DirectoryInfo currentDirectory = new DirectoryInfo(Application.dataPath);

            while (currentDirectory != null)
            {
                string candidateRoot = currentDirectory.FullName;
                bool hasDataDirectory = Directory.Exists(Path.Combine(candidateRoot, "data"));
                bool hasUnityDirectory = Directory.Exists(Path.Combine(candidateRoot, "unity"));

                if (hasDataDirectory && hasUnityDirectory)
                {
                    repositoryRoot = candidateRoot;
                    return true;
                }

                currentDirectory = currentDirectory.Parent;
            }

            repositoryRoot = string.Empty;
            return false;
        }

        private static void AddRepositoryStimuli(Dictionary<string, ExperimentStimulusDefinition> stimuliByKey)
        {
            if (!TryResolveRepositoryRoot(out string repositoryRoot))
            {
                Debug.LogWarning("[ExperimentStimulusCatalog] No se ha podido resolver la raíz del repo. En Android build esto es normal: usa StreamingAssets.");
                return;
            }

            string inputVideosRoot = Path.Combine(repositoryRoot, "data", "input_videos");
            string processedMetadataRoot = Path.Combine(repositoryRoot, "data", "processed", "metadata");
            string processedMapsRoot = Path.Combine(repositoryRoot, "data", "processed", "id_maps");

            Debug.Log($"[ExperimentStimulusCatalog] Repo root: {repositoryRoot}");
            Debug.Log($"[ExperimentStimulusCatalog] inputVideosRoot: {inputVideosRoot}");
            Debug.Log($"[ExperimentStimulusCatalog] processedMetadataRoot: {processedMetadataRoot}");
            Debug.Log($"[ExperimentStimulusCatalog] processedMapsRoot: {processedMapsRoot}");

            if (!Directory.Exists(inputVideosRoot))
            {
                Debug.LogWarning($"[ExperimentStimulusCatalog] No existe data/input_videos: {inputVideosRoot}");
                return;
            }

            if (!Directory.Exists(processedMetadataRoot))
            {
                Debug.LogWarning($"[ExperimentStimulusCatalog] No existe data/processed/metadata: {processedMetadataRoot}");
                return;
            }

            if (!Directory.Exists(processedMapsRoot))
            {
                Debug.LogWarning($"[ExperimentStimulusCatalog] No existe data/processed/id_maps: {processedMapsRoot}");
                return;
            }

            string[] manifestPaths = Directory.GetFiles(processedMetadataRoot, $"*{ManifestSuffix}", SearchOption.TopDirectoryOnly);
            Debug.Log($"[ExperimentStimulusCatalog] Manifests encontrados: {manifestPaths.Length}");

            for (int i = 0; i < manifestPaths.Length; i++)
            {
                string manifestPath = manifestPaths[i];
                string sequenceName = Path.GetFileNameWithoutExtension(manifestPath)
                    .Replace("_aoi_sequence_manifest", string.Empty);

                string mapsDirectoryPath = Path.Combine(processedMapsRoot, sequenceName);
                if (!Directory.Exists(mapsDirectoryPath))
                {
                    Debug.LogWarning($"[ExperimentStimulusCatalog] Se omite '{sequenceName}': no existe carpeta de mapas: {mapsDirectoryPath}");
                    continue;
                }

                string videoFileName = ResolveVideoFileName(manifestPath, sequenceName);
                string videoAbsolutePath = Path.Combine(inputVideosRoot, videoFileName);
                if (!File.Exists(videoAbsolutePath))
                {
                    Debug.LogWarning($"[ExperimentStimulusCatalog] Se omite '{sequenceName}': no existe vídeo: {videoAbsolutePath}");
                    continue;
                }

                ExperimentStimulusDefinition stimulus = new(
                    videoId: Path.GetFileNameWithoutExtension(videoFileName),
                    videoFileName: videoFileName,
                    videoAbsolutePath: videoAbsolutePath,
                    sequenceName: sequenceName,
                    manifestAbsolutePath: manifestPath,
                    mapsDirectoryAbsolutePath: mapsDirectoryPath,
                    sourceKind: ExperimentStimulusSourceKind.RepositoryData,
                    sourceLabel: "Repo:data"
                );

                Debug.Log($"[ExperimentStimulusCatalog] Estímulo listo: {stimulus.DisplayName} | {stimulus.VideoAbsolutePath}");

                stimuliByKey[sequenceName] = stimulus;
            }
        }

        private static void AddStreamingAssetStimuli(Dictionary<string, ExperimentStimulusDefinition> stimuliByKey)
        {
            string videosRoot = Path.Combine(Application.streamingAssetsPath, "Videos");
            string sequencesRoot = Path.Combine(Application.streamingAssetsPath, "AOIMaps", "Sequences");
            if (!Directory.Exists(videosRoot) || !Directory.Exists(sequencesRoot))
            {
                return;
            }

            string[] sequenceDirectories = Directory.GetDirectories(sequencesRoot, "*", SearchOption.TopDirectoryOnly);
            for (int i = 0; i < sequenceDirectories.Length; i++)
            {
                string sequenceDirectory = sequenceDirectories[i];
                string sequenceName = Path.GetFileName(sequenceDirectory);
                string manifestPath = Path.Combine(sequenceDirectory, $"{sequenceName}{ManifestSuffix}");
                if (!File.Exists(manifestPath))
                {
                    continue;
                }

                string mapsDirectoryPath = Path.Combine(sequenceDirectory, "maps");
                if (!Directory.Exists(mapsDirectoryPath))
                {
                    continue;
                }

                string videoFileName = ResolveVideoFileName(manifestPath, sequenceName);
                string videoAbsolutePath = Path.Combine(videosRoot, videoFileName);
                if (!File.Exists(videoAbsolutePath))
                {
                    continue;
                }

                if (stimuliByKey.ContainsKey(sequenceName))
                {
                    continue;
                }

                ExperimentStimulusDefinition stimulus = new(
                    videoId: Path.GetFileNameWithoutExtension(videoFileName),
                    videoFileName: videoFileName,
                    videoAbsolutePath: videoAbsolutePath,
                    sequenceName: sequenceName,
                    manifestAbsolutePath: manifestPath,
                    mapsDirectoryAbsolutePath: mapsDirectoryPath,
                    sourceKind: ExperimentStimulusSourceKind.StreamingAssets,
                    sourceLabel: "StreamingAssets"
                );

                stimuliByKey[sequenceName] = stimulus;
            }
        }

        private static string ResolveVideoFileName(string manifestPath, string sequenceName)
        {
            if (TryReadVideoFileNameFromManifest(manifestPath, out string manifestVideoFileName))
            {
                return manifestVideoFileName;
            }

            return $"{sequenceName}.mp4";
        }
    }
}
