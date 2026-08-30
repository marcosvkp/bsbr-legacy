using BeatSaberMarkupLanguage.Parser;
using HMUI;
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace BSBRLeaderboard.Features.Leaderboards.Addons {

    /// <summary>
    /// Célula do leaderboard customizado (port do MyCustomCell do AccSaber, sem
    /// selected/hovered tags — as células não são clicáveis nesta fase).
    /// </summary>
    internal class BSBRCell : MonoBehaviour {

        public BSMLParserParams ParserParams { get; internal set; }

        /// <summary>Reaplica o estado visual da célula (no-op: não há seleção nesta fase).</summary>
        public virtual void RefreshVisuals() {
        }

        protected internal void SetupPostParse() {
            if (ParserParams is null) {
                throw new InvalidOperationException("ParserParams cannot be null when calling SetupPostParse.");
            }
        }

        private void Awake() {
            RectTransform rt = (gameObject.transform as RectTransform)!;
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;
            rt.anchorMin = new Vector2(0f, 1f);
            rt.anchorMax = new Vector2(1f, 1f);
            rt.pivot = new Vector2(0.5f, 1f);
            rt.sizeDelta = new Vector2(0f, 8.5f);
            gameObject.AddComponent<LayoutElement>();
            gameObject.AddComponent<Touchable>();
        }
    }
}
