using Zenject;

namespace BSBRLeaderboard.Core {

    internal class AppInstaller : Installer {

        public override void InstallBindings() {
            Container.Bind<BSBRConfig>().FromInstance(BSBRConfig.Instance).AsSingle();
        }
    }
}
