using UnityEngine;

namespace AOI360.Runtime.Experiment
{
    public static class ExperimentSessionState
    {
        public static ExperimentStimulusDefinition SelectedStimulus { get; private set; }
        public static bool HasSelectedStimulus => SelectedStimulus != null;
        public static bool IsPlaybackStartLocked { get; private set; }
        public static float CountdownSeconds { get; private set; } = 5f;

        public static void SetSelectedStimulus(
            ExperimentStimulusDefinition stimulus,
            bool lockPlaybackStart = true,
            float countdownSeconds = 5f
        )
        {
            SelectedStimulus = stimulus;
            IsPlaybackStartLocked = lockPlaybackStart;
            CountdownSeconds = Mathf.Max(0f, countdownSeconds);
        }

        public static void UnlockPlaybackStart()
        {
            IsPlaybackStartLocked = false;
        }

        public static void LockPlaybackStart()
        {
            IsPlaybackStartLocked = true;
        }

        public static void Clear()
        {
            SelectedStimulus = null;
            IsPlaybackStartLocked = false;
            CountdownSeconds = 5f;
        }
    }
}
