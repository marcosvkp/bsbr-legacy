"""Builders de charts sintéticos V2/V3 compartilhados pelos testes."""

from __future__ import annotations

from typing import Dict, List, Tuple

NoteSpec = Tuple[float, int, int, int, int]  # (b, x, y, c, d)


def to_v2(notes: List[NoteSpec], bombs: List[NoteSpec] = None, obstacles: List[Dict] = None) -> Dict:
    return {
        "_version": "2.2.0",
        "_notes": [
            {
                "_time": b,
                "_lineIndex": x,
                "_lineLayer": y,
                "_type": c,
                "_cutDirection": d,
            }
            for (b, x, y, c, d) in notes + (bombs or [])
        ],
        "_obstacles": obstacles or [],
    }


def to_v3(
    notes: List[NoteSpec],
    bombs: List[NoteSpec] = None,
    obstacles: List[Dict] = None,
    arcs: List[Dict] = None,
    chains: List[Dict] = None,
) -> Dict:
    data = {
        "version": "3.0.0",
        "colorNotes": [
            {"b": b, "x": x, "y": y, "c": c, "d": d, "a": 0}
            for (b, x, y, c, d) in notes
        ],
        "bombNotes": [
            {"b": b, "x": x, "y": y}
            for (b, x, y, c, d) in (bombs or [])
        ],
        "obstacles": [
            {
                "b": o["_time"],
                "x": o["_lineIndex"],
                "y": 0 if o["_type"] != 2 else 2,
                "d": o["_duration"],
                "w": o["_width"],
                "h": 5 if o["_type"] == 0 else (2 if o["_type"] == 1 else 1),
            }
            for o in (obstacles or [])
        ],
    }
    if arcs:
        data["sliders"] = arcs
    if chains:
        data["burstSliders"] = chains
    return data


def tech_note_specs() -> List[NoteSpec]:
    """
    Mapa tech-heavy: diagonais em todas as notas (pat_tech_ratio → 1),
    paridade quebrada na maior parte das transições e crossovers
    frequentes (mão esquerda em colunas ≥ 2, direita em colunas ≤ 1).
    """
    # Diagonais: UP_LEFT=4, UP_RIGHT=5, DOWN_LEFT=6, DOWN_RIGHT=7
    diagonals = [4, 5, 6, 7]
    notes: List[NoteSpec] = []
    beat = 0.0
    for i in range(200):
        hand = i % 2
        if hand == 0:
            x = 2 if (i // 2) % 2 == 0 else 0
        else:
            x = 1 if (i // 2) % 2 == 0 else 3
        y = (i // 4) % 3
        d = diagonals[i % 4]
        notes.append((beat, x, y, hand, d))
        beat += 0.5
    return notes


def make_tech_map_v2() -> Dict:
    return to_v2(tech_note_specs())


def make_tech_map_v3() -> Dict:
    """Mesmo mapa tech-heavy no formato V3."""
    return to_v3(tech_note_specs())


def make_speed_map_v2() -> Dict:
    """
    Mapa linear de NPS altíssimo: stream contínuo alternando mãos em grade
    de 1/8 de beat, tudo corte DOWN (linear), lanes externas (sem vision
    block), mesma altura (sem strain geométrico).
    """
    notes: List[NoteSpec] = []
    beat = 0.0
    for i in range(400):
        hand = i % 2
        x = 0 if hand == 0 else 3
        notes.append((beat, x, 1, hand, 1))  # DOWN, linha do meio
        beat += 0.125
    return to_v2(notes)


TECH_INFO_V2 = {
    "_beatsPerMinute": 120.0,
    "_songName": "Tech Test",
    "_levelAuthorName": "MapperA",
    "_difficultyBeatmapSets": [
        {
            "_beatmapCharacteristicName": "Standard",
            "_difficultyBeatmaps": [
                {
                    "_difficulty": "ExpertPlus",
                    "_difficultyRank": 9,
                    "_beatmapFilename": "ExpertPlus.dat",
                    "_noteJumpMovementSpeed": 18.0,
                }
            ],
        },
        {
            "_beatmapCharacteristicName": "Lightshow",
            "_difficultyBeatmaps": [],
        },
    ],
}

SPEED_INFO_V2 = {
    "_beatsPerMinute": 128.0,
    "_songName": "Speed Test",
    "_levelAuthorName": "MapperB",
    "_difficultyBeatmapSets": [
        {
            "_beatmapCharacteristicName": "Standard",
            "_difficultyBeatmaps": [
                {
                    "_difficulty": "Expert",
                    "_difficultyRank": 7,
                    "_beatmapFilename": "Expert.dat",
                    "_noteJumpMovementSpeed": 20.0,
                }
            ],
        },
    ],
}
