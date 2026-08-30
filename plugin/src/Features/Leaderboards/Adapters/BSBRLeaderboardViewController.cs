using System;
using System.Collections.Generic;
using BeatSaberMarkupLanguage.Attributes;
using BSBRLeaderboard.Features.Leaderboards.Addons;
using BSBRLeaderboard.Features.Leaderboards.Services;
using HMUI;
using IPA.Utilities;
using Zenject;

namespace BSBRLeaderboard.Features.Leaderboards.Adapters {

    /// <summary>
    /// Painel do leaderboard BSBR — lista de células BSML customizadas (port do
    /// AccSaber), substituindo o &lt;leaderboard&gt; nativo. Isso elimina:
    /// 1. Rich text literal (células são templates BSML com richText nativo).
    /// 2. Loading duplicado (sem LeaderboardTableView nativa).
    /// O LoadingControl nativo da plataforma ainda é escondido (defensivo).
    /// Paginação: top 10 por página com setas cima/baixo (offset no backend).
    /// </summary>
    [ViewDefinition("BSBRLeaderboard.Features.Leaderboards.Adapters.BSBRLeaderboardViewController.bsml")]
    internal class BSBRLeaderboardViewController : BSBRSafeAutomaticViewController {

        private const int PageSize = 10;

        private static readonly FieldAccessor<PlatformLeaderboardViewController, LoadingControl>.Accessor PlatformLoadingControl =
            FieldAccessor<PlatformLeaderboardViewController, LoadingControl>.GetAccessor("_loadingControl");

        [UIComponent("leaderboard")]
        private readonly BSBRCellListTableData _leaderboard = null;

        [UIValue("leaderboard-contents")]
        private List<IBSBRCellDataSource> LeaderboardContents { get; set; } = new();

        [UIValue("scores-active")]
        private bool ScoresActive { get; set; }

        [UIValue("error-active")]
        private bool ErrorActive { get; set; }

        [UIValue("error-title")]
        private string ErrorTitle { get; set; } = "";

        [UIValue("error-text")]
        private string ErrorText { get; set; } = "";

        [UIValue("up-enabled")]
        private bool UpEnabled { get; set; }

        [UIValue("down-enabled")]
        private bool DownEnabled { get; set; }

        private BSBRLeaderboardService _service;
        private PlatformLeaderboardViewController _platformLeaderboardViewController;
        private string _currentHash;
        private string _currentDifficulty;
        private string _currentCharacteristic;
        private int _offset;

        /// <summary>Disparado quando o fetch retorna — alimenta o painel de info do mapa.</summary>
        internal event Action<BSBRLeaderboardResponse> MapInfoUpdated;

        [Inject]
        private void Construct(PlatformLeaderboardViewController platformLeaderboardViewController) {
            _platformLeaderboardViewController = platformLeaderboardViewController;
        }

        internal void Init(BSBRLeaderboardService service) {
            _service = service;
        }

        internal void OnLeaderboardSet(string songHash, string difficulty, string characteristic) {
            if (_service == null) {
                return;
            }
            _currentHash = songHash;
            _currentDifficulty = difficulty;
            _currentCharacteristic = characteristic;
            _offset = 0;  // novo mapa/dificuldade → volta ao topo
            _ = LoadAsync();
        }

        protected override void DidActivate(bool firstActivation, bool addedToHierarchy, bool screenSystemEnabling) {
            base.DidActivate(firstActivation, addedToHierarchy, screenSystemEnabling);
            HidePlatformLoading();
        }

        [UIAction("up-clicked")]
        private void UpClicked() {
            if (_offset <= 0) {
                return;
            }
            _offset -= PageSize;
            _ = LoadAsync();
        }

        [UIAction("down-clicked")]
        private void DownClicked() {
            // down-enabled só liga quando há mais; o refresh refaz o fetch com o novo offset
            _offset += PageSize;
            _ = LoadAsync();
        }

        private async System.Threading.Tasks.Task LoadAsync() {
            ScoresActive = false;
            ErrorActive = false;
            NotifyPropertyChanged(nameof(ScoresActive));
            NotifyPropertyChanged(nameof(ErrorActive));
            HidePlatformLoading();

            var response = await _service.FetchAsync(_currentHash, _currentDifficulty, _currentCharacteristic, _offset);

            if (response == null) {
                ShowError("Sem resposta do BSBR", "Verifique sua conexão com bsbr.pro");
                return;
            }

            // repassa os dados do mapa ao painel acima do HIGHSCORES (panelViewController)
            MapInfoUpdated?.Invoke(response);

            if (response.Scores == null || response.Scores.Length == 0) {
                ShowError("Sem scores BSBR", "Esse mapa não tem scores BSBR nessa dificuldade");
                return;
            }

            var contents = new List<IBSBRCellDataSource>();
            for (int i = 0; i < response.Scores.Length; i++) {
                contents.Add(new BSBRLeaderboardEntryDisplay(response.Scores[i], response.Player));
            }

            LeaderboardContents = contents;
            ScoresActive = true;
            UpEnabled = _offset > 0;
            DownEnabled = response.HasMore;
            NotifyPropertyChanged(nameof(ScoresActive));
            NotifyPropertyChanged(nameof(ErrorActive));
            NotifyPropertyChanged(nameof(UpEnabled));
            NotifyPropertyChanged(nameof(DownEnabled));

            if (_leaderboard != null) {
                _leaderboard.Data = contents;  // setter dispara ReloadTemplates
            }
            HidePlatformLoading();
        }

        private void ShowError(string title, string text) {
            ErrorActive = true;
            ScoresActive = false;
            UpEnabled = _offset > 0;
            DownEnabled = false;
            ErrorTitle = title;
            ErrorText = text;
            NotifyPropertyChanged(nameof(ErrorActive));
            NotifyPropertyChanged(nameof(ScoresActive));
            NotifyPropertyChanged(nameof(UpEnabled));
            NotifyPropertyChanged(nameof(DownEnabled));
            NotifyPropertyChanged(nameof(ErrorTitle));
            NotifyPropertyChanged(nameof(ErrorText));
            if (_leaderboard != null) {
                _leaderboard.Data = new List<IBSBRCellDataSource>();  // setter limpa as células
            }
            HidePlatformLoading();
        }

        private void HidePlatformLoading() {
            if (_platformLeaderboardViewController == null) {
                return;
            }
            var loadingControl = PlatformLoadingControl(ref _platformLeaderboardViewController);
            loadingControl?.Hide();
        }
    }
}
