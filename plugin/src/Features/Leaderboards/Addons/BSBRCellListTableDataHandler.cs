using BeatSaberMarkupLanguage;
using BeatSaberMarkupLanguage.Parser;
using BeatSaberMarkupLanguage.TypeHandlers;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace BSBRLeaderboard.Features.Leaderboards.Addons {

    /// <summary>
    /// Handler do `bsbr-list` (port do MyCustomCellListTableDataHandler do AccSaber,
    /// SEM select-cell/highlight-cell/pager — células não-clicáveis nesta fase).
    /// </summary>
    [ComponentHandler(typeof(BSBRCellListTableData))]
    internal class BSBRCellListTableDataHandler : TypeHandler {

        public override Dictionary<string, string[]> Props => new() {
            { "id", new[] { "id" } },
            { "data", new[] { "contents", "data" } },
            { "cellNumber", new[] { "pref-number-cells", "cells", "number-of-cells", "visible-cells" } },
            { "cellSize", new[] { "main-cell-size", "cell-size" } }
        };

        public override void HandleType(BSMLParser.ComponentTypeWithData componentType, BSMLParserParams parserParams) {
            Component component = componentType.Component;
            Dictionary<string, string> data = componentType.Data;
            Dictionary<string, BSMLValue> values = parserParams.Values;

            var componentData = (component as BSBRCellListTableData)!;

            if (data.TryGetValue("data", out string dataStr)) {
                if (!values.TryGetValue(dataStr, out BSMLValue contents)) {
                    throw new Exception($"Value '{dataStr}' not found");
                }

                object maybeCells = contents.GetValue();

                if (maybeCells is not IEnumerable ienum) {
                    throw new Exception($"Value '{dataStr}' is not an IEnumerable and cannot be used as data for bsbr-list.");
                }

                componentData.Data = ConvariantConverter<IBSBRCellDataSource>(ienum).ToList();
            }

            if (data.TryGetValue("cellNumber", out string cellNum)) {
                if (!int.TryParse(cellNum, out int value)) {
                    throw new Exception($"the cell number \"{cellNum}\" cannot be parsed into an int.");
                }

                componentData.PrefNumberOfCells = value;
            }

            if (data.TryGetValue("cellSize", out string cellSize)) {
                if (!float.TryParse(cellSize, out float value)) {
                    throw new Exception($"the cell size \"{cellSize}\" cannot be parsed into a float.");
                }

                componentData.MainCellSize = value;
            }
        }

        internal static IEnumerable<T2> ConvariantConverter<T2>(IEnumerable arr) {
            if (arr is IEnumerable<T2> typedEnumerable) {
                return typedEnumerable;
            }

            Type enumerableInterface = arr.GetType().GetInterfaces()
                .FirstOrDefault(i => i.IsGenericType && i.GetGenericTypeDefinition() == typeof(IEnumerable<>));

            if (enumerableInterface is not null) {
                if (typeof(T2).IsAssignableFrom(enumerableInterface.GetGenericArguments()[0])) {
                    return arr.Cast<T2>();
                }

                throw new Exception(
                    $"Value '{arr}' implements IEnumerable<{enumerableInterface.GetGenericArguments()[0].Name}> which is not assignable to IEnumerable<{typeof(T2)}>.");
            }

            List<T2> list = new();
            foreach (object item in arr) {
                if (item is T2 type2) {
                    list.Add(type2);
                } else {
                    throw new Exception(
                        $"Value '{arr}' contains an element of type {item?.GetType().Name ?? "null"} which does not implement {typeof(T2)}.");
                }
            }
            return list;
        }
    }
}
