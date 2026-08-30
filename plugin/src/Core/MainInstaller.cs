using Zenject;

namespace BSBRLeaderboard.Core {

    internal class MainInstaller : Installer {

        public override void InstallBindings() {
            Container.Install<BSBRLeaderboard.Features.Leaderboards.LeaderboardFeatureInstaller>();
        }
    }
}
