using BSBRLeaderboard.Features.Leaderboards.Adapters;
using BSBRLeaderboard.Features.Leaderboards.Services;
using Zenject;

namespace BSBRLeaderboard.Features.Leaderboards {

    internal class LeaderboardFeatureInstaller : Installer {

        public override void InstallBindings() {
            Container.Bind<BSBRLeaderboardService>().AsSingle();
            Container.Bind<BSBRLeaderboardViewController>()
                .FromNewComponentAsViewController()
                .AsSingle();
            Container.Bind<BSBRMapInfoViewController>()
                .FromNewComponentAsViewController()
                .AsSingle();
            // NonLazy: cria o adapter no load do menu p/ registrar a tab no
            // CustomLeaderboardManager (senão nada o resolve e o Initialize() nunca roda)
            Container.BindInterfacesAndSelfTo<BSBRCustomLeaderboard>().AsSingle().NonLazy();
        }
    }
}
