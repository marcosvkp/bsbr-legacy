using System;
using BSBRLeaderboard.Features.Leaderboards.Domain;
using BSBRLeaderboard.Features.Leaderboards.Services;
using HMUI;
using LeaderboardCore.Interfaces;
using LeaderboardCore.Managers;
using LeaderboardCore.Models;
using Zenject;

namespace BSBRLeaderboard.Features.Leaderboards.Adapters {

    /// <summary>
    /// Registra o leaderboard "BSBR" no LeaderboardCore (tab própria no painel
    /// de leaderboard do jogo). A cada mapa/dificuldade selecionada o
    /// LeaderboardCore chama OnLeaderboardSet → busca o top no backend.
    /// </summary>
    internal class BSBRCustomLeaderboard : CustomLeaderboard, IInitializable, IDisposable, INotifyLeaderboardSet {

        private readonly CustomLeaderboardManager _manager;
        private readonly BSBRLeaderboardService _service;
        private readonly BSBRLeaderboardViewController _viewController;

        internal BSBRCustomLeaderboard(
            CustomLeaderboardManager manager,
            BSBRLeaderboardService service,
            BSBRLeaderboardViewController viewController) {
            _manager = manager;
            _service = service;
            _viewController = viewController;
        }

        protected override string leaderboardId => "BSBR";

        protected override ViewController panelViewController => null;

        protected override ViewController leaderboardViewController => _viewController;

        public void Initialize() {
            _viewController.Init(_service);
            _manager.Register(this);
        }

        public void Dispose() {
            _manager.Unregister(this);
        }

        public override bool ShowForLevel(BeatmapKey? beatmapKey) =>
            beatmapKey != null && BSBRBeatmapKey.IsSupportedLevelId(beatmapKey.Value.levelId);

        public void OnLeaderboardSet(BeatmapKey beatmapKey) {
            if (!BSBRBeatmapKey.TryGetSongHash(beatmapKey, out var hash)) {
                return;
            }
            var difficulty = beatmapKey.difficulty.ToString();
            var characteristic = beatmapKey.beatmapCharacteristic.serializedName;
            _viewController.OnLeaderboardSet(hash, difficulty, characteristic);
        }
    }
}
