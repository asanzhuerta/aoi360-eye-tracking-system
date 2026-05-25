using System.IO;
using AOI360.Runtime.Experiment;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace AOI360.Editor
{
    public static class BuildWindowsPlayer
    {
        private const string BuildFolderName = "build";
        private const string WindowsFolderName = "windows";
        private const string PlayerFolderName = "AOI360Runtime";
        private const string ExecutableName = "AOI360Runtime.exe";
<<<<<<< HEAD
=======
        private static readonly string RuntimeConfigRelativePath =
            Path.Combine("data", "experiment", "runtime_config.json");
>>>>>>> feat/pilot-test-ready

        [MenuItem("Tools/AOI/Build Windows x64 Player")]
        public static void BuildWindowsX64Player()
        {
            if (!RepositoryPathResolver.TryResolveRepositoryRoot(out string repositoryRoot))
            {
                Debug.LogError(
                    "[BuildWindowsPlayer] No se ha podido resolver la raiz del repositorio. " +
                    "Abre el proyecto desde la carpeta del repo o define AOI360_REPOSITORY_ROOT."
                );
                return;
            }

            string[] enabledScenes = GetEnabledScenes();
            if (enabledScenes.Length == 0)
            {
                Debug.LogError("[BuildWindowsPlayer] No hay escenas habilitadas en Build Settings.");
                return;
            }

            string outputDirectory = Path.Combine(repositoryRoot, BuildFolderName, WindowsFolderName, PlayerFolderName);
            Directory.CreateDirectory(outputDirectory);

            string executablePath = Path.Combine(outputDirectory, ExecutableName);
            BuildPlayerOptions buildOptions = new BuildPlayerOptions
            {
                scenes = enabledScenes,
                locationPathName = executablePath,
                target = BuildTarget.StandaloneWindows64,
                targetGroup = BuildTargetGroup.Standalone,
                options = BuildOptions.None
            };

            BuildReport report = BuildPipeline.BuildPlayer(buildOptions);
            if (report.summary.result == BuildResult.Succeeded)
            {
<<<<<<< HEAD
                Debug.Log(
                    $"[BuildWindowsPlayer] Build de Windows generado en: {executablePath}\n" +
                    "[BuildWindowsPlayer] Al quedar dentro del repo, el runtime podra seguir leyendo data/ y exportando CSV en data/exports/csv."
=======
                string runtimeConfigPath = Path.Combine(repositoryRoot, RuntimeConfigRelativePath);
                Debug.Log(
                    $"[BuildWindowsPlayer] Build de Windows generado en: {executablePath}\n" +
                    "[BuildWindowsPlayer] Al quedar dentro del repo, el runtime podra seguir leyendo data/ y exportando CSV en data/exports/csv.\n" +
                    $"[BuildWindowsPlayer] La visibilidad de videos en Initial_Scene se controla desde: {runtimeConfigPath}"
>>>>>>> feat/pilot-test-ready
                );
                return;
            }

            Debug.LogError(
                $"[BuildWindowsPlayer] El build de Windows no se completo correctamente. " +
                $"Resultado: {report.summary.result}."
            );
        }

        private static string[] GetEnabledScenes()
        {
            EditorBuildSettingsScene[] buildScenes = EditorBuildSettings.scenes;
            int enabledCount = 0;

            for (int i = 0; i < buildScenes.Length; i++)
            {
                if (buildScenes[i].enabled)
                {
                    enabledCount++;
                }
            }

            string[] enabledScenes = new string[enabledCount];
            int writeIndex = 0;

            for (int i = 0; i < buildScenes.Length; i++)
            {
                if (!buildScenes[i].enabled)
                {
                    continue;
                }

                enabledScenes[writeIndex] = buildScenes[i].path;
                writeIndex++;
            }

            return enabledScenes;
        }
    }
}
