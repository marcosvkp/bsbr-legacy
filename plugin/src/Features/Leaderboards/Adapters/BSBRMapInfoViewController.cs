using BeatSaberMarkupLanguage.Attributes;
using BSBRLeaderboard.Features.Leaderboards.Services;
using Zenject;

namespace BSBRLeaderboard.Features.Leaderboards.Adapters {

    /// <summary>
    /// Painel de info do mapa exibido ACIMA do HIGHSCORES (panelViewController
    /// do LeaderboardCore → FloatingScreen próprio, mesma posição do painel de
    /// stats do ScoreSaber). Recebe os dados via SetInfo a cada fetch.
    /// </summary>
    internal class BSBRMapInfoViewController : BeatSaberMarkupLanguage.ViewControllers.BSMLAutomaticViewController {

        [UIValue("info-active")]
        private bool InfoActive { get; set; }

        [UIValue("map-title")]
        private string MapTitle { get; set; } = "";

        [UIValue("map-stars")]
        private string MapStars { get; set; } = "";

        [UIValue("map-meta")]
        private string MapMeta { get; set; } = "";

        [Inject]
        private void Construct() {
        }

        internal void SetInfo(BSBRLeaderboardResponse response) {
            if (response == null) {
                return;
            }
            MapTitle = response.MapName ?? "Mapa desconhecido";
            var t = response.TotalStars ?? 0;
            var a = response.AccStars ?? 0;
            var tt = response.TechStars ?? 0;
            var s = response.SpeedStars ?? 0;
            var bpm = response.Bpm;
            MapStars =
                $"<color=#ffd244>{t:0.##}★ Total</color>" +
                (bpm.HasValue ? $"  <color=#aaaaaa>|  {bpm.Value:0} BPM</color>" : "") +
                "\n" +
                $"<color=#98ff00>{a:0.##} Acc</color>  |  " +
                $"<color=#6772e5>{tt:0.##} Tech</color>  |  " +
                $"<color=#ff6b6b>{s:0.##} Speed</color>";
            MapMeta =
                $"<color=#bbbbbb>{response.Characteristic} • {response.Difficulty}</color>" +
                (string.IsNullOrEmpty(response.Mapper) ? "" : $"  <color=#999>Mapper: {response.Mapper}</color>");
            InfoActive = true;
            NotifyPropertyChanged(nameof(MapTitle));
            NotifyPropertyChanged(nameof(MapStars));
            NotifyPropertyChanged(nameof(MapMeta));
            NotifyPropertyChanged(nameof(InfoActive));
        }

        internal void ClearInfo() {
            InfoActive = false;
            NotifyPropertyChanged(nameof(InfoActive));
        }
    }
}
