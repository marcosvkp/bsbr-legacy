using BeatSaberMarkupLanguage.Attributes;
using BSBRLeaderboard.Features.Leaderboards.Addons;
using BSBRLeaderboard.Features.Leaderboards.Services;
using System;

namespace BSBRLeaderboard.Features.Leaderboards.Adapters {

    /// <summary>
    /// Fonte de dados de uma linha do leaderboard customizado: expõe os UIValues
    /// do template BSBRLeaderboardCell.bsml a partir de um BSBRScoreRow.
    /// </summary>
    internal class BSBRLeaderboardEntryDisplay : IBSBRCellDataSource {

        private const string CellTemplate = "BSBRLeaderboard.Features.Leaderboards.Adapters.BSBRLeaderboardCell.bsml";
        private const float CellHeight = 5.5f;

        [UIValue("rank-text")]
        private readonly string _rankText;

        [UIValue("player-name")]
        private readonly string _playerName;

        [UIValue("acc-text")]
        private readonly string _accText;

        [UIValue("pp-text")]
        private readonly string _ppText;

        [UIValue("score-text")]
        private readonly string _scoreText;

        public int TemplateId { get; set; }

        public string TemplatePath => CellTemplate;

        public float CellSize => CellHeight;

        internal BSBRLeaderboardEntryDisplay(BSBRScoreRow row, BSBRPlayerInfo player) {
            bool isMine = player != null && row.PlayerSsId == player.SsId;
            string nameColor = isMine ? "#ffd244" : "#ffffff";

            _rankText = $"<color=#999999>{row.Rank}</color>";
            _playerName = $"<color={nameColor}>{row.PlayerName}</color>";
            _accText = row.Acc.HasValue
                ? $"<color=#98ff00>{row.Acc.Value * 100f:0.00}%</color>"
                : "<color=#666666>—</color>";
            _ppText = row.Pp > 0
                ? $"<color=#6772e5>{row.Pp:0.00}</color>"
                : "<color=#666666>—</color>";
            var fc = row.FullCombo ? "<color=#22c55e>FC</color>" : "";
            var score = row.Score.ToString("N0");
            _scoreText = string.IsNullOrEmpty(fc) ? score : $"{score}  {fc}";
        }
    }
}
