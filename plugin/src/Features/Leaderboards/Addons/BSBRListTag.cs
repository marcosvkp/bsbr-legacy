using BeatSaberMarkupLanguage.Tags;
using BSBRLeaderboard.Features.Leaderboards.Addons;
using UnityEngine;
using UnityEngine.UI;

namespace BSBRLeaderboard.Features.Leaderboards.Addons {

    /// <summary>Tag BSML `bsbr-list` — lista vertical de células customizadas (port do MyCustomList do AccSaber).</summary>
    internal class BSBRListTag : BSMLTag {

        public override string[] Aliases => new[] { "bsbr-list" };

        public override bool AddChildren => false;

        public override GameObject CreateObject(Transform parent) {
            var gameObject = new GameObject("BSBRList");
            gameObject.transform.SetParent(parent, false);
            gameObject.AddComponent<VerticalLayoutGroup>().childForceExpandHeight = false;

            var csf = gameObject.AddComponent<ContentSizeFitter>();
            csf.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            csf.horizontalFit = ContentSizeFitter.FitMode.PreferredSize;

            var rt = (gameObject.transform as RectTransform)!;
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.sizeDelta = Vector2.zero;

            gameObject.AddComponent<LayoutElement>();
            gameObject.AddComponent<BSBRCellListTableData>();
            return gameObject;
        }
    }
}
