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


def test_v3_chains_arcs_parsed():
    """V3: sliders = arcs, burstSliders = chains (nomenclatura BL)."""
    chart = to_v3(
        notes=[(0.0, 0, 0, 0, 1)],
        arcs=[{"b": 1.0, "x": 0, "y": 0, "c": 0, "d": 1, "tb": 2.0, "tx": 3, "ty": 2, "mu": 1.5, "tmu": 1.0, "m": 0}],
        chains=[{"b": 3.0, "x": 1, "y": 1, "c": 1, "d": 0, "tb": 4.0, "tx": 2, "ty": 0, "sc": 8, "s": 1.0}],
    )
    bm = Beatmap()
    bm.parse_json(chart)
    assert len(bm.arcs) == 1
    assert len(bm.chains) == 1
    assert bm.arcs[0].b == 1.0 and bm.arcs[0].multiplier == 1.5
    assert bm.chains[0].b == 3.0 and bm.chains[0].slice_count == 8


def test_v3_bpm_njs_events_parsed():
    """BPM variable e NJS events (V3 bpmEvents/njsEvents)."""
    chart = {
        "version": "3.3.0",
        "colorNotes": [{"b": 0.0, "x": 0, "y": 0, "c": 0, "d": 1, "a": 0}],
        "bpmEvents": [{"b": 0.0, "m": 128.0}, {"b": 8.0, "m": 160.0}],
        "njsEvents": [{"b": 4.0, "d": 2.0, "p": 0, "e": 0}],
    }
    bm = Beatmap()
    bm.parse_json(chart)
    assert len(bm.bpm_events) == 2
    assert len(bm.njs_events) == 1
    assert bm.bpm_events[1].bpm == 160.0
    assert bm.njs_events[0].delta == 2.0


def test_v2_has_no_chains_arcs_events():
    """V2 não tem chains/arcs/bpmEvents — listas vazias."""
    bm = Beatmap()
    bm.parse_json(to_v2([(0.0, 0, 0, 0, 1)]))
    assert bm.chains == [] and bm.arcs == []
    assert bm.bpm_events == [] and bm.njs_events == []


def test_v41_chains_arcs_use_hb_tb_and_tolerate_encoded_color():
    """V4.1: chains/arcs têm hb/tb (não b); chainsData c é codificado.

    Regressão: mapas 1.40+ (ex.: São Paulo - The Weeknd) crashavam com
    KeyError('b')/NoteColor inválido e ficavam sem predição do ML.
    """
    chart = {
        "version": "4.1.0",
        "colorNotes": [{"b": 1.0, "i": 0}],
        "colorNotesData": [{"x": 0, "y": 0, "c": 1, "d": 2, "a": 0}],
        "bombNotes": [{"b": 2.0}],
        "bombNotesData": [{"x": 2}],
        "obstacles": [{"b": 3.0}],
        "obstaclesData": [{"d": 0.5, "w": 1, "h": 5}],
        "chains": [
            {"hb": 4.0, "tb": 4.5, "i": 1},
            {"hb": 6.0, "tb": 6.5, "i": 2},
        ],
        "chainsData": [{"tx": 3, "ty": 2, "c": 6, "s": 0.9}, {"tx": 2, "ty": 2, "c": 12, "s": 1.0}],
        "arcs": [{"hb": 8.0, "tb": 10.0, "ai": 0}],
        "arcsData": [{"m": 1.0, "tm": 0.5}],
    }
    bm = Beatmap()
    bm.parse_json(chart)
    assert len(bm.chains) == 2
    assert bm.chains[0].b == 4.0
    assert bm.chains[1].tail_in_beats == 6.5
    # c codificado (6/12 não são NoteColor válido) não derruba o parse
    assert bm.chains[0].c in (NoteColor.RED, NoteColor.BLUE)
    assert len(bm.arcs) == 1
    assert bm.arcs[0].b == 8.0 and bm.arcs[0].tail_in_beats == 10.0
    assert len(bm.notes) == 1 and len(bm.bombs) == 1
