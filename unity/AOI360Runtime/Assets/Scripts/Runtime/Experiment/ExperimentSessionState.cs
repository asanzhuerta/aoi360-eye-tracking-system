using UnityEngine;

namespace AOI360.Runtime.Experiment
{
    public static class ExperimentSessionState
    {
        private const string ParticipantCounterPrefsKey = "AOI360.ParticipantCounter";

        private static bool runtimeIdentifiersInitialized;

        public static ExperimentStimulusDefinition SelectedStimulus { get; private set; }
        public static bool HasSelectedStimulus => SelectedStimulus != null;
        public static bool IsPlaybackStartLocked { get; private set; }
        public static float CountdownSeconds { get; private set; } = 5f;
        public static float VideoVolume { get; private set; } = 1f;
        public static bool CountdownBeepEnabled { get; private set; } = true;
        public static float CountdownBeepVolume { get; private set; } = 0.75f;
        public static int CurrentParticipantNumber { get; private set; }
        public static int CurrentSessionNumber { get; private set; }
        public static string CurrentParticipantId
        {
            get
            {
                EnsureRuntimeIdentifiersInitialized();
                return FormatParticipantId(CurrentParticipantNumber);
            }
        }

        public static string CurrentSessionId
        {
            get
            {
                EnsureRuntimeIdentifiersInitialized();
                return CurrentSessionNumber > 0 ? FormatSessionId(CurrentSessionNumber) : string.Empty;
            }
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetRuntimeState()
        {
            runtimeIdentifiersInitialized = false;
            CurrentParticipantNumber = 0;
            CurrentSessionNumber = 0;
            SelectedStimulus = null;
            IsPlaybackStartLocked = false;
            CountdownSeconds = 5f;
            VideoVolume = 1f;
            CountdownBeepEnabled = true;
            CountdownBeepVolume = 0.75f;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void InitializeRuntimeIdentifiers()
        {
            EnsureRuntimeIdentifiersInitialized();
        }

        public static void SetSelectedStimulus(
            ExperimentStimulusDefinition stimulus,
            bool lockPlaybackStart = true,
            float countdownSeconds = 5f,
            float videoVolume = 1f,
            bool countdownBeepEnabled = true,
            float countdownBeepVolume = 0.75f
        )
        {
            SelectedStimulus = stimulus;
            IsPlaybackStartLocked = lockPlaybackStart;
            CountdownSeconds = Mathf.Max(0f, countdownSeconds);
            VideoVolume = Mathf.Clamp01(videoVolume);
            CountdownBeepEnabled = countdownBeepEnabled;
            CountdownBeepVolume = Mathf.Clamp01(countdownBeepVolume);
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
            VideoVolume = 1f;
            CountdownBeepEnabled = true;
            CountdownBeepVolume = 0.75f;
        }

        public static string ReserveNextSessionId()
        {
            EnsureRuntimeIdentifiersInitialized();
            CurrentSessionNumber = Mathf.Max(0, CurrentSessionNumber) + 1;
            return FormatSessionId(CurrentSessionNumber);
        }

        public static string PeekNextSessionId()
        {
            EnsureRuntimeIdentifiersInitialized();
            return FormatSessionId(Mathf.Max(0, CurrentSessionNumber) + 1);
        }

        private static void EnsureRuntimeIdentifiersInitialized()
        {
            if (runtimeIdentifiersInitialized)
            {
                return;
            }

            // Each Unity app execution advances the participant counter once.
            // This keeps one participant id per app run even when multiple
            // experiments are launched before returning to the desktop.
            int lastParticipantNumber = PlayerPrefs.GetInt(ParticipantCounterPrefsKey, 0);
            CurrentParticipantNumber = Mathf.Max(0, lastParticipantNumber) + 1;
            CurrentSessionNumber = 0;

            PlayerPrefs.SetInt(ParticipantCounterPrefsKey, CurrentParticipantNumber);
            PlayerPrefs.Save();

            runtimeIdentifiersInitialized = true;
        }

        private static string FormatParticipantId(int participantNumber)
        {
            return $"P{Mathf.Max(0, participantNumber):D3}";
        }

        private static string FormatSessionId(int sessionNumber)
        {
            return $"S{Mathf.Max(0, sessionNumber):D3}";
        }
    }
}
