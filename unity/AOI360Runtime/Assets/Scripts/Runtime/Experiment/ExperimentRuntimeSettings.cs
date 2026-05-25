using UnityEngine;

namespace AOI360.Runtime.Experiment
{
    public static class ExperimentRuntimeSettings
    {
        private const string CountdownSecondsPrefsKey = "AOI360.Experiment.CountdownSeconds";
        private const string VideoVolumePrefsKey = "AOI360.Experiment.VideoVolume";
        private const string CountdownBeepEnabledPrefsKey = "AOI360.Experiment.CountdownBeepEnabled";
        private const string CountdownBeepVolumePrefsKey = "AOI360.Experiment.CountdownBeepVolume";

        private const float DefaultCountdownSeconds = 5f;
        private const float DefaultVideoVolume = 1f;
        private const float DefaultCountdownBeepVolume = 0.75f;
        private const float MinCountdownSeconds = 0f;
        private const float MaxCountdownSeconds = 15f;

        public static float CountdownSeconds
        {
            get
            {
                float storedValue = PlayerPrefs.GetFloat(CountdownSecondsPrefsKey, DefaultCountdownSeconds);
                return NormalizeCountdownSeconds(storedValue);
            }
        }

        public static float VideoVolume
        {
            get
            {
                float storedValue = PlayerPrefs.GetFloat(VideoVolumePrefsKey, DefaultVideoVolume);
                return NormalizeVolume(storedValue);
            }
        }

        public static bool CountdownBeepEnabled
        {
            get
            {
                return PlayerPrefs.GetInt(CountdownBeepEnabledPrefsKey, 1) != 0;
            }
        }

        public static float CountdownBeepVolume
        {
            get
            {
                float storedValue = PlayerPrefs.GetFloat(CountdownBeepVolumePrefsKey, DefaultCountdownBeepVolume);
                return NormalizeVolume(storedValue);
            }
        }

        public static void SetCountdownSeconds(float value)
        {
            SaveFloatPreference(
                CountdownSecondsPrefsKey,
                NormalizeCountdownSeconds(value)
            );
        }

        public static void SetVideoVolume(float value)
        {
            SaveFloatPreference(
                VideoVolumePrefsKey,
                NormalizeVolume(value)
            );
        }

        public static void SetCountdownBeepEnabled(bool value)
        {
            PlayerPrefs.SetInt(CountdownBeepEnabledPrefsKey, value ? 1 : 0);
            PlayerPrefs.Save();
        }

        public static void SetCountdownBeepVolume(float value)
        {
            SaveFloatPreference(
                CountdownBeepVolumePrefsKey,
                NormalizeVolume(value)
            );
        }

        private static void SaveFloatPreference(string prefsKey, float value)
        {
            PlayerPrefs.SetFloat(prefsKey, value);
            PlayerPrefs.Save();
        }

        private static float NormalizeCountdownSeconds(float value)
        {
            return Mathf.Clamp(Mathf.Round(value), MinCountdownSeconds, MaxCountdownSeconds);
        }

        private static float NormalizeVolume(float value)
        {
            return Mathf.Clamp01(value);
        }
    }
}
