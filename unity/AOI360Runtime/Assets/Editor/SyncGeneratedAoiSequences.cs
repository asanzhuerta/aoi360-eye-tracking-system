using System;
using System.IO;
using AOI360.Runtime.Experiment;
using UnityEditor;
using UnityEngine;

public static class SyncGeneratedAoiSequences
{
    private const string ManifestSuffix = "_aoi_sequence_manifest.json";

    [MenuItem("Tools/AOI/Sync All Generated Sequences To StreamingAssets")]
    public static void SyncAllGeneratedSequences()
    {
        string repoRoot = ResolveRepoRoot();
        string sourceVideosRoot = Path.Combine(repoRoot, "data", "input_videos");
        string sourceMetadataRoot = Path.Combine(repoRoot, "data", "processed", "metadata");
        string sourceMapsRoot = Path.Combine(repoRoot, "data", "processed", "id_maps");
        string streamingVideosRoot = Path.Combine(
            Application.dataPath,
            "StreamingAssets",
            "Videos"
        );
        string streamingSequencesRoot = Path.Combine(
            Application.dataPath,
            "StreamingAssets",
            "AOIMaps",
            "Sequences"
        );

        if (!Directory.Exists(sourceVideosRoot) || !Directory.Exists(sourceMetadataRoot) || !Directory.Exists(sourceMapsRoot))
        {
            Debug.LogWarning(
                "[SyncGeneratedAoiSequences] The generated Python outputs were not found. " +
                "Run the offline pipeline before syncing."
            );
            return;
        }

        string[] manifestPaths = Directory.GetFiles(sourceMetadataRoot, $"*{ManifestSuffix}", SearchOption.TopDirectoryOnly);
        if (manifestPaths.Length == 0)
        {
            Debug.LogWarning("[SyncGeneratedAoiSequences] No AOI sequence manifests were found to sync.");
            return;
        }

        Directory.CreateDirectory(streamingVideosRoot);
        int syncedCount = 0;
        for (int i = 0; i < manifestPaths.Length; i++)
        {
            string manifestPath = manifestPaths[i];
            string sequenceName = Path.GetFileNameWithoutExtension(manifestPath)
                .Replace("_aoi_sequence_manifest", string.Empty);

            string sourceMapsDirectory = Path.Combine(sourceMapsRoot, sequenceName);
            string sourceKeyframesDirectory = Path.Combine(sourceMetadataRoot, sequenceName);
            if (!Directory.Exists(sourceMapsDirectory) || !Directory.Exists(sourceKeyframesDirectory))
            {
                Debug.LogWarning(
                    $"[SyncGeneratedAoiSequences] Skipping '{sequenceName}' because maps or keyframes are missing."
                );
                continue;
            }

            string videoFileName = $"{sequenceName}.mp4";
            if (ExperimentStimulusCatalog.TryReadVideoFileNameFromManifest(manifestPath, out string manifestVideoFileName))
            {
                videoFileName = manifestVideoFileName;
            }

            string sourceVideoPath = Path.Combine(sourceVideosRoot, videoFileName);
            if (!File.Exists(sourceVideoPath))
            {
                Debug.LogWarning(
                    $"[SyncGeneratedAoiSequences] Skipping '{sequenceName}' because the source video is missing: {sourceVideoPath}"
                );
                continue;
            }

            string destinationSequenceRoot = Path.Combine(streamingSequencesRoot, sequenceName);
            string destinationMapsDirectory = Path.Combine(destinationSequenceRoot, "maps");
            string destinationKeyframesDirectory = Path.Combine(destinationSequenceRoot, "keyframes");

            PrepareDestinationDirectory(destinationMapsDirectory);
            PrepareDestinationDirectory(destinationKeyframesDirectory);
            File.Copy(
                sourceVideoPath,
                Path.Combine(streamingVideosRoot, Path.GetFileName(sourceVideoPath)),
                overwrite: true
            );

            CopyMatchingFiles(sourceMapsDirectory, destinationMapsDirectory, "*_aoi_map.png");
            CopyMatchingFiles(sourceKeyframesDirectory, destinationKeyframesDirectory, "*_aoi_keyframe.json");
            File.Copy(
                manifestPath,
                Path.Combine(destinationSequenceRoot, Path.GetFileName(manifestPath)),
                overwrite: true
            );
            CopyMatchingFiles(
                sourceMetadataRoot,
                destinationSequenceRoot,
                $"{sequenceName}_aoi_sequence_rgb24.bin"
            );

            syncedCount++;
            Debug.Log(
                $"[SyncGeneratedAoiSequences] Synced '{sequenceName}' to StreamingAssets/AOIMaps/Sequences/{sequenceName}"
            );
        }

        AssetDatabase.Refresh();
        EditorUtility.DisplayDialog(
            "AOI Sequence Sync",
            $"Synced {syncedCount} generated sequence(s) into StreamingAssets.",
            "OK"
        );
    }

    private static string ResolveRepoRoot()
    {
        DirectoryInfo currentDirectory = new DirectoryInfo(Application.dataPath);

        while (currentDirectory != null)
        {
            bool hasDataDirectory = Directory.Exists(Path.Combine(currentDirectory.FullName, "data"));
            bool hasUnityDirectory = Directory.Exists(Path.Combine(currentDirectory.FullName, "unity"));

            if (hasDataDirectory && hasUnityDirectory)
            {
                return currentDirectory.FullName;
            }

            currentDirectory = currentDirectory.Parent;
        }

        throw new InvalidOperationException(
            $"Could not resolve the repository root from Application.dataPath='{Application.dataPath}'."
        );
    }

    private static void PrepareDestinationDirectory(string destinationDirectory)
    {
        if (Directory.Exists(destinationDirectory))
        {
            Directory.Delete(destinationDirectory, recursive: true);
        }

        Directory.CreateDirectory(destinationDirectory);
    }

    private static void CopyMatchingFiles(string sourceDirectory, string destinationDirectory, string searchPattern)
    {
        string[] sourceFiles = Directory.GetFiles(sourceDirectory, searchPattern, SearchOption.TopDirectoryOnly);
        for (int i = 0; i < sourceFiles.Length; i++)
        {
            string sourceFile = sourceFiles[i];
            string destinationFile = Path.Combine(destinationDirectory, Path.GetFileName(sourceFile));
            File.Copy(sourceFile, destinationFile, overwrite: true);
        }
    }
}
