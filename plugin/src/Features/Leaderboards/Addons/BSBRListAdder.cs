using BeatSaberMarkupLanguage;
using Zenject;

namespace BSBRLeaderboard.Features.Leaderboards.Addons {

    /// <summary>
    /// Registra os tags/handlers customizados do leaderboard no BSMLParser
    /// (uma única vez no load do menu). Port do AddonAdder do AccSaber.
    /// </summary>
    internal class BSBRListAdder : IInitializable {

        private static bool _inited;

        public void Initialize() {
            if (_inited) {
                return;
            }
            _inited = true;

#if V129
            // BSML 1.6.10: PersistentSingleton<BSMLParser> → instance (minúsculo).
            // BSML 1.12+: property estática Instance.
            BSMLParser parser = BSMLParser.instance;
#else
            BSMLParser parser = BSMLParser.Instance;
#endif

            parser.RegisterTag(new BSBRListTag());
            parser.RegisterTypeHandler(new BSBRCellListTableDataHandler());

            Plugin.Log?.Debug("BSBR BSML addons registrados.");
        }
    }
}
