"""Parser V2/V3: normalização unificada e detecção de versão."""

import pytest

from bsbr_analyzer.parser import Beatmap, NoteColor, NoteCutDirection, detect_version
from conftest import make_tech_map_v2, to_v2, to_v3


def test_detect_version():
    assert detect_version({"_version": "2.2.0"}) == "2.2.0"
    assert detect_version({"version": "3.3.0"}) == "3.3.0"
    with pytest.raises(ValueError):
        detect_version({})


def test_unknown_format_rejected():
    with pytest.raises(ValueError):
        Beatmap().parse_json({"foo": 1})


def test_v2_notes_and_bombs_split():
    chart = to_v2(
        notes=[(0.0, 0, 0, 0, 1), (1.0, 3, 2, 1, 0)],
        bombs=[(2.0, 1, 1, 3, 0)],
    )
    bm = Beatmap()
    bm.parse_json(chart)
    assert bm.version == "2.2.0"
    assert len(bm.notes) == 2
    assert len(bm.bombs) == 1
    assert all(n.c == NoteColor.BOMB for n in bm.bombs)


def test_v3_notes_and_bombs_split():
    chart = to_v3(
        notes=[(0.0, 0, 0, 0, 1), (1.0, 3, 2, 1, 0)],
        bombs=[(2.0, 1, 1, 3, 8)],
        arcs=[{"b": 4.0}],
        chains=[{"b": 5.0}],
    )
    bm = Beatmap()
    bm.parse_json(chart)
    assert bm.version == "3.0.0"
    assert len(bm.notes) == 2
    assert len(bm.bombs) == 1
    assert bm.notes[0].a == 0
    specs = [
        (b, x, y % 3, c, d)
        for b, (x, y, c, d) in enumerate(
            [(0, 0, 0, 0), (3, 2, 1, 0), (1, 1, 0, 1), (2, 0, 1, 1)]
        )
    ]
    v2_bm, v3_bm = Beatmap(), Beatmap()
    v2_bm.parse_json(to_v2(specs))
    v3_bm.parse_json(to_v3(specs))

    assert [(n.b, n.x, n.y, int(n.c), int(n.d), n.a) for n in v2_bm.notes] == [
        (n.b, n.x, n.y, int(n.c), int(n.d), n.a) for n in v3_bm.notes
    ]


def test_v2_obstacle_type_mapping():
    chart = {
        "_version": "2.0.0",
        "_notes": [],
        "_obstacles": [
            {"_time": 0, "_lineIndex": 0, "_type": 0, "_duration": 1, "_width": 1},
            {"_time": 2, "_lineIndex": 2, "_type": 1, "_duration": 1, "_width": 1},
            {"_time": 4, "_lineIndex": 3, "_type": 2, "_duration": 1, "_width": 1},
        ],
    }
    bm = Beatmap()
    bm.parse_json(chart)
    assert [(o.y, o.h) for o in bm.obstacles] == [(0, 3), (0, 2), (2, 1)]


def test_cut_directions_preserved():
    specs = [(i * 0.5, i % 4, i % 3, i % 2, i % 9) for i in range(9)]
    bm = Beatmap()
    bm.parse_json(to_v2(specs))
    assert [int(n.d) for n in sorted(bm.notes, key=lambda n: n.b)] == list(range(9))
    assert NoteCutDirection.ANY == 8
