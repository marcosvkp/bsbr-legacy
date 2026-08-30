using System;
using System.IO;
using IPA.Utilities;
using Newtonsoft.Json;

namespace BSBRLeaderboard.Core {

    /// <summary>Config do plugin — UserData/BSBRLeaderboard.json.</summary>
    internal class BSBRConfig {

        private const string FileName = "BSBRLeaderboard.json";

        internal static BSBRConfig Instance { get; private set; } = new BSBRConfig();

        [JsonProperty("enabled")]
        internal bool Enabled { get; set; } = true;

        [JsonProperty("apiBaseUrl")]
        internal string ApiBaseUrl { get; set; } = "https://bsbr.pro/api/v1";

        private string FilePath =>
            Path.Combine(UnityGame.UserDataPath, FileName);

        internal static BSBRConfig Load() {
            var cfg = new BSBRConfig();
            try {
                if (File.Exists(cfg.FilePath)) {
                    var json = File.ReadAllText(cfg.FilePath);
                    Instance = JsonConvert.DeserializeObject<BSBRConfig>(json) ?? cfg;
                } else {
                    Instance = cfg;
                    cfg.Save();
                }
            } catch (Exception ex) {
                Plugin.Log?.Error($"Falha ao carregar config: {ex}");
                Instance = cfg;
            }
            return Instance;
        }

        internal void Save() {
            try {
                var dir = Path.GetDirectoryName(FilePath);
                if (!string.IsNullOrEmpty(dir)) {
                    Directory.CreateDirectory(dir);
                }
                File.WriteAllText(FilePath, JsonConvert.SerializeObject(this, Formatting.Indented));
            } catch (Exception ex) {
                Plugin.Log?.Error($"Falha ao salvar config: {ex}");
            }
        }
    }
}
