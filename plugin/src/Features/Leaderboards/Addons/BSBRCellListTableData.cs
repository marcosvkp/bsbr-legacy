using BeatSaberMarkupLanguage;
using IPA.Utilities.Async;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using UnityEngine;
using UnityEngine.UI;

// (Canvas.ForceUpdateCanvases vem de UnityEngine)

namespace BSBRLeaderboard.Features.Leaderboards.Addons {

    /// <summary>
    /// Lista vertical de células BSML customizadas (port do MyCustomCellListTableData
    /// do AccSaber, SEM pager/PageUpdater/AsyncLock/ObjectCacher — o BSBR pagina via
    /// offset no backend e os reloads são sequenciais). Substitui o &lt;leaderboard&gt;
    /// nativo: células são templates BSML (rich text nativo, sem loading nativo).
    /// </summary>
    internal class BSBRCellListTableData : MonoBehaviour {

        private readonly List<string> cellTemplates = new();
        private readonly List<float> cellSizes = new();
        private readonly List<BSBRCell> dataSources = new();

        private readonly object templateLocker = new();
        private int prefNumberOfCells = 10;
        private float mainCellSize = 5.5f;

        private List<IBSBRCellDataSource> data = new();
        public List<IBSBRCellDataSource> Data {
            get => data;
            set {
                data = value;
                // reload automático no setter (mesmo padrão do AccSaber); ReloadTemplates
                // usa objetos Unity → garantir a main thread.
                if (!IPA.Utilities.UnityGame.OnMainThread) {
                    _ = IPA.Utilities.Async.UnityMainThreadTaskScheduler.Factory.StartNew(ReloadTemplates);
                } else {
                    ReloadTemplates();
                }
            }
        }
        public int PrefNumberOfCells { get => prefNumberOfCells; set => prefNumberOfCells = value; }
        public float MainCellSize { get => mainCellSize; set => mainCellSize = value; }

        public int NumberOfCells() => Math.Min(prefNumberOfCells, Data.Count);

        public float CellSize(int idx) => cellSizes.Count > 0 ? cellSizes[Data[idx].TemplateId] : mainCellSize;

        public BSBRCell CellForIdx(int idx) {
            var go = new GameObject("Cell", typeof(RectTransform));
            var cell = go.AddComponent<BSBRCell>();
            cell.name = "BSBRTableCell";

            int tempId = Data[idx].TemplateId;
#if V129
            cell.ParserParams = BSMLParser.instance.Parse(cellTemplates[tempId], cell.gameObject, Data[idx]);
#else
            cell.ParserParams = BSMLParser.Instance.Parse(cellTemplates[tempId], cell.gameObject, Data[idx]);
#endif
            cell.SetupPostParse();

            foreach (Graphic g in cell.GetComponentsInChildren<Graphic>(true)) {
                g.raycastTarget = false;
            }

            cell.GetComponent<LayoutElement>().preferredHeight = cellSizes[tempId];
            return cell;
        }

        public void ReloadTemplates() {
            lock (templateLocker) {
                cellTemplates.Clear();
                cellSizes.Clear();

                foreach (BSBRCell cell in dataSources) {
                    Destroy(cell.gameObject);
                }
                dataSources.Clear();

                var paths = new Dictionary<string, int>();
                Assembly current = Assembly.GetExecutingAssembly();
                int cellId = 0;
                float cellHeight = 0f;

                List<IBSBRCellDataSource> rows = Data.Where(cell => cell is not null).Take(prefNumberOfCells).ToList();

                foreach (IBSBRCellDataSource cell in rows) {
                    if (paths.TryGetValue(cell.TemplatePath, out int id)) {
                        cell.TemplateId = id;
                    } else {
                        id = paths.Count;
                        paths.Add(cell.TemplatePath, id);
                        cellTemplates.Add(cell.TemplatePath[0] == '<'
                            ? cell.TemplatePath
                            : Utilities.GetResourceContent(current, cell.TemplatePath));
                        cellSizes.Add(cell.CellSize);
                        cell.TemplateId = id;
                    }

                    BSBRCell customCell = CellForIdx(cellId++);
                    customCell.transform.SetParent(transform, false);
                    cellHeight += cellSizes[id];
                    dataSources.Add(customCell);
                }

                LayoutElement le = gameObject.GetComponent<LayoutElement>();
                le.preferredHeight = cellHeight;
                le.minHeight = cellHeight;

                Canvas.ForceUpdateCanvases();
            }
        }
    }
}
