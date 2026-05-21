using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AOI360.Runtime.Experiment
{
    public static class ExperimentStimulusCatalog
    {
        private const string ManifestSuffix = "_aoi_sequence_manifest.json";
        private static readonly string[] PreferredVideoExtensions = { ".mp4", ".mov", ".webm", ".mkv" };

        public static List<ExperimentStimulusDefinition> DiscoverAvailableStimuli(
            bool includeStreamingAssetsMirror = true
        )
        {
            Dictionary<string, ExperimentStimulusDefinition> stimuliByKey =
                new Dictionary<string, ExperimentStimulusDefinition>(StringComparer.OrdinalIgnoreCase);

            AddRepositoryStimuli(stimuliByKey);
            if (includeStreamingAssetsMirror)
            {
                AddStreamingAssetStimuli(stimuliByKey);
            }

            List<ExperimentStimulusDefinition> stimuli =
                new List<ExperimentStimulusDefinition>(stimuliByKey.Values);

            ExperimentStimulusAllowlist stimulusAllowlist =
                ExperimentRuntimeConfig.LoadStimulusAllowlist();

            if (stimulusAllowlist.FiltersStimuli)
            {
                int discoveredCount = stimuli.Count;
                stimuli = stimuli.FindAll(stimulusAllowlist.Allows);
                Debug.Log(
                    $"[ExperimentStimulusCatalog] Allowlist activa desde '{stimulusAllowlist.ConfigPath}'. " +
                    $"Videos visibles: {stimuli.Count}/{discoveredCount}."
                );
            }

            stimuli.Sort(delegate (ExperimentStimulusDefinition left, ExperimentStimulusDefinition right)
            {
                return string.Compare(left.DisplayName, right.DisplayName, StringComparison.OrdinalIgnoreCase);
            });

            return stimuli;
        }

        public static bool TryResolveRepositoryRoot(out string repositoryRoot)
        {
            return RepositoryPathResolver.TryResolveRepositoryRoot(out repositoryRoot);
        }

        private static void AddRepositoryStimuli(Dictionary<string, ExperimentStimulusDefinition> stimuliByKey)
        {
            string repositoryRoot;
            if (!TryResolveRepositoryRoot(out repositoryRoot))
            {
                Debug.LogWarning(
                    "[ExperimentStimulusCatalog] No se ha podido resolver la raiz del repo. " +
                    "En Android build esto es normal: usa StreamingAssets."
                );
                return;
            }

            string inputVideosRoot = Path.Combine(repositoryRoot, "data", "input_videos");
            string processedMetadataRoot = Path.Combine(repositoryRoot, "data", "processed", "metadata");
            string processedMapsRoot = Path.Combine(repositoryRoot, "data", "processed", "id_maps");

            if (!Directory.Exists(inputVideosRoot) ||
                !Directory.Exists(processedMetadataRoot) ||
                !Directory.Exists(processedMapsRoot))
            {
                return;
            }

            string[] manifestPaths = Directory.GetFiles(
                processedMetadataRoot,
                "*" + ManifestSuffix,
                SearchOption.TopDirectoryOnly
            );

            for (int i = 0; i < manifestPaths.Length; i++)
            {
                string manifestPath = manifestPaths[i];
                string sequenceName = Path.GetFileNameWithoutExtension(manifestPath)
                    .Replace("_aoi_sequence_manifest", string.Empty);

                string mapsDirectoryPath = Path.Combine(processedMapsRoot, sequenceName);
                if (!Directory.Exists(mapsDirectoryPath))
                {
                    continue;
                }

                string videoAbsolutePath;
                string videoFileName;
                if (!TryFindVideoForSequence(inputVideosRoot, sequenceName, out videoAbsolutePath, out videoFileName))
                {
                    continue;
                }

                ExperimentStimulusDefinition stimulus = new ExperimentStimulusDefinition(
                    Path.GetFileNameWithoutExtension(videoFileName),
                    videoFileName,
                    videoAbsolutePath,
                    sequenceName,
                    manifestPath,
                    mapsDirectoryPath,
                    ExperimentStimulusSourceKind.RepositoryData,
                    "Repo:data"
                );

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
                string manifestPath = Path.Combine(sequenceDirectory, sequenceName + ManifestSuffix);
                if (!File.Exists(manifestPath))
                {
                    continue;
                }

                string mapsDirectoryPath = Path.Combine(sequenceDirectory, "maps");
                if (!Directory.Exists(mapsDirectoryPath))
                {
                    continue;
                }

                string videoAbsolutePath;
                string videoFileName;
                if (!TryFindVideoForSequence(videosRoot, sequenceName, out videoAbsolutePath, out videoFileName))
                {
                    continue;
                }

                if (stimuliByKey.ContainsKey(sequenceName))
                {
                    continue;
                }

                ExperimentStimulusDefinition stimulus = new ExperimentStimulusDefinition(
                    Path.GetFileNameWithoutExtension(videoFileName),
                    videoFileName,
                    videoAbsolutePath,
                    sequenceName,
                    manifestPath,
                    mapsDirectoryPath,
                    ExperimentStimulusSourceKind.StreamingAssets,
                    "StreamingAssets"
                );

                stimuliByKey[sequenceName] = stimulus;
            }
        }

        private static bool TryFindVideoForSequence(
            string videosRoot,
            string sequenceName,
            out string videoAbsolutePath,
            out string videoFileName
        )
        {
            videoAbsolutePath = string.Empty;
            videoFileName = string.Empty;

            if (string.IsNullOrWhiteSpace(videosRoot) || !Directory.Exists(videosRoot))
            {
                return false;
            }

            for (int i = 0; i < PreferredVideoExtensions.Length; i++)
            {
                string preferredPath = Path.Combine(videosRoot, sequenceName + PreferredVideoExtensions[i]);
                if (!File.Exists(preferredPath))
                {
                    continue;
                }

                videoAbsolutePath = preferredPath;
                videoFileName = Path.GetFileName(preferredPath);
                return true;
            }

            string[] matches = Directory.GetFiles(videosRoot, sequenceName + ".*", SearchOption.TopDirectoryOnly);
            for (int i = 0; i < matches.Length; i++)
            {
                string candidatePath = matches[i];
                string extension = Path.GetExtension(candidatePath);
                if (!IsSupportedVideoExtension(extension))
                {
                    continue;
                }

                videoAbsolutePath = candidatePath;
                videoFileName = Path.GetFileName(candidatePath);
                return true;
            }

            return false;
        }

        private static bool IsSupportedVideoExtension(string extension)
        {
            if (string.IsNullOrWhiteSpace(extension))
            {
                return false;
            }

            string normalized = extension.ToLowerInvariant();
            return normalized == ".mp4" ||
                   normalized == ".mkv" ||
                   normalized == ".mov" ||
                   normalized == ".webm";
        }
    }
}
