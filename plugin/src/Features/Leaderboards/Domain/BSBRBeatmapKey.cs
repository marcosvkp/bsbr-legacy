using System;

namespace BSBRLeaderboard.Features.Leaderboards.Domain {

    /// <summary>Extrai o song hash (40 hex) de um levelId do jogo.</summary>
    internal static class BSBRBeatmapKey {

        private const string CustomLevelPrefix = "custom_level_";
        private const string WipLevelSuffix = " WIP";
        private const string WipLevelSegment = "_WIP";

        internal static bool IsSupported(BeatmapKey beatmapKey) => TryGetSongHash(beatmapKey, out _);

        internal static bool IsSupportedLevelId(string levelId) => TryGetSongHash(levelId, out _);

        internal static bool IsCustomLevelId(string levelId) =>
            !string.IsNullOrEmpty(levelId) && levelId.StartsWith(CustomLevelPrefix, StringComparison.Ordinal);

        private static bool IsWipLevelId(string levelId) =>
            levelId.EndsWith(WipLevelSuffix, StringComparison.Ordinal)
            || levelId.IndexOf(WipLevelSegment, StringComparison.Ordinal) >= 0;

        internal static bool TryGetSongHash(BeatmapKey beatmapKey, out string songHash) =>
            TryGetSongHash(beatmapKey.levelId, out songHash);

        internal static bool TryGetSongHash(string levelId, out string songHash) {
            songHash = string.Empty;
            if (string.IsNullOrEmpty(levelId) || !IsCustomLevelId(levelId) || IsWipLevelId(levelId)) {
                return false;
            }
            var hash = levelId.Substring(CustomLevelPrefix.Length);
            if (hash.Length != 40) {
                return false;
            }
            songHash = hash.ToLowerInvariant();
            return true;
        }
    }
}
