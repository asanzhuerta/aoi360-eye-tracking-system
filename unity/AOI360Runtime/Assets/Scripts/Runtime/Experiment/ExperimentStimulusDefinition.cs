using System;

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

        public string VideoId { get; private set; }
        public string VideoFileName { get; private set; }
        public string VideoAbsolutePath { get; private set; }
        public string SequenceName { get; private set; }
        public string ManifestAbsolutePath { get; private set; }
        public string MapsDirectoryAbsolutePath { get; private set; }
        public ExperimentStimulusSourceKind SourceKind { get; private set; }
        public string SourceLabel { get; private set; }

        public string DisplayName
        {
            get { return !string.IsNullOrWhiteSpace(VideoId) ? VideoId : SequenceName; }
        }

        public bool HasExternalVideoPath
        {
            get { return !string.IsNullOrWhiteSpace(VideoAbsolutePath); }
        }

        public bool HasManifestPath
        {
            get { return !string.IsNullOrWhiteSpace(ManifestAbsolutePath); }
        }

        public bool HasMapsDirectory
        {
            get { return !string.IsNullOrWhiteSpace(MapsDirectoryAbsolutePath); }
        }
    }
}
