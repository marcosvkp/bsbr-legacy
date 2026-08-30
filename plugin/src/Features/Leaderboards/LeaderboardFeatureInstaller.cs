using BSBRLeaderboard.Features.Leaderboards.Adapters;
using BSBRLeaderboard.Features.Leaderboards.Addons;
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
            // registra os tags/handlers customizados (bsbr-list) no BSMLParser;
            // BindInterfacesAndSelfTo é OBRIGATÓRIO p/ o Zenject registrar IInitializable
            // e chamar Initialize() no load do menu (Bind<> simples não dispara)
            Container.BindInterfacesAndSelfTo<BSBRListAdder>().AsSingle().NonLazy();
            // NonLazy: cria o adapter no load do menu p/ registrar a tab no
            // CustomLeaderboardManager (senão nada o resolve e o Initialize() nunca roda)
            Container.BindInterfacesAndSelfTo<BSBRCustomLeaderboard>().AsSingle().NonLazy();
        }
    }
}
