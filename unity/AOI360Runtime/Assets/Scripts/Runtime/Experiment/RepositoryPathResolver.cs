using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AOI360.Runtime.Experiment
{
    public static class RepositoryPathResolver
    {
        private const string RepositoryRootEnvironmentVariable = "AOI360_REPOSITORY_ROOT";
        private static readonly string[] CommandLinePrefixes =
        {
            "--aoi360-repo-root=",
            "-aoi360RepoRoot=",
            "/aoi360RepoRoot="
        };

        private static bool hasCachedRepositoryRoot;
        private static string cachedRepositoryRoot = string.Empty;

        public static bool TryResolveRepositoryRoot(out string repositoryRoot)
        {
            if (hasCachedRepositoryRoot && IsRepositoryRoot(cachedRepositoryRoot))
            {
                repositoryRoot = cachedRepositoryRoot;
                return true;
            }

            if (TryGetExplicitRepositoryRoot(out string explicitRepositoryRoot))
            {
                CacheRepositoryRoot(explicitRepositoryRoot);
                repositoryRoot = explicitRepositoryRoot;
                return true;
            }

            List<string> candidateDirectories = new List<string>();
            AddCandidateDirectory(candidateDirectories, Application.dataPath);
            AddCandidateDirectory(candidateDirectories, Application.streamingAssetsPath);
            AddCandidateDirectory(candidateDirectories, Environment.CurrentDirectory);
            AddCandidateDirectory(candidateDirectories, AppDomain.CurrentDomain.BaseDirectory);

            for (int i = 0; i < candidateDirectories.Count; i++)
            {
                if (!TrySearchAncestors(candidateDirectories[i], out repositoryRoot))
                {
                    continue;
                }

                CacheRepositoryRoot(repositoryRoot);
                return true;
            }

            repositoryRoot = string.Empty;
            return false;
        }

        private static void AddCandidateDirectory(List<string> candidates, string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return;
            }

            candidates.Add(path);
        }

        private static void CacheRepositoryRoot(string repositoryRoot)
        {
            hasCachedRepositoryRoot = !string.IsNullOrWhiteSpace(repositoryRoot);
            cachedRepositoryRoot = hasCachedRepositoryRoot
                ? repositoryRoot
                : string.Empty;
        }

        private static bool TryGetExplicitRepositoryRoot(out string repositoryRoot)
        {
            repositoryRoot = string.Empty;

            string environmentPath = Environment.GetEnvironmentVariable(RepositoryRootEnvironmentVariable);
            if (TryNormalizeRepositoryRoot(environmentPath, out repositoryRoot))
            {
                return true;
            }

            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length; i++)
            {
                string argument = args[i];
                if (string.IsNullOrWhiteSpace(argument))
                {
                    continue;
                }

                for (int prefixIndex = 0; prefixIndex < CommandLinePrefixes.Length; prefixIndex++)
                {
                    string prefix = CommandLinePrefixes[prefixIndex];
                    if (!argument.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    string candidateValue = argument.Substring(prefix.Length);
                    if (TryNormalizeRepositoryRoot(candidateValue, out repositoryRoot))
                    {
                        return true;
                    }
                }

                if (!string.Equals(argument, "--aoi360-repo-root", StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(argument, "-aoi360RepoRoot", StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(argument, "/aoi360RepoRoot", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (i + 1 < args.Length && TryNormalizeRepositoryRoot(args[i + 1], out repositoryRoot))
                {
                    return true;
                }
            }

            return false;
        }

        private static bool TrySearchAncestors(string startPath, out string repositoryRoot)
        {
            repositoryRoot = string.Empty;

            if (!TryNormalizeExistingDirectory(startPath, out string normalizedStartPath))
            {
                return false;
            }

            DirectoryInfo currentDirectory = new DirectoryInfo(normalizedStartPath);
            while (currentDirectory != null)
            {
                if (IsRepositoryRoot(currentDirectory.FullName))
                {
                    repositoryRoot = currentDirectory.FullName;
                    return true;
                }

                currentDirectory = currentDirectory.Parent;
            }

            return false;
        }

        private static bool TryNormalizeRepositoryRoot(string candidatePath, out string repositoryRoot)
        {
            repositoryRoot = string.Empty;

            if (!TryNormalizeExistingDirectory(candidatePath, out string normalizedDirectory))
            {
                return false;
            }

            if (!IsRepositoryRoot(normalizedDirectory))
            {
                return false;
            }

            repositoryRoot = normalizedDirectory;
            return true;
        }

        private static bool TryNormalizeExistingDirectory(string candidatePath, out string normalizedDirectory)
        {
            normalizedDirectory = string.Empty;

            if (string.IsNullOrWhiteSpace(candidatePath))
            {
                return false;
            }

            string trimmedPath = candidatePath.Trim().Trim('"');
            if (string.IsNullOrWhiteSpace(trimmedPath))
            {
                return false;
            }

            string directoryPath = trimmedPath;
            if (File.Exists(trimmedPath))
            {
                directoryPath = Path.GetDirectoryName(trimmedPath);
            }

            if (string.IsNullOrWhiteSpace(directoryPath) || !Directory.Exists(directoryPath))
            {
                return false;
            }

            normalizedDirectory = Path.GetFullPath(directoryPath);
            return true;
        }

        private static bool IsRepositoryRoot(string candidateRoot)
        {
            if (string.IsNullOrWhiteSpace(candidateRoot))
            {
                return false;
            }

            return Directory.Exists(Path.Combine(candidateRoot, "data")) &&
                   Directory.Exists(Path.Combine(candidateRoot, "unity"));
        }
    }
}
