using BSBRLeaderboard.Core;
using BSBRLeaderboard.Features.Leaderboards;
using IPA;
using IPA.Logging;
using SiraUtil.Zenject;
using Zenject;

namespace BSBRLeaderboard {

    [Plugin(RuntimeOptions.DynamicInit)]
    public class Plugin {

        internal static Logger Log { get; private set; }
        internal static Plugin Instance { get; private set; }
        internal static BSBRConfig Config { get; private set; }

        private readonly Zenjector _zenjector;

        [Init]
        public Plugin(Logger logger, Zenjector zenjector) {
            Log = logger;
            Instance = this;
            _zenjector = zenjector;

            // carrega o config antes dos installers (AppInstaller liga BSBRConfig.Instance)
            Config = BSBRConfig.Load();

            zenjector.UseLogger(logger);
            zenjector.UseHttpService(SiraUtil.Web.HttpServiceType.UnityWebRequests);
            zenjector.UseAutoBinder();

            zenjector.Install<AppInstaller>(Location.App);
            zenjector.Install<MainInstaller>(Location.Menu);
        }

        [OnDisable]
        public void OnDisable() {
            Config?.Save();
        }
    }
}
