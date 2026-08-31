using System;
using System.Threading;
using System.Threading.Tasks;
using BSBRLeaderboard.Core;
using Newtonsoft.Json;
using SiraUtil.Web;

namespace BSBRLeaderboard.Features.Leaderboards.Services {

    internal class BSBRScoreRow {
        [JsonProperty("rank")]
        internal int Rank { get; set; }
        [JsonProperty("player_name")]
        internal string PlayerName { get; set; }
        [JsonProperty("player_ss_id")]
        internal string PlayerSsId { get; set; }
        [JsonProperty("score")]
        internal long Score { get; set; }
        [JsonProperty("acc")]
        internal float? Acc { get; set; }
        [JsonProperty("pp")]
        internal float Pp { get; set; }
        [JsonProperty("full_combo")]
        internal bool FullCombo { get; set; }
        [JsonProperty("modifiers")]
        internal string Modifiers { get; set; }
    }

    internal class BSBRPlayerInfo {
        [JsonProperty("ss_id")]
        internal string SsId { get; set; }
        [JsonProperty("name")]
        internal string Name { get; set; }
        [JsonProperty("rank")]
        internal int Rank { get; set; }
    }

    internal class BSBRLeaderboardResponse {
        [JsonProperty("hash")]
        internal string Hash { get; set; }
        [JsonProperty("map_name")]
        internal string MapName { get; set; }
        [JsonProperty("mapper")]
        internal string Mapper { get; set; }
        [JsonProperty("cover_url")]
        internal string CoverUrl { get; set; }
        [JsonProperty("bpm")]
        internal float? Bpm { get; set; }
        [JsonProperty("difficulty")]
        internal string Difficulty { get; set; }
        [JsonProperty("characteristic")]
        internal string Characteristic { get; set; }
        [JsonProperty("total_stars")]
        internal float? TotalStars { get; set; }
        [JsonProperty("acc_stars")]
        internal float? AccStars { get; set; }
        [JsonProperty("tech_stars")]
        internal float? TechStars { get; set; }
        [JsonProperty("speed_stars")]
        internal float? SpeedStars { get; set; }
        [JsonProperty("total")]
        internal int Total { get; set; }
        [JsonProperty("has_more")]
        internal bool HasMore { get; set; }
        [JsonProperty("scores")]
        internal BSBRScoreRow[] Scores { get; set; } = Array.Empty<BSBRScoreRow>();
        [JsonProperty("player")]
        internal BSBRPlayerInfo Player { get; set; }
    }

    /// <summary>Busca o leaderboard do BSBR para (hash, difficulty, characteristic).</summary>
    internal class BSBRLeaderboardService {

        private readonly IHttpService _http;
        private readonly string _playerId;  // ss_id (Steam ID) do jogador local, p/ destacar

        internal BSBRLeaderboardService(IHttpService http, IPlatformUserModel platformUserModel) {
            _http = http;
            _playerId = TryGetSteamId(platformUserModel);
        }

        internal async Task<BSBRLeaderboardResponse> FetchAsync(string songHash, string difficulty, string characteristic, int offset = 0) {
            var config = BSBRConfig.Instance;
            var url = $"{config.ApiBaseUrl.TrimEnd('/')}/leaderboard/{songHash}" +
                      $"?difficulty={Uri.EscapeDataString(difficulty)}" +
                      $"&characteristic={Uri.EscapeDataString(characteristic)}" +
                      $"&limit=10&offset={offset}" +
                      (string.IsNullOrEmpty(_playerId) ? "" : $"&player_id={_playerId}");
            try {
                var response = await _http.GetAsync(url);
                if (response == null || !response.Successful) {
                    Plugin.Log?.Warn($"Falha ao buscar leaderboard BSBR (HTTP {(response?.Code.ToString() ?? "sem resposta")})");
                    return null;
                }
                var body = await response.ReadAsStringAsync();
                if (string.IsNullOrEmpty(body)) {
                    return null;
                }
                return JsonConvert.DeserializeObject<BSBRLeaderboardResponse>(body);
            } catch (Exception ex) {
                Plugin.Log?.Warn($"Falha ao buscar leaderboard BSBR: {ex.Message}");
                return null;
            }
        }

        private static string TryGetSteamId(IPlatformUserModel platformUserModel) {
            try {
#if V129
                // 1.29.1 (Mono): IPlatformUserModel.GetUserInfo() sem CancellationToken.
                var userInfo = platformUserModel?.GetUserInfo().GetAwaiter().GetResult();
#else
                var userInfo = platformUserModel?.GetUserInfo(CancellationToken.None).GetAwaiter().GetResult();
#endif
                return userInfo?.platformUserId ?? string.Empty;
            } catch (Exception ex) {
                Plugin.Log?.Warn($"Falha ao obter playerId da plataforma: {ex.Message}");
                return string.Empty;
            }
        }
    }
}
