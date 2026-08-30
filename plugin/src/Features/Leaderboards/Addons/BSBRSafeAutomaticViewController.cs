using BeatSaberMarkupLanguage.ViewControllers;
using IPA.Utilities;
using IPA.Utilities.Async;
using System.Runtime.CompilerServices;

namespace BSBRLeaderboard.Features.Leaderboards.Addons {

    /// <summary>
    /// BSMLAutomaticViewController com NotifyPropertyChanged seguro em relação à
    /// thread: se a atualização vier de fora da main thread, o notify é re-enfileirado
    /// via UnityMainThreadTaskScheduler (mesmo padrão do BSMLSafeAutomaticViewController
    /// do AccSaber, sem precisar de um MonoBehaviour dispatcher).
    /// </summary>
    internal class BSBRSafeAutomaticViewController : BSMLAutomaticViewController {

        protected new void NotifyPropertyChanged([CallerMemberName] string propertyName = "") {
            try {
                if (!UnityGame.OnMainThread) {
                    UnityMainThreadTaskScheduler.Factory.StartNew(() => base.NotifyPropertyChanged(propertyName));
                } else {
                    base.NotifyPropertyChanged(propertyName);
                }
            } catch (System.Exception ex) {
                Plugin.Log?.Warn($"Falha no NotifyPropertyChanged({propertyName}): {ex.Message}");
            }
        }
    }
}
