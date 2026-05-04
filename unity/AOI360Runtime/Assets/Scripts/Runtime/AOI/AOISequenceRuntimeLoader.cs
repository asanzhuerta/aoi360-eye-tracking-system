using System;
using System.Collections.Generic;
using System.IO;
using AOI360.Runtime.Video;
using AOI360.Runtime.Mapping;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AOI360.Runtime.AOI
{
    [DefaultExecutionOrder(-180)]
    public class AOISequenceRuntimeLoader : MonoBehaviour
    {
        private const string TargetSceneName = "Phase0_360Playback_VR";
        private const string RuntimeLoaderName = "AOISequenceRuntimeLoader_Runtime";

        [Serializable]
        private class SequenceManifestDocument
        {
            public string video;
            public int fps;
            public int[] idMapResolution;
            public string mapsDirectory;
            public string keyframesDirectory;
            public float bakedYawOffsetDegrees;
            public RuntimePackDocument runtimePack;
            public AoiDefinitionDocument[] aois;
            public FrameEntryDocument[] frames;
        }

        [Serializable]
        private class AoiDefinitionDocument
        {
            public int id;
            public string name;
            public string prompt;
            public string category;
            public int parentId;
            public string color;
            public int firstFrameIndex;
            public int lastFrameIndex;
            public int keyframeCount;
        }

        [Serializable]
        private class RuntimePackDocument
        {
            public string file;
            public string encoding;
            public int frameWidth;
            public int frameHeight;
            public int bytesPerPixel;
            public int frameByteLength;
        }

        [Serializable]
        private class FrameEntryDocument
        {
            public int frameIndex;
            public string frameFile;
            public string mapFile;
            public string keyframeFile;
            public int aoiCount;
            public int packOffset;
            public int packLength;
            public bool skipped;
        }

        [Serializable]
        private class KeyframeDocument
        {
            public string video;
            public int frameIndex;
            public string frameFile;
            public string mapFile;
            public KeyframeAoiEntry[] aois;
        }

        [Serializable]
        private class KeyframeAoiEntry
        {
            public int id;
            public int[] bbox;
            public float confidence;
            public int sourceDetectionIndex;
        }

        [Header("References")]
        [SerializeField] private VideoPlayback videoPlayback;
        [SerializeField] private AOILookup aoiLookup;
        [SerializeField] private SphericalMapper sphericalMapper;

        [Header("StreamingAssets")]
        [SerializeField] private bool autoLoadFromStreamingAssets = true;
        [SerializeField] private string sequenceRootFolder = "AOIMaps/Sequences";
        [SerializeField] private string legacySequenceRootFolder = "AOIMaps";
        [SerializeField] private string sequenceFolderName = "";
        [SerializeField] private string manifestFileName = "";

        [Header("Frame Selection")]
        [SerializeField] private bool clampToNearestPreviousKeyframe = true;
        [SerializeField] private bool preloadNextKeyframe = true;
        [SerializeField] private bool resetSphericalYawWhenManifestHasBakedOffset = true;

        [Header("Debug")]
        [SerializeField] private bool logSequenceEvents = true;

        public bool IsSequenceLoaded => manifestDocument != null && frameEntries.Count > 0;
        public int CurrentKeyframeFrameIndex { get; private set; } = -1;
        public string CurrentMapFile { get; private set; } = "";
        public string CurrentKeyframeFile { get; private set; } = "";
        public int CurrentKeyframeAoiCount { get; private set; }
        public int GlobalAoiCount => manifestDocument != null && manifestDocument.aois != null ? manifestDocument.aois.Length : 0;
        public string ActiveSequenceFolder => resolvedSequenceFolder;

        private SequenceManifestDocument manifestDocument;
        private readonly List<FrameEntryDocument> frameEntries = new();
        private string manifestJsonText;
        private string manifestPath = "";
        private string resolvedSequenceBasePath = "";
        private string resolvedMapsPath = "";
        private string resolvedKeyframesPath = "";
        private string resolvedSequenceFolder = "";
        private string resolvedManifestFileName = "";
        private string resolvedRuntimePackPath = "";
        private bool metadataInjectedIntoLookup;
        private Texture2D runtimeAoiTexture;
        private Texture2D preloadedAoiTexture;
        private byte[] runtimeFrameBuffer = Array.Empty<byte>();
        private byte[] preloadedPackBytes;
        private FrameEntryDocument currentFrameEntry;
        private KeyframeDocument currentKeyframe;
        private FrameEntryDocument preloadedFrameEntry;
        private KeyframeDocument preloadedKeyframe;
        private long lastObservedVideoFrame = -1;
        private Coroutine preloadCoroutine;
        private FileStream runtimePackStream;
        private readonly Dictionary<int, int> frameIndexToSequenceIndex = new();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void EnsureLoader()
        {
            Scene activeScene = SceneManager.GetActiveScene();
            if (activeScene.name != TargetSceneName)
            {
                return;
            }

            if (FindFirstObjectByType<AOISequenceRuntimeLoader>() != null)
            {
                return;
            }

            GameObject loaderObject = new GameObject(RuntimeLoaderName);
            loaderObject.AddComponent<AOISequenceRuntimeLoader>();
        }

        private void Awake()
        {
            if (SceneManager.GetActiveScene().name != TargetSceneName)
            {
                enabled = false;
                return;
            }

            ResolveReferences();
            TryLoadManifest();
        }

        private void Update()
        {
            ResolveReferences();

            if (!autoLoadFromStreamingAssets || videoPlayback == null || aoiLookup == null || !IsSequenceLoaded)
            {
                return;
            }

            TryInjectMetadataIntoLookup();

            long currentVideoFrame = videoPlayback.CurrentFrame;
            if (currentVideoFrame < 0)
            {
                return;
            }

            if (lastObservedVideoFrame >= 0 && currentVideoFrame < lastObservedVideoFrame)
            {
                HandleVideoLoopOrSeek(currentVideoFrame);
            }

            lastObservedVideoFrame = currentVideoFrame;

            FrameEntryDocument targetEntry = FindFrameEntryForVideoFrame((int)currentVideoFrame);
            if (targetEntry == null || targetEntry == currentFrameEntry)
            {
                return;
            }

            LoadFrameEntry(targetEntry);
        }

        private void OnDestroy()
        {
            if (runtimeAoiTexture != null)
            {
                Destroy(runtimeAoiTexture);
                runtimeAoiTexture = null;
            }

            if (preloadedAoiTexture != null)
            {
                Destroy(preloadedAoiTexture);
                preloadedAoiTexture = null;
            }

            CloseRuntimePackStream();
        }

        private void ResolveReferences()
        {
            if (videoPlayback == null)
            {
                videoPlayback = FindFirstObjectByType<VideoPlayback>();
            }

            if (aoiLookup == null)
            {
                aoiLookup = FindFirstObjectByType<AOILookup>();
            }

            if (sphericalMapper == null)
            {
                sphericalMapper = FindFirstObjectByType<SphericalMapper>();
            }
        }

        private void TryInjectMetadataIntoLookup()
        {
            if (metadataInjectedIntoLookup || aoiLookup == null || string.IsNullOrWhiteSpace(manifestJsonText))
            {
                return;
            }

            aoiLookup.SetRuntimeMetadataJson(manifestJsonText, manifestPath);
            metadataInjectedIntoLookup = true;
        }

        private void TryLoadManifest()
        {
            if (!autoLoadFromStreamingAssets || videoPlayback == null)
            {
                return;
            }

            resolvedSequenceFolder = ResolveSequenceFolderName();
            resolvedManifestFileName = ResolveManifestFileName();
            if (!TryResolveManifestPath(out manifestPath, out resolvedSequenceBasePath))
            {
                if (Application.isEditor && logSequenceEvents)
                {
                    Debug.Log(
                        $"[AOISequenceRuntimeLoader] No sequence manifest found for '{resolvedSequenceFolder}' " +
                        $"under '{sequenceRootFolder}' or '{legacySequenceRootFolder}'."
                    );
                }

                return;
            }

            try
            {
                manifestJsonText = File.ReadAllText(manifestPath);
                manifestDocument = JsonUtility.FromJson<SequenceManifestDocument>(manifestJsonText);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"[AOISequenceRuntimeLoader] Could not parse AOI sequence manifest: {exception.Message}");
                manifestDocument = null;
                frameEntries.Clear();
                return;
            }

            if (manifestDocument == null || manifestDocument.frames == null || manifestDocument.frames.Length == 0)
            {
                Debug.LogWarning("[AOISequenceRuntimeLoader] Manifest loaded but no frame entries were found.");
                manifestDocument = null;
                frameEntries.Clear();
                return;
            }

            frameEntries.Clear();
            frameEntries.AddRange(manifestDocument.frames);
            frameEntries.Sort((left, right) => left.frameIndex.CompareTo(right.frameIndex));
            frameIndexToSequenceIndex.Clear();
            for (int i = 0; i < frameEntries.Count; i++)
            {
                frameIndexToSequenceIndex[frameEntries[i].frameIndex] = i;
            }

            resolvedMapsPath = ResolveSequenceSubdirectory(manifestDocument.mapsDirectory, "maps");
            resolvedKeyframesPath = ResolveSequenceSubdirectory(manifestDocument.keyframesDirectory, "keyframes", "metadata");
            InitializeRuntimePack();
            metadataInjectedIntoLookup = false;
            TryInjectMetadataIntoLookup();
            ApplyManifestProjectionCalibration();

            if (Application.isEditor && logSequenceEvents)
            {
                Debug.Log(
                    $"[AOISequenceRuntimeLoader] Loaded manifest with {frameEntries.Count} keyframes " +
                    $"and {GlobalAoiCount} global AOIs from: {manifestPath}" +
                    $"{(HasRuntimePack() ? $" | runtime-pack={Path.GetFileName(resolvedRuntimePackPath)}" : string.Empty)}"
                );
            }
        }

        private void InitializeRuntimePack()
        {
            CloseRuntimePackStream();
            resolvedRuntimePackPath = "";

            if (manifestDocument == null ||
                manifestDocument.runtimePack == null ||
                string.IsNullOrWhiteSpace(manifestDocument.runtimePack.file))
            {
                return;
            }

            resolvedRuntimePackPath = ResolveFrameAssetPath(resolvedSequenceBasePath, manifestDocument.runtimePack.file);
            if (!File.Exists(resolvedRuntimePackPath))
            {
                resolvedRuntimePackPath = "";
                return;
            }

            runtimePackStream = new FileStream(
                resolvedRuntimePackPath,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read
            );
        }

        private void CloseRuntimePackStream()
        {
            if (runtimePackStream != null)
            {
                runtimePackStream.Dispose();
                runtimePackStream = null;
            }
        }

        private bool HasRuntimePack()
        {
            return runtimePackStream != null &&
                   manifestDocument != null &&
                   manifestDocument.runtimePack != null &&
                   manifestDocument.runtimePack.frameWidth > 0 &&
                   manifestDocument.runtimePack.frameHeight > 0 &&
                   manifestDocument.runtimePack.frameByteLength > 0;
        }

        private void ApplyManifestProjectionCalibration()
        {
            if (!resetSphericalYawWhenManifestHasBakedOffset || sphericalMapper == null || manifestDocument == null)
            {
                return;
            }

            if (Mathf.Abs(manifestDocument.bakedYawOffsetDegrees) <= 0.0001f)
            {
                return;
            }

            sphericalMapper.SetProjectionCalibration(
                yawDegrees: 0f,
                horizontalFlip: sphericalMapper.FlipHorizontally,
                verticalFlip: sphericalMapper.FlipVertically
            );
        }

        private FrameEntryDocument FindFrameEntryForVideoFrame(int videoFrame)
        {
            if (frameEntries.Count == 0)
            {
                return null;
            }

            FrameEntryDocument bestEntry = null;
            for (int i = 0; i < frameEntries.Count; i++)
            {
                FrameEntryDocument candidate = frameEntries[i];

                if (candidate.frameIndex == videoFrame)
                {
                    return candidate;
                }

                if (candidate.frameIndex < videoFrame)
                {
                    bestEntry = candidate;
                    continue;
                }

                if (candidate.frameIndex > videoFrame)
                {
                    return clampToNearestPreviousKeyframe ? bestEntry ?? candidate : candidate;
                }
            }

            return bestEntry ?? frameEntries[frameEntries.Count - 1];
        }

        private void LoadFrameEntry(FrameEntryDocument entry)
        {
            if (entry == null || entry.skipped)
            {
                return;
            }

            if (!TryGetLoadedFrameData(entry, out Texture2D loadedTexture, out KeyframeDocument loadedKeyframe))
            {
                return;
            }

            if (runtimeAoiTexture != null && loadedTexture != runtimeAoiTexture)
            {
                Destroy(runtimeAoiTexture);
            }

            runtimeAoiTexture = loadedTexture;
            currentKeyframe = loadedKeyframe;
            TryInjectMetadataIntoLookup();
            aoiLookup.SetRuntimeAoiTexture(runtimeAoiTexture, forceRefresh: true);

            currentFrameEntry = entry;
            CurrentKeyframeFrameIndex = entry.frameIndex;
            CurrentMapFile = entry.mapFile ?? "";
            CurrentKeyframeFile = entry.keyframeFile ?? "";
            CurrentKeyframeAoiCount = currentKeyframe != null && currentKeyframe.aois != null
                ? currentKeyframe.aois.Length
                : 0;

            if (Application.isEditor && logSequenceEvents)
            {
                Debug.Log(
                    $"[AOISequenceRuntimeLoader] Loaded keyframe frame={CurrentKeyframeFrameIndex} " +
                    $"| map={CurrentMapFile} | aois={CurrentKeyframeAoiCount}"
                );
            }

            SchedulePreloadForNextEntry(entry);
        }

        private KeyframeDocument LoadKeyframeDocument(string keyframePath)
        {
            if (string.IsNullOrWhiteSpace(keyframePath) || !File.Exists(keyframePath))
            {
                return null;
            }

            try
            {
                return JsonUtility.FromJson<KeyframeDocument>(File.ReadAllText(keyframePath));
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"[AOISequenceRuntimeLoader] Could not parse keyframe JSON '{keyframePath}': {exception.Message}");
                return null;
            }
        }

        private void HandleVideoLoopOrSeek(long currentVideoFrame)
        {
            currentFrameEntry = null;
            currentKeyframe = null;
            CurrentKeyframeFrameIndex = -1;
            CurrentMapFile = "";
            CurrentKeyframeFile = "";
            CurrentKeyframeAoiCount = 0;
            ClearPreloadedFrameData();

            if (Application.isEditor && logSequenceEvents)
            {
                Debug.Log(
                    $"[AOISequenceRuntimeLoader] Video frame moved backwards ({lastObservedVideoFrame} -> {currentVideoFrame}). " +
                    "Resetting AOI sequence state so the correct keyframe can be reloaded."
                );
            }
        }

        private bool TryGetLoadedFrameData(
            FrameEntryDocument entry,
            out Texture2D loadedTexture,
            out KeyframeDocument loadedKeyframe
        )
        {
            if (HasRuntimePack() &&
                preloadedFrameEntry != null &&
                preloadedFrameEntry.frameIndex == entry.frameIndex &&
                preloadedPackBytes != null)
            {
                loadedKeyframe = preloadedKeyframe;
                loadedTexture = ApplyRawFrameDataToRuntimeTexture(entry, preloadedPackBytes);
                preloadedPackBytes = null;
                preloadedFrameEntry = null;
                preloadedKeyframe = null;
                return loadedTexture != null;
            }

            if (preloadedFrameEntry != null && preloadedFrameEntry.frameIndex == entry.frameIndex && preloadedAoiTexture != null)
            {
                loadedTexture = preloadedAoiTexture;
                loadedKeyframe = preloadedKeyframe;
                preloadedAoiTexture = null;
                preloadedFrameEntry = null;
                preloadedKeyframe = null;
                return true;
            }

            return TryLoadFrameDataImmediate(entry, out loadedTexture, out loadedKeyframe);
        }

        private bool TryLoadFrameDataImmediate(
            FrameEntryDocument entry,
            out Texture2D loadedTexture,
            out KeyframeDocument loadedKeyframe
        )
        {
            loadedTexture = null;
            loadedKeyframe = null;

            if (HasRuntimePack() && entry.packLength > 0)
            {
                if (!TryReadRawFrameBytes(entry, cloneBuffer: false, out byte[] rawBytes))
                {
                    return false;
                }

                string keyframePath = ResolveFrameAssetPath(resolvedKeyframesPath, entry.keyframeFile);
                loadedKeyframe = LoadKeyframeDocument(keyframePath);
                loadedTexture = ApplyRawFrameDataToRuntimeTexture(entry, rawBytes);
                return loadedTexture != null;
            }

            string mapPath = ResolveFrameAssetPath(resolvedMapsPath, entry.mapFile);
            if (!File.Exists(mapPath))
            {
                Debug.LogWarning($"[AOISequenceRuntimeLoader] AOI map file was not found: {mapPath}");
                return false;
            }

            byte[] imageBytes = File.ReadAllBytes(mapPath);
            Texture2D texture = new Texture2D(2, 2, TextureFormat.RGB24, false);
            texture.name = Path.GetFileNameWithoutExtension(entry.mapFile);
            texture.wrapMode = TextureWrapMode.Repeat;
            texture.filterMode = FilterMode.Point;
            if (!texture.LoadImage(imageBytes, markNonReadable: false))
            {
                Debug.LogWarning($"[AOISequenceRuntimeLoader] AOI map could not be decoded: {mapPath}");
                Destroy(texture);
                return false;
            }

            string keyframePath = ResolveFrameAssetPath(resolvedKeyframesPath, entry.keyframeFile);
            loadedKeyframe = LoadKeyframeDocument(keyframePath);
            loadedTexture = texture;
            return true;
        }

        private bool TryReadRawFrameBytes(FrameEntryDocument entry, bool cloneBuffer, out byte[] rawBytes)
        {
            rawBytes = null;
            if (!HasRuntimePack() || entry.packLength <= 0)
            {
                return false;
            }

            if (runtimeFrameBuffer.Length != entry.packLength)
            {
                runtimeFrameBuffer = new byte[entry.packLength];
            }

            runtimePackStream.Seek(entry.packOffset, SeekOrigin.Begin);
            int totalRead = 0;
            while (totalRead < entry.packLength)
            {
                int bytesRead = runtimePackStream.Read(runtimeFrameBuffer, totalRead, entry.packLength - totalRead);
                if (bytesRead <= 0)
                {
                    Debug.LogWarning(
                        $"[AOISequenceRuntimeLoader] Runtime pack ended unexpectedly while reading frame {entry.frameIndex}."
                    );
                    return false;
                }

                totalRead += bytesRead;
            }

            if (cloneBuffer)
            {
                rawBytes = new byte[entry.packLength];
                Buffer.BlockCopy(runtimeFrameBuffer, 0, rawBytes, 0, entry.packLength);
            }
            else
            {
                rawBytes = runtimeFrameBuffer;
            }

            return true;
        }

        private Texture2D ApplyRawFrameDataToRuntimeTexture(FrameEntryDocument entry, byte[] rawBytes)
        {
            if (manifestDocument == null || manifestDocument.runtimePack == null || rawBytes == null)
            {
                return null;
            }

            RuntimePackDocument runtimePack = manifestDocument.runtimePack;
            EnsureReusableRuntimeTexture(runtimePack.frameWidth, runtimePack.frameHeight);

            runtimeAoiTexture.name = !string.IsNullOrWhiteSpace(entry.mapFile)
                ? Path.GetFileNameWithoutExtension(entry.mapFile)
                : $"aoi_frame_{entry.frameIndex:000000}";
            runtimeAoiTexture.LoadRawTextureData(rawBytes);
            runtimeAoiTexture.Apply(updateMipmaps: false, makeNoLongerReadable: false);
            return runtimeAoiTexture;
        }

        private void EnsureReusableRuntimeTexture(int width, int height)
        {
            if (runtimeAoiTexture != null &&
                runtimeAoiTexture.width == width &&
                runtimeAoiTexture.height == height)
            {
                return;
            }

            if (runtimeAoiTexture != null)
            {
                Destroy(runtimeAoiTexture);
            }

            runtimeAoiTexture = new Texture2D(width, height, TextureFormat.RGB24, false);
            runtimeAoiTexture.wrapMode = TextureWrapMode.Repeat;
            runtimeAoiTexture.filterMode = FilterMode.Point;
        }

        private void SchedulePreloadForNextEntry(FrameEntryDocument entry)
        {
            if (!preloadNextKeyframe || entry == null)
            {
                return;
            }

            FrameEntryDocument nextEntry = FindNextEntry(entry);
            if (nextEntry == null || (preloadedFrameEntry != null && preloadedFrameEntry.frameIndex == nextEntry.frameIndex))
            {
                return;
            }

            if (preloadCoroutine != null)
            {
                StopCoroutine(preloadCoroutine);
            }

            preloadCoroutine = StartCoroutine(PreloadFrameEntryAfterYield(nextEntry));
        }

        private System.Collections.IEnumerator PreloadFrameEntryAfterYield(FrameEntryDocument entry)
        {
            yield return null;

            if (entry == null || currentFrameEntry == null)
            {
                preloadCoroutine = null;
                yield break;
            }

            if (preloadedFrameEntry != null && preloadedFrameEntry.frameIndex == entry.frameIndex)
            {
                preloadCoroutine = null;
                yield break;
            }

            ClearPreloadedFrameData();
            if (HasRuntimePack() && entry.packLength > 0)
            {
                string keyframePath = ResolveFrameAssetPath(resolvedKeyframesPath, entry.keyframeFile);
                preloadedKeyframe = LoadKeyframeDocument(keyframePath);
                if (TryReadRawFrameBytes(entry, cloneBuffer: true, out byte[] rawBytes))
                {
                    preloadedFrameEntry = entry;
                    preloadedPackBytes = rawBytes;
                }
            }
            else if (TryLoadFrameDataImmediate(entry, out Texture2D loadedTexture, out KeyframeDocument loadedKeyframe))
            {
                preloadedFrameEntry = entry;
                preloadedAoiTexture = loadedTexture;
                preloadedKeyframe = loadedKeyframe;
            }

            preloadCoroutine = null;
        }

        private FrameEntryDocument FindNextEntry(FrameEntryDocument entry)
        {
            if (entry == null || !frameIndexToSequenceIndex.TryGetValue(entry.frameIndex, out int sequenceIndex))
            {
                return null;
            }

            int nextIndex = sequenceIndex + 1;
            if (nextIndex < 0 || nextIndex >= frameEntries.Count)
            {
                return null;
            }

            return frameEntries[nextIndex];
        }

        private void ClearPreloadedFrameData()
        {
            if (preloadCoroutine != null)
            {
                StopCoroutine(preloadCoroutine);
                preloadCoroutine = null;
            }

            if (preloadedAoiTexture != null)
            {
                Destroy(preloadedAoiTexture);
                preloadedAoiTexture = null;
            }

            preloadedPackBytes = null;
            preloadedFrameEntry = null;
            preloadedKeyframe = null;
        }

        private bool TryResolveManifestPath(out string resolvedPath, out string resolvedBasePath)
        {
            string[] candidateRoots =
            {
                sequenceRootFolder,
                legacySequenceRootFolder
            };

            for (int i = 0; i < candidateRoots.Length; i++)
            {
                string candidateRoot = candidateRoots[i];
                if (string.IsNullOrWhiteSpace(candidateRoot))
                {
                    continue;
                }

                string candidateBasePath = Path.Combine(
                    Application.streamingAssetsPath,
                    candidateRoot,
                    resolvedSequenceFolder
                );
                string candidateManifestPath = Path.Combine(candidateBasePath, resolvedManifestFileName);

                if (!File.Exists(candidateManifestPath))
                {
                    continue;
                }

                resolvedPath = candidateManifestPath;
                resolvedBasePath = candidateBasePath;
                return true;
            }

            resolvedPath = "";
            resolvedBasePath = "";
            return false;
        }

        private string ResolveSequenceSubdirectory(string manifestDirectoryValue, params string[] preferredSubfolders)
        {
            for (int i = 0; i < preferredSubfolders.Length; i++)
            {
                string preferredSubfolder = preferredSubfolders[i];
                if (string.IsNullOrWhiteSpace(preferredSubfolder))
                {
                    continue;
                }

                string candidatePath = Path.Combine(resolvedSequenceBasePath, preferredSubfolder);
                if (Directory.Exists(candidatePath))
                {
                    return candidatePath;
                }
            }

            if (!string.IsNullOrWhiteSpace(manifestDirectoryValue))
            {
                string normalizedManifestDirectory = manifestDirectoryValue
                    .Replace('/', Path.DirectorySeparatorChar)
                    .Replace('\\', Path.DirectorySeparatorChar);
                string manifestDirectoryName = Path.GetFileName(normalizedManifestDirectory.TrimEnd(Path.DirectorySeparatorChar));

                if (!string.IsNullOrWhiteSpace(manifestDirectoryName))
                {
                    string candidatePath = Path.Combine(resolvedSequenceBasePath, manifestDirectoryName);
                    if (Directory.Exists(candidatePath))
                    {
                        return candidatePath;
                    }
                }
            }

            return resolvedSequenceBasePath;
        }

        private string ResolveFrameAssetPath(string baseDirectory, string fileName)
        {
            if (string.IsNullOrWhiteSpace(fileName))
            {
                return "";
            }

            string[] candidateDirectories =
            {
                baseDirectory,
                resolvedSequenceBasePath
            };

            for (int i = 0; i < candidateDirectories.Length; i++)
            {
                string candidateDirectory = candidateDirectories[i];
                if (string.IsNullOrWhiteSpace(candidateDirectory))
                {
                    continue;
                }

                string candidatePath = Path.Combine(candidateDirectory, fileName);
                if (File.Exists(candidatePath))
                {
                    return candidatePath;
                }
            }

            return Path.Combine(baseDirectory ?? resolvedSequenceBasePath, fileName);
        }

        private string ResolveSequenceFolderName()
        {
            if (!string.IsNullOrWhiteSpace(sequenceFolderName))
            {
                return sequenceFolderName.Trim();
            }

            if (videoPlayback != null && !string.IsNullOrWhiteSpace(videoPlayback.VideoFileName))
            {
                return Path.GetFileNameWithoutExtension(videoPlayback.VideoFileName);
            }

            return "video_360";
        }

        private string ResolveManifestFileName()
        {
            if (!string.IsNullOrWhiteSpace(manifestFileName))
            {
                return manifestFileName.Trim();
            }

            return $"{resolvedSequenceFolder}_aoi_sequence_manifest.json";
        }
    }
}
