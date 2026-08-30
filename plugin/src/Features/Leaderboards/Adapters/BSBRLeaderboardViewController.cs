using System;
using System.Collections.Generic;
using BeatSaberMarkupLanguage.Attributes;
using BSBRLeaderboard.Features.Leaderboards.Services;
using HMUI;
using IPA.Utilities;
using TMPro;
using UnityEngine;
using Zenject;

namespace BSBRLeaderboard.Features.Leaderboards.Adapters {

    /// <summary>
    /// Painel do leaderboard BSBR — tabela nativa do jogo via BSML.
    ///
    /// Correções de runtime (problemas vistos no jogo):
    /// 1. O LeaderboardTableCell nativo nasce com richText desligado — sem isso
    ///    os tags &lt;color&gt; do nome aparecem como texto cru. Ativamos via
    ///    didReloadDataEvent da TableView interna (mesmo approach do pc-mod).
    /// 2. O PlatformLeaderboardViewController mantém o LoadingControl nativo
    ///    ativo por baixo do nosso painel — escondemos no DidActivate E a cada
    ///    reload (o jogo o re-mostra ao trocar de mapa).
    /// 3. Paginação: top 10 por página, com setas cima/baixo (offset no backend).
    /// </summary>
    internal class BSBRLeaderboardViewController : BeatSaberMarkupLanguage.ViewControllers.BSMLAutomaticViewController {

        private const int PageSize = 10;

        private static readonly FieldAccessor<LeaderboardTableView, TableView>.Accessor InnerTable =
            FieldAccessor<LeaderboardTableView, TableView>.GetAccessor("_tableView");

        private static readonly FieldAccessor<LeaderboardTableCell, TextMeshProUGUI>.Accessor PlayerNameText =
            FieldAccessor<LeaderboardTableCell, TextMeshProUGUI>.GetAccessor("_playerNameText");

        private static readonly FieldAccessor<PlatformLeaderboardViewController, LoadingControl>.Accessor PlatformLoadingControl =
            FieldAccessor<PlatformLeaderboardViewController, LoadingControl>.GetAccessor("_loadingControl");

        [UIComponent("leaderboard")]
        private readonly LeaderboardTableView _leaderboard = null;

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
        private TableView _innerTable;
        private string _currentHash;
        private string _currentDifficulty;
        private string _currentCharacteristic;
        private int _offset;

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
            if (response.Scores == null || response.Scores.Length == 0) {
                ShowError("Sem scores BSBR", "Esse mapa não tem scores BSBR nessa dificuldade");
                return;
            }

            var rows = new List<LeaderboardTableView.ScoreData>();
            var myScoreIndex = -1;
            for (int i = 0; i < response.Scores.Length; i++) {
                var row = response.Scores[i];
                bool isMine = response.Player != null && row.PlayerSsId == response.Player.SsId;
                if (isMine) {
                    myScoreIndex = i;
                }
                rows.Add(new LeaderboardTableView.ScoreData(
                    (int)row.Score,
                    FormatRow(row),
                    row.Rank,
                    row.FullCombo
                ));
            }
            ScoresActive = true;
            UpEnabled = _offset > 0;
            DownEnabled = response.HasMore;
            NotifyPropertyChanged(nameof(ScoresActive));
            NotifyPropertyChanged(nameof(ErrorActive));
            NotifyPropertyChanged(nameof(UpEnabled));
            NotifyPropertyChanged(nameof(DownEnabled));
            if (_leaderboard != null) {
                _leaderboard.SetScores(rows, myScoreIndex);
                BindRichTextReload();
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
                _leaderboard.SetScores(new List<LeaderboardTableView.ScoreData>(), -1);
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

        // Ativa richText nas células do nome do jogador (senão <color> vira texto cru)
        private void BindRichTextReload() {
            if (_leaderboard == null) {
                return;
            }
            var leaderboard = _leaderboard;
            if (_innerTable == null) {
                _innerTable = InnerTable(ref leaderboard);
            }
            if (_innerTable == null) {
                return;
            }
            _innerTable.didReloadDataEvent -= TableDidReloadData;
            _innerTable.didReloadDataEvent += TableDidReloadData;
            ConfigureVisibleCells();
        }

        private void TableDidReloadData(TableView tableView) => ConfigureVisibleCells();

        private void ConfigureVisibleCells() {
            if (_innerTable == null) {
                return;
            }
            foreach (TableCell cell in _innerTable.visibleCells) {
                if (cell is LeaderboardTableCell leaderboardCell) {
                    EnableRichText(leaderboardCell);
                }
            }
        }

        private static void EnableRichText(LeaderboardTableCell cell) {
            var playerNameText = PlayerNameText(ref cell);
            if (playerNameText == null) {
                return;
            }
            if (!playerNameText.richText) {
                playerNameText.richText = true;
            }
            // reaplica o texto para re-renderizar os tags
            playerNameText.text = playerNameText.text;
            playerNameText.SetVerticesDirty();
        }

        private static string FormatRow(BSBRScoreRow row) {
            var acc = row.Acc.HasValue ? $"<color=#98ff00>{row.Acc.Value * 100f:0.00}%</color>" : "<color=#888888>—</color>";
            var pp = row.Pp > 0 ? $"<color=#6772E5>{row.Pp:0.00}<size=70%>pp</size></color>" : "";
            return $"<color=#ffffff>{row.PlayerName}</color>  {acc}  {pp}".Trim();
        }
    }
}
