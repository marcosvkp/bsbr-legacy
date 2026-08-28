"""
Orquestrador: analyze_map(source) → MapAnalysis.

`source` é o id ou hash do BeatSaver. Baixa o mapa, lê o Info.dat e analisa
todas as dificuldades da characteristic Standard.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .beatsaver import (
    BeatSaverError,
    download_map_zip,
    extract_to_tempdir,
    fetch_map_metadata,
    find_info_dat,
    load_json_file,
    map_name_mapper,
)
from .features import compute_physical_features
from .parser.beatmap import Beatmap
from .patterns import analyze_patterns, classify_map_style
from .beatsaver import map_hash
from .substars import compute_substars


@dataclass
class DifficultyAnalysis:
    characteristic: str
    difficulty: str
    njs: float
    notes: int
    nps: float
    total_stars: float  # modelo treinado quando disponível, senão heurística
    acc_stars: float
    tech_stars: float
    speed_stars: float  # soma == total_stars
    share_acc: float
    share_tech: float
    share_speed: float  # soma == 1.0
    style_tags: List[str]
    features: Dict[str, float] = field(default_factory=dict)
    stars_source: str = "heuristic"  # "model" | "heuristic"


@dataclass
class MapAnalysis:
    map_id: str
    name: str
    mapper: str
    bpm: float
    difficulties: List[DifficultyAnalysis]
    hash: str = ""


def _get(info: Dict[str, Any], v2_key: str, *v3_keys: str, default: Any = None) -> Any:
    if v2_key in info:
        return info[v2_key]
    for key in v3_keys:
        if key in info:
            return info[key]
    return default


def read_info_dat(map_dir: str) -> Dict[str, Any]:
    """Lê Info.dat/info.dat de uma pasta de mapa."""
    path = find_info_dat(map_dir)
    return load_json_file(path)


def iter_standard_difficulties(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Lista normalizada das dificuldades Standard do Info.dat.
    Suporta V2 (_difficultyBeatmapSets), V3 (difficultyBeatmapSets) e
    V4 (difficultyBeatmaps).
    """
    diffs: List[Dict[str, Any]] = []

    # V4
    for beatmap_set in info.get("difficultyBeatmaps", []):
        if beatmap_set.get("characteristic") not in (None, "Standard"):
            continue
        diffs.append(
            {
                "filename": beatmap_set.get("beatmapDataFilename", ""),
                "difficulty": beatmap_set.get("difficulty", "Unknown"),
                "njs": float(beatmap_set.get("noteJumpMovementSpeed", 0.0) or 0.0),
            }
        )

    # V2 / V3
    sets_key = "_difficultyBeatmapSets" if "_difficultyBeatmapSets" in info else "difficultyBeatmapSets"
    for beatmap_set in info.get(sets_key, []):
        char_key = (
            "_beatmapCharacteristicName"
            if "_beatmapCharacteristicName" in beatmap_set
            else "beatmapCharacteristicName"
        )
        if beatmap_set.get(char_key) != "Standard":
            continue
        diffs_key = "_difficultyBeatmaps" if "_difficultyBeatmaps" in beatmap_set else "difficultyBeatmaps"
        for diff in beatmap_set.get(diffs_key, []):
            file_key = "_beatmapFilename" if "_beatmapFilename" in diff else "beatmapFilename"
            njs = diff.get("_noteJumpMovementSpeed") or diff.get("noteJumpMovementSpeed") or 0.0
            diffs.append(
                {
                    "filename": diff.get(file_key, ""),
                    "difficulty": diff.get("_difficulty", diff.get("difficulty", "Unknown")),
                    "njs": float(njs),
                }
            )
    return diffs


def parse_difficulty_file(map_dir: str, filename: str) -> tuple[Beatmap, Dict[str, Any]]:
    """Carrega e faz parse do JSON de uma dificuldade."""
    path = os.path.join(map_dir, filename)
    raw_data = load_json_file(path)
    beatmap = Beatmap()
    beatmap.parse_json(raw_data)
    return beatmap, raw_data


def analyze_difficulty(
    map_dir: str,
    filename: str,
    bpm: float,
    characteristic: str = "Standard",
    difficulty_name: str = "Unknown",
    njs: float = 0.0,
) -> Optional[DifficultyAnalysis]:
    """
    Análise completa de uma dificuldade: features físicas + padrões +
    heurística de stars + sub-stars + estilo.
    Retorna None se a dificuldade não puder ser analisada (sem notas etc.).
    """
    try:
        beatmap, raw_data = parse_difficulty_file(map_dir, filename)
        features = compute_physical_features(beatmap, bpm)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None

    duration = features["duration_seconds"]
    version = features["map_version"]
    pattern_metrics = analyze_patterns(
        notes=beatmap.notes,
        bombs=beatmap.bombs,
        obstacles=beatmap.obstacles,
        bpm=bpm,
        duration_seconds=duration,
        version=version,
        raw_data=raw_data,
    )
    all_features: Dict[str, Any] = {
        **{k: v for k, v in features.items() if k != "_bpm"},
        "bpm": float(bpm),
        **pattern_metrics,
    }

    style_tags = classify_map_style(pattern_metrics)

    # Modelo treinado quando existir; senão heurística de fallback
    from .trainer import predict_with_fallback  # import tardio: pandas/sklearn são pesados

    total_stars, stars_source = predict_with_fallback(all_features)
    substars = compute_substars(total_stars, all_features)

    return DifficultyAnalysis(
        characteristic=characteristic,
        difficulty=difficulty_name,
        njs=float(njs),
        notes=int(features["note_count"]),
        nps=float(features["nps"]),
        total_stars=total_stars,
        acc_stars=substars["acc_stars"],
        tech_stars=substars["tech_stars"],
        speed_stars=substars["speed_stars"],
        share_acc=substars["share_acc"],
        share_tech=substars["share_tech"],
        share_speed=substars["share_speed"],
        style_tags=style_tags,
        features={k: float(v) for k, v in all_features.items() if isinstance(v, (int, float))},
        stars_source=stars_source,
    )


def analyze_map_folder(map_dir: str) -> MapAnalysis:
    """Analisa um mapa já extraído em disco (id sintético 'local')."""
    info = read_info_dat(map_dir)
    bpm = _get(info, "_beatsPerMinute", "beatsPerMinute", default=None)
    if bpm is None:
        bpm = (_get(info, "_songName", default={}) and 0) or 0
    bpm = float(bpm or 0.0)

    name = _get(info, "_songName", "songName", default="Unknown")
    mapper = _get(info, "_levelAuthorName", "levelAuthorName", default="Unknown")

    difficulties: List[DifficultyAnalysis] = []
    for diff in iter_standard_difficulties(info):
        result = analyze_difficulty(
            map_dir,
            diff["filename"],
            bpm=bpm,
            characteristic="Standard",
            difficulty_name=diff["difficulty"],
            njs=diff["njs"],
        )
        if result is not None:
            difficulties.append(result)

    return MapAnalysis(
        map_id="local",
        name=name,
        mapper=mapper,
        bpm=bpm,
        difficulties=difficulties,
    )


def analyze_map(source: str) -> MapAnalysis:
    """
    Analisa um mapa do BeatSaver ponta a ponta.

    `source`: id numérico do mapa ou hash (40 hex).
    Baixa metadados + zip, extrai em tempdir, analisa todas as dificuldades
    Standard e limpa o tempdir ao final.
    """
    metadata = fetch_map_metadata(source)
    name, mapper = map_name_mapper(metadata)
    zip_bytes = download_map_zip(metadata)
    map_dir = extract_to_tempdir(zip_bytes)
    try:
        analysis = analyze_map_folder(map_dir)
        analysis.map_id = source
        analysis.hash = map_hash(metadata)
        if name and name != "Unknown":
            analysis.name = name
        if mapper and mapper != "Unknown":
            analysis.mapper = mapper
        # BPM dos metadados caso o Info.dat não tenha
        if analysis.bpm <= 0:
            meta_bpm = (metadata.get("metadata") or {}).get("bpm")
            if meta_bpm:
                analysis.bpm = float(meta_bpm)
                for d in analysis.difficulties:
                    reanalysis = analyze_difficulty(
                        map_dir,
                        next(
                            dd["filename"]
                            for dd in iter_standard_difficulties(read_info_dat(map_dir))
                            if dd["difficulty"] == d.difficulty
                        ),
                        bpm=analysis.bpm,
                        difficulty_name=d.difficulty,
                        njs=d.njs,
                    )
                    if reanalysis is not None:
                        idx = analysis.difficulties.index(d)
                        analysis.difficulties[idx] = reanalysis
        return analysis
    finally:
        shutil.rmtree(map_dir, ignore_errors=True)


__all__ = [
    "MapAnalysis",
    "DifficultyAnalysis",
    "analyze_map",
    "analyze_map_folder",
    "analyze_difficulty",
    "iter_standard_difficulties",
    "read_info_dat",
    "parse_difficulty_file",
    "BeatSaverError",
]
