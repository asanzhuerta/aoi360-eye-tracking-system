using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AOI360.Runtime.Experiment
{
    internal sealed class ExperimentStimulusAllowlist
    {
        public static ExperimentStimulusAllowlist AllowAll { get; } =
            new ExperimentStimulusAllowlist(
                isEnabled: false,
                configPath: string.Empty,
                allowedVideoIds: new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            );

        private readonly HashSet<string> allowedVideoIds;

        public ExperimentStimulusAllowlist(
            bool isEnabled,
            string configPath,
            HashSet<string> allowedVideoIds
        )
        {
            IsEnabled = isEnabled;
            ConfigPath = configPath ?? string.Empty;
            this.allowedVideoIds = allowedVideoIds ??
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        }

        public bool IsEnabled { get; }
        public string ConfigPath { get; }
        public bool FiltersStimuli => IsEnabled && allowedVideoIds.Count > 0;

        public bool Allows(ExperimentStimulusDefinition stimulus)
        {
            if (!FiltersStimuli || stimulus == null)
            {
                return true;
            }

            return Contains(stimulus.VideoId) ||
                   Contains(stimulus.SequenceName) ||
                   Contains(Path.GetFileNameWithoutExtension(stimulus.VideoFileName));
        }

        private bool Contains(string candidate)
        {
            string normalized = ExperimentRuntimeConfig.NormalizeVideoId(candidate);
            return !string.IsNullOrWhiteSpace(normalized) && allowedVideoIds.Contains(normalized);
        }
    }

    public static class ExperimentRuntimeConfig
    {
        private static readonly string RuntimeConfigRelativePath =
            Path.Combine("data", "experiment", "runtime_config.json");

        [Serializable]
        private sealed class RuntimeConfigPayload
        {
            public bool stimulusAllowlistEnabled;
            public string[] allowedVideoIds;
        }

        internal static ExperimentStimulusAllowlist LoadStimulusAllowlist()
        {
            string repositoryRoot;
            if (!RepositoryPathResolver.TryResolveRepositoryRoot(out repositoryRoot))
            {
                return ExperimentStimulusAllowlist.AllowAll;
            }

            string configPath = Path.Combine(repositoryRoot, RuntimeConfigRelativePath);
            if (!File.Exists(configPath))
            {
                return ExperimentStimulusAllowlist.AllowAll;
            }

            try
            {
                string json = File.ReadAllText(configPath);
                RuntimeConfigPayload payload = JsonUtility.FromJson<RuntimeConfigPayload>(json);
                if (payload == null)
                {
                    Debug.LogWarning(
                        $"[ExperimentRuntimeConfig] No se pudo leer '{configPath}'. " +
                        "Se mostraran todos los videos."
                    );
                    return ExperimentStimulusAllowlist.AllowAll;
                }

                HashSet<string> allowedVideoIds =
                    new HashSet<string>(StringComparer.OrdinalIgnoreCase);

                if (payload.allowedVideoIds != null)
                {
                    for (int i = 0; i < payload.allowedVideoIds.Length; i++)
                    {
                        string normalizedVideoId = NormalizeVideoId(payload.allowedVideoIds[i]);
                        if (!string.IsNullOrWhiteSpace(normalizedVideoId))
                        {
                            allowedVideoIds.Add(normalizedVideoId);
                        }
                    }
                }

                if (payload.stimulusAllowlistEnabled && allowedVideoIds.Count == 0)
                {
                    Debug.LogWarning(
                        $"[ExperimentRuntimeConfig] '{configPath}' tiene la allowlist activada " +
                        "pero no define ningun video valido. Se mostraran todos los videos."
                    );
                    return ExperimentStimulusAllowlist.AllowAll;
                }

                return new ExperimentStimulusAllowlist(
                    payload.stimulusAllowlistEnabled,
                    configPath,
                    allowedVideoIds
                );
            }
            catch (Exception exception)
            {
                Debug.LogWarning(
                    $"[ExperimentRuntimeConfig] Error leyendo '{configPath}': {exception.Message}. " +
                    "Se mostraran todos los videos."
                );
                return ExperimentStimulusAllowlist.AllowAll;
            }
        }

        internal static string NormalizeVideoId(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return string.Empty;
            }

            string trimmed = value.Trim().Trim('"');
            if (string.IsNullOrWhiteSpace(trimmed))
            {
                return string.Empty;
            }

            return Path.GetFileNameWithoutExtension(trimmed).Trim();
        }
    }
}
