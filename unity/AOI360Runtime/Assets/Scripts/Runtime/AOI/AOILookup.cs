using System;
using System.Collections.Generic;
using System.IO;
using AOI360.Runtime.Mapping;
using UnityEngine;

namespace AOI360.Runtime.AOI
{
    public class AOILookup : MonoBehaviour
    {
        private enum AoiEncodingMode
        {
            MetadataExactColor = 0,
            Grayscale8Bit = 1,
            LegacyDominantRgb = 2
        }

        [Serializable]
        private class AoiMetadataDocument
        {
            public string video;
            public int fps;
            public int[] idMapResolution;
            public AoiMetadataEntry[] aois;
        }

        [Serializable]
        private class AoiMetadataEntry
        {
            public int id;
            public string name;
            public string prompt;
            public string category;
            public int parentId;
            public string color;
        }

        public readonly struct AoiDefinition
        {
            public AoiDefinition(int id, string name, string category, Color32 color)
            {
                Id = id;
                Name = name;
                Category = category;
                Color = color;
            }

            public int Id { get; }
            public string Name { get; }
            public string Category { get; }
            public Color32 Color { get; }
        }

        [Header("References")]
        [SerializeField] private SphericalMapper sphericalMapper;
        [SerializeField] private Texture2D aoiMapTexture;
        [SerializeField] private TextAsset aoiMetadataJson;

        [Header("Encoding")]
        [SerializeField] private AoiEncodingMode encodingMode = AoiEncodingMode.MetadataExactColor;
        [SerializeField] private bool autoLoadMetadataFromStreamingAssets = true;
        [SerializeField] private string metadataStreamingFolder = "AOIMaps";
        [SerializeField] private bool autoLoadMetadataFromResources = true;
        [SerializeField] private string metadataResourcesFolder = "AOIMaps";
        [SerializeField] private float grayscaleTolerance = 0.01f;

        [Header("Confidence")]
        [SerializeField] private float neighborhoodRadiusDegrees = 1.5f;
        [SerializeField] private int neighborhoodSamples = 8;
        [SerializeField] private bool throttleConfidenceUpdates = true;
        [SerializeField] private float confidenceUpdateIntervalSeconds = 0.05f;

        [Header("Debug")]
        [SerializeField] private bool logAOIChanges = true;
        [SerializeField] private bool logContinuous = false;
        [SerializeField] private int logEveryNFrames = 30;

        public int CurrentAOIId { get; private set; }
        public float CurrentAOIConfidence { get; private set; }
        public Color CurrentAOIColor { get; private set; } = Color.clear;
        public Vector2 CurrentUV { get; private set; }
        public string CurrentAOIName { get; private set; } = "";
        public string CurrentAOICategory { get; private set; } = "";
        public IReadOnlyList<int> NeighborAOIIds => neighborAOIIds;
        public Texture2D AOIMapTexture => aoiMapTexture;
        public bool HasMetadataDefinitions => colorToDefinition.Count > 0;
        public string ActiveEncodingLabel => encodingMode.ToString();
        public string LoadedMetadataSource { get; private set; } = "";
        public string CurrentTextureName => aoiMapTexture != null ? aoiMapTexture.name : "";

        private int lastLoggedAOIId = -1;
        private bool hasWarnedTextureNotReadable;
        private bool hasWarnedMetadataMissing;
        private bool metadataLoaded;
        private string runtimeMetadataJsonText;
        private string runtimeMetadataSource = "";
        private Texture2D cachedPixelSourceTexture;
        private Color32[] cachedPixels = Array.Empty<Color32>();
        private int cachedTextureWidth;
        private int cachedTextureHeight;
        private readonly List<int> neighborAOIIds = new();
        private readonly HashSet<int> neighborAOISet = new();
        private readonly Dictionary<uint, AoiDefinition> colorToDefinition = new();
        private readonly Dictionary<int, AoiDefinition> idToDefinition = new();
        private int lastConfidenceAoiId = int.MinValue;
        private float nextConfidenceUpdateTime;

        private void Awake()
        {
            NormalizeConfigurationDefaults();
            EnsureMetadataLoaded();
            ValidateTextureSettings();
        }

        private void OnValidate()
        {
            NormalizeConfigurationDefaults();
            metadataLoaded = false;
            colorToDefinition.Clear();
            idToDefinition.Clear();
            hasWarnedMetadataMissing = false;
            LoadedMetadataSource = "";
        }

        private void Update()
        {
            if (sphericalMapper == null || aoiMapTexture == null)
            {
                return;
            }

            if (!EnsureTextureReadable())
            {
                return;
            }

            EnsurePixelCache();

            EnsureMetadataLoaded();

            Vector2 uv = sphericalMapper.CurrentUV;
            CurrentUV = uv;

            int pixelX = Mathf.Clamp(Mathf.FloorToInt(uv.x * cachedTextureWidth), 0, cachedTextureWidth - 1);
            int pixelY = Mathf.Clamp(Mathf.FloorToInt(uv.y * cachedTextureHeight), 0, cachedTextureHeight - 1);

            Color32 pixel = GetCachedPixel(pixelX, pixelY);
            CurrentAOIColor = pixel;

            int aoiId = ResolveAOIIdFromColor(pixel);
            CurrentAOIId = aoiId;
            RefreshConfidenceIfNeeded(uv, aoiId);

            if (TryGetDefinition(aoiId, out AoiDefinition definition))
            {
                CurrentAOIName = definition.Name ?? "";
                CurrentAOICategory = definition.Category ?? "";
            }
            else
            {
                CurrentAOIName = "";
                CurrentAOICategory = "";
            }

            if (Application.isEditor && logAOIChanges && CurrentAOIId != lastLoggedAOIId)
            {
                string metadataSuffix = string.IsNullOrWhiteSpace(CurrentAOIName)
                    ? ""
                    : $" | name={CurrentAOIName} | category={CurrentAOICategory}";

                Debug.Log(
                    $"[AOILookup] AOI changed -> id={CurrentAOIId} | conf={CurrentAOIConfidence:F2} " +
                    $"| uv=({uv.x:F3}, {uv.y:F3}) | px=({pixelX}, {pixelY}){metadataSuffix}"
                );
                lastLoggedAOIId = CurrentAOIId;
            }

            if (Application.isEditor && logContinuous && Time.frameCount % Mathf.Max(1, logEveryNFrames) == 0)
            {
                Debug.Log(
                    $"[AOILookup] id={CurrentAOIId} | conf={CurrentAOIConfidence:F2} " +
                    $"| uv=({uv.x:F3}, {uv.y:F3}) | px=({pixelX}, {pixelY}) | mode={encodingMode}"
                );
            }
        }

        public bool TryResolveAOIFromPixel(Color pixel, out int aoiId, out Color overlayColor)
        {
            aoiId = ResolveAOIIdFromColor(pixel);
            overlayColor = ResolveOverlayColor(pixel, aoiId);
            return aoiId > 0;
        }

        public Color ResolveOverlayColor(Color pixel, int aoiId)
        {
            if (aoiId <= 0)
            {
                return new Color(0f, 0f, 0f, 0f);
            }

            if (TryGetDefinition(aoiId, out AoiDefinition definition))
            {
                return definition.Color;
            }

            if (LooksGrayscale(pixel))
            {
                float hue = Mathf.Repeat(aoiId * 0.173f, 1f);
                return Color.HSVToRGB(hue, 0.8f, 1f);
            }

            return new Color(pixel.r, pixel.g, pixel.b, 1f);
        }

        public bool TryGetDefinition(int aoiId, out AoiDefinition definition)
        {
            return idToDefinition.TryGetValue(aoiId, out definition);
        }

        public void SetRuntimeAoiTexture(Texture2D runtimeTexture, bool forceRefresh = false)
        {
            if (aoiMapTexture == runtimeTexture && !forceRefresh)
            {
                return;
            }

            aoiMapTexture = runtimeTexture;
            hasWarnedTextureNotReadable = false;
            lastLoggedAOIId = -1;
            lastConfidenceAoiId = int.MinValue;
            nextConfidenceUpdateTime = 0f;
            InvalidatePixelCache();
            ValidateTextureSettings();
        }

        public void SetRuntimeMetadataJson(string metadataJsonText, string metadataSource = "")
        {
            runtimeMetadataJsonText = metadataJsonText;
            runtimeMetadataSource = metadataSource ?? "";
            metadataLoaded = false;
            hasWarnedMetadataMissing = false;
            colorToDefinition.Clear();
            idToDefinition.Clear();
            LoadedMetadataSource = "";
            lastLoggedAOIId = -1;
            lastConfidenceAoiId = int.MinValue;
            nextConfidenceUpdateTime = 0f;
        }

        public void SetRuntimeAoiData(Texture2D runtimeTexture, string metadataJsonText, string metadataSource = "")
        {
            SetRuntimeAoiTexture(runtimeTexture, forceRefresh: true);
            SetRuntimeMetadataJson(metadataJsonText, metadataSource);
        }

        private int ResolveAOIIdFromColor(Color pixel)
        {
            return ResolveAOIIdFromColor((Color32)pixel);
        }

        private int ResolveAOIIdFromColor(Color32 pixel32)
        {
            switch (encodingMode)
            {
                case AoiEncodingMode.MetadataExactColor:
                    EnsureMetadataLoaded();

                    // Production path: resolve AOIs by exact color through metadata so
                    // offline-generated instance maps can be consumed deterministically.
                    if (colorToDefinition.TryGetValue(ColorToKey(pixel32), out AoiDefinition definition))
                    {
                        return definition.Id;
                    }

                    if (!hasWarnedMetadataMissing && colorToDefinition.Count == 0)
                    {
                        Debug.LogWarning(
                            "[AOILookup] MetadataExactColor is active but no AOI metadata is loaded. " +
                            "The lookup will return 0 until a valid JSON is available."
                        );
                        hasWarnedMetadataMissing = true;
                    }

                    return 0;

                case AoiEncodingMode.Grayscale8Bit:
                    if (LooksGrayscale(pixel32))
                    {
                        return Mathf.Clamp(Mathf.RoundToInt((pixel32.r / 255f) * 255f), 0, 255);
                    }

                    return 0;

                case AoiEncodingMode.LegacyDominantRgb:
                    return ResolveLegacyDominantRgb(pixel32);

                default:
                    return 0;
            }
        }

        private int ResolveLegacyDominantRgb(Color32 pixel)
        {
            float r = pixel.r / 255f;
            float g = pixel.g / 255f;
            float b = pixel.b / 255f;

            if (r < 0.1f && g < 0.1f && b < 0.1f)
            {
                return 0;
            }

            if (r > 0.9f && g < 0.1f && b < 0.1f)
            {
                return 1;
            }

            if (r < 0.1f && g > 0.9f && b < 0.1f)
            {
                return 2;
            }

            if (r > g && r > b)
            {
                return 1;
            }

            if (g > r && g > b)
            {
                return 2;
            }

            return 0;
        }

        private float ComputeNeighborhoodConfidence(Vector2 uv, int centerAoiId)
        {
            neighborAOIIds.Clear();
            neighborAOISet.Clear();

            if (centerAoiId <= 0 || neighborhoodSamples <= 0)
            {
                return 0f;
            }

            float angularRadiusRad = neighborhoodRadiusDegrees * Mathf.Deg2Rad;
            float deltaU = angularRadiusRad / (2f * Mathf.PI);
            float deltaV = angularRadiusRad / Mathf.PI;

            int total = neighborhoodSamples + 1;
            int matches = 0;

            for (int sampleIndex = 0; sampleIndex < total; sampleIndex++)
            {
                Vector2 sampleUv;

                if (sampleIndex == 0)
                {
                    sampleUv = uv;
                }
                else
                {
                    float t = (sampleIndex - 1) / (float)neighborhoodSamples;
                    float angle = t * Mathf.PI * 2f;
                    float offsetU = Mathf.Cos(angle) * deltaU;
                    float offsetV = Mathf.Sin(angle) * deltaV;
                    sampleUv = new Vector2(Mathf.Repeat(uv.x + offsetU, 1f), Mathf.Clamp01(uv.y + offsetV));
                }

                int sampleX = Mathf.Clamp(Mathf.FloorToInt(sampleUv.x * cachedTextureWidth), 0, cachedTextureWidth - 1);
                int sampleY = Mathf.Clamp(Mathf.FloorToInt(sampleUv.y * cachedTextureHeight), 0, cachedTextureHeight - 1);
                int sampleAoiId = ResolveAOIIdFromColor(GetCachedPixel(sampleX, sampleY));

                if (sampleAoiId == centerAoiId)
                {
                    matches++;
                }
                else if (sampleAoiId > 0 && neighborAOISet.Add(sampleAoiId))
                {
                    neighborAOIIds.Add(sampleAoiId);
                }
            }

            return matches / (float)total;
        }

        private void RefreshConfidenceIfNeeded(Vector2 uv, int aoiId)
        {
            if (aoiId <= 0)
            {
                CurrentAOIConfidence = 0f;
                lastConfidenceAoiId = aoiId;
                nextConfidenceUpdateTime = Time.unscaledTime + Mathf.Max(0.01f, confidenceUpdateIntervalSeconds);
                neighborAOIIds.Clear();
                neighborAOISet.Clear();
                return;
            }

            bool shouldRefresh =
                !throttleConfidenceUpdates ||
                aoiId != lastConfidenceAoiId ||
                Time.unscaledTime >= nextConfidenceUpdateTime;

            if (!shouldRefresh)
            {
                return;
            }

            CurrentAOIConfidence = ComputeNeighborhoodConfidence(uv, aoiId);
            lastConfidenceAoiId = aoiId;
            nextConfidenceUpdateTime = Time.unscaledTime + Mathf.Max(0.01f, confidenceUpdateIntervalSeconds);
        }

        private void EnsureMetadataLoaded()
        {
            if (metadataLoaded)
            {
                return;
            }

            metadataLoaded = true;
            colorToDefinition.Clear();
            idToDefinition.Clear();
            LoadedMetadataSource = "";

            if (encodingMode != AoiEncodingMode.MetadataExactColor)
            {
                return;
            }

            string metadataJsonText = !string.IsNullOrWhiteSpace(runtimeMetadataJsonText)
                ? runtimeMetadataJsonText
                : aoiMetadataJson != null ? aoiMetadataJson.text : null;

            if (!string.IsNullOrWhiteSpace(runtimeMetadataJsonText))
            {
                LoadedMetadataSource = string.IsNullOrWhiteSpace(runtimeMetadataSource)
                    ? "RuntimeJson"
                    : runtimeMetadataSource;
            }

            // StreamingAssets is the main handoff point from the future Python pipeline because
            // it lets the experiment consume exported AOI metadata without hard-wiring editor assets.
            if (string.IsNullOrWhiteSpace(metadataJsonText) && autoLoadMetadataFromStreamingAssets && aoiMapTexture != null)
            {
                string streamingPath = BuildMetadataStreamingPath();
                if (!string.IsNullOrWhiteSpace(streamingPath) && File.Exists(streamingPath))
                {
                    metadataJsonText = File.ReadAllText(streamingPath);
                    LoadedMetadataSource = streamingPath;
                }
            }

            if (string.IsNullOrWhiteSpace(metadataJsonText) && aoiMetadataJson == null && autoLoadMetadataFromResources && aoiMapTexture != null)
            {
                string resourcePath = BuildMetadataResourcePath();
                if (!string.IsNullOrEmpty(resourcePath))
                {
                    aoiMetadataJson = Resources.Load<TextAsset>(resourcePath);
                }
            }

            if (string.IsNullOrWhiteSpace(metadataJsonText) && aoiMetadataJson != null)
            {
                metadataJsonText = aoiMetadataJson.text;
                LoadedMetadataSource = $"TextAsset:{aoiMetadataJson.name}";
            }

            if (string.IsNullOrWhiteSpace(metadataJsonText))
            {
                return;
            }

            AoiMetadataDocument document;
            try
            {
                document = JsonUtility.FromJson<AoiMetadataDocument>(metadataJsonText);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"[AOILookup] Could not parse AOI metadata JSON: {exception.Message}");
                return;
            }

            if (document == null || document.aois == null)
            {
                return;
            }

            foreach (AoiMetadataEntry entry in document.aois)
            {
                if (entry == null || entry.id <= 0 || string.IsNullOrWhiteSpace(entry.color))
                {
                    continue;
                }

                if (!ColorUtility.TryParseHtmlString(entry.color, out Color parsedColor))
                {
                    Debug.LogWarning($"[AOILookup] Invalid metadata color for AOI id={entry.id}: {entry.color}");
                    continue;
                }

                Color32 color32 = (Color32)parsedColor;
                AoiDefinition definition = new(entry.id, entry.name, entry.category, color32);
                colorToDefinition[ColorToKey(color32)] = definition;
                idToDefinition[definition.Id] = definition;
            }
        }

        private bool EnsureTextureReadable()
        {
            if (aoiMapTexture != null && aoiMapTexture.isReadable)
            {
                return true;
            }

            if (!hasWarnedTextureNotReadable && aoiMapTexture != null)
            {
                Debug.LogWarning(
                    $"[AOILookup] AOI texture '{aoiMapTexture.name}' is not readable from script. " +
                    "Enable Read/Write, disable Mip Maps, use Filter Mode Point, and disable compression for AOI data maps."
                );
                hasWarnedTextureNotReadable = true;
            }

            return false;
        }

        private void EnsurePixelCache()
        {
            if (aoiMapTexture == null || !aoiMapTexture.isReadable)
            {
                return;
            }

            if (cachedPixelSourceTexture == aoiMapTexture &&
                cachedPixels.Length == aoiMapTexture.width * aoiMapTexture.height)
            {
                return;
            }

            cachedPixels = aoiMapTexture.GetPixels32();
            cachedTextureWidth = aoiMapTexture.width;
            cachedTextureHeight = aoiMapTexture.height;
            cachedPixelSourceTexture = aoiMapTexture;
        }

        private void InvalidatePixelCache()
        {
            cachedPixelSourceTexture = null;
            cachedPixels = Array.Empty<Color32>();
            cachedTextureWidth = 0;
            cachedTextureHeight = 0;
        }

        private Color32 GetCachedPixel(int x, int y)
        {
            int index = y * cachedTextureWidth + x;
            if (index < 0 || index >= cachedPixels.Length)
            {
                return new Color32(0, 0, 0, 255);
            }

            return cachedPixels[index];
        }

        private void ValidateTextureSettings()
        {
            if (aoiMapTexture == null)
            {
                return;
            }

            // AOI maps are data textures, not regular art assets. These warnings are here because
            // filtering, mipmaps, or compression can silently corrupt exact-color AOI lookup.
            if (!aoiMapTexture.isReadable)
            {
                Debug.LogWarning(
                    $"[AOILookup] '{aoiMapTexture.name}' is not readable. " +
                    "AOI lookup and overlay will not work until the import settings are fixed."
                );
            }

            if (aoiMapTexture.filterMode != FilterMode.Point)
            {
                Debug.LogWarning(
                    $"[AOILookup] '{aoiMapTexture.name}' uses FilterMode {aoiMapTexture.filterMode}. " +
                    "Point is recommended for AOI data maps so IDs stay exact."
                );
            }

            if (aoiMapTexture.mipmapCount > 1)
            {
                Debug.LogWarning(
                    $"[AOILookup] '{aoiMapTexture.name}' has mipmaps enabled. " +
                    "Disable them for AOI data maps to avoid ID bleeding."
                );
            }
        }

        private void NormalizeConfigurationDefaults()
        {
            if (string.IsNullOrWhiteSpace(metadataStreamingFolder))
            {
                metadataStreamingFolder = "AOIMaps";
            }

            if (string.IsNullOrWhiteSpace(metadataResourcesFolder))
            {
                metadataResourcesFolder = "AOIMaps";
            }

            if (aoiMetadataJson == null && !autoLoadMetadataFromStreamingAssets && !autoLoadMetadataFromResources)
            {
                autoLoadMetadataFromStreamingAssets = true;
            }

            grayscaleTolerance = Mathf.Clamp(grayscaleTolerance, 0.0001f, 0.05f);
            neighborhoodSamples = Mathf.Max(0, neighborhoodSamples);
            neighborhoodRadiusDegrees = Mathf.Max(0.1f, neighborhoodRadiusDegrees);
            confidenceUpdateIntervalSeconds = Mathf.Max(0.01f, confidenceUpdateIntervalSeconds);
        }

        private string BuildMetadataResourcePath()
        {
            if (string.IsNullOrWhiteSpace(metadataResourcesFolder) || aoiMapTexture == null)
            {
                return null;
            }

            return $"{metadataResourcesFolder.TrimEnd('/')}/{aoiMapTexture.name}_metadata";
        }

        private string BuildMetadataStreamingPath()
        {
            if (string.IsNullOrWhiteSpace(metadataStreamingFolder) || aoiMapTexture == null)
            {
                return null;
            }

            return Path.Combine(
                Application.streamingAssetsPath,
                metadataStreamingFolder,
                $"{aoiMapTexture.name}_metadata.json"
            );
        }

        private bool LooksGrayscale(Color pixel)
        {
            return Mathf.Abs(pixel.r - pixel.g) < grayscaleTolerance &&
                   Mathf.Abs(pixel.g - pixel.b) < grayscaleTolerance;
        }

        private bool LooksGrayscale(Color32 pixel)
        {
            return Mathf.Abs(pixel.r - pixel.g) <= grayscaleTolerance * 255f &&
                   Mathf.Abs(pixel.g - pixel.b) <= grayscaleTolerance * 255f;
        }

        private bool IsBlack(Color32 pixel)
        {
            return pixel.r == 0 && pixel.g == 0 && pixel.b == 0;
        }

        private uint ColorToKey(Color32 color)
        {
            return (uint)(color.r | (color.g << 8) | (color.b << 16) | (color.a << 24));
        }
    }
}
