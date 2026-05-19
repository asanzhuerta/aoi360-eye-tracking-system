using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AOI360.Runtime.Experiment
{
    public static class ExperimentStimulusCatalog
    {
        private const string ManifestSuffix = "_aoi_sequence_manifest.json";

        public static List<ExperimentStimulusDefinition> DiscoverAvailableStimuli()
        {
            Dictionary<string, ExperimentStimulusDefinition> stimuliByKey =
                new Dictionary<string, ExperimentStimulusDefinition>(StringComparer.OrdinalIgnoreCase);

            AddRepositoryStimuli(stimuliByKey);
            AddStreamingAssetStimuli(stimuliByKey);

            List<ExperimentStimulusDefinition> stimuli =
                new List<ExperimentStimulusDefinition>(stimuliByKey.Values);

            stimuli.Sort(delegate (ExperimentStimulusDefinition left, ExperimentStimulusDefinition right)
            {
                return string.Compare(left.DisplayName, right.DisplayName, StringComparison.OrdinalIgnoreCase);
            });

            return stimuli;
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
