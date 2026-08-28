"""
Métricas físicas de dificuldade — porte direto de references/BSStarAnalyzer/analyzer.py.

Preserva EXATAMENTE as janelas e decaimentos da referência:
- Strain com decay exponencial DECAY_RATE = 2.0 por segundo.
- Peak NPS em janela deslizante de 1 segundo (window_size = bpm / 60).
- weighted_peak_sum: média do top-20 das densidades de janela.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from .parser.beatmap import Beatmap

DIR_TO_ANGLE: Dict[int, float] = {
    0: 180.0,
    1: 0.0,
    2: 270.0,
    3: 90.0,
    4: 225.0,
    5: 135.0,
    6: 315.0,
    7: 45.0,
    8: -1.0,  # dot note
}

DECAY_RATE = 2.0


def _grid_dist(n1, n2) -> float:
    dx, dy = n1.x - n2.x, n1.y - n2.y
    return math.sqrt(dx * dx + dy * dy)


def _angle_diff(a1: float, a2: float) -> float:
    if a1 < 0 or a2 < 0:
        return 0.0
    diff = abs(a1 - a2) % 360.0
    return min(diff, 360.0 - diff)


def compute_strain_curve(hand_notes, bpm: float) -> List[float]:
    if len(hand_notes) < 2:
        return []
    curve = []
    current = 0.0
    for i in range(1, len(hand_notes)):
        prev, curr = hand_notes[i - 1], hand_notes[i]
        beat_diff = curr.b - prev.b
        time_diff = max((beat_diff / bpm) * 60, 0.001) if bpm > 0 else 0.001
        current *= math.exp(-DECAY_RATE * time_diff)
        dist = _grid_dist(prev, curr)
        a1 = DIR_TO_ANGLE.get(int(prev.d), -1.0)
        a2 = DIR_TO_ANGLE.get(int(curr.d), -1.0)
        deviation = abs(180.0 - _angle_diff(a1, a2))
        speed_pressure = 1.0 / (time_diff + 0.05)
        instant = (dist * 1.2 + (deviation / 180.0) * 0.8) * speed_pressure
        current += instant
        curve.append(current)
    return curve


def peak_stats(curve: List[float], top_n: int = 10):
    if not curve:
        return 0.0, 0.0
    sorted_vals = sorted(curve, reverse=True)
    peak_avg = sum(sorted_vals[:top_n]) / min(top_n, len(sorted_vals))
    mean = sum(curve) / len(curve)
    variance = sum((v - mean) ** 2 for v in curve) / len(curve)
    return peak_avg, math.sqrt(variance)


def _analyze_hand_legacy(hand_notes, bpm: float):
    if len(hand_notes) < 2:
        return 0.0, 0.0, 0.0
    total_dist = total_ang = streams = 0
    for i in range(1, len(hand_notes)):
        prev, curr = hand_notes[i - 1], hand_notes[i]
        beat_diff = curr.b - prev.b
        time_diff = max((beat_diff / bpm) * 60, 0.001)
        weight = 1 / (time_diff + 0.05)
        total_dist += _grid_dist(prev, curr) * weight
        a1 = DIR_TO_ANGLE.get(int(prev.d), -1.0)
        a2 = DIR_TO_ANGLE.get(int(curr.d), -1.0)
        ad = _angle_diff(a1, a2)
        total_ang += (abs(180.0 - ad) * weight) / 180.0
        if beat_diff <= 0.25:
            streams += 1
    n = len(hand_notes)
    return total_dist / n, total_ang / n, streams / n


def compute_physical_features(beatmap: Beatmap, bpm: float) -> Dict[str, Any]:
    """
    Calcula todas as features físicas de uma dificuldade parseada.
    Retorna dict com as mesmas chaves da referência (exceto pat_*).
    """
    notes = beatmap.notes
    bombs = beatmap.bombs
    obstacles = beatmap.obstacles
    version = beatmap.version

    if not notes:
        raise ValueError("Mapa sem notas.")

    notes_sorted = sorted(notes, key=lambda n: n.b)
    total_notes = len(notes_sorted)

    last_beat = notes_sorted[-1].b
    duration_seconds = (last_beat / bpm) * 60.0 if bpm > 0 else 0.0
    if duration_seconds == 0:
        raise ValueError("Duração inválida (bpm <= 0 ou mapa vazio).")

    avg_nps = total_notes / duration_seconds

    # Peak NPS: janela deslizante de 1 segundo sobre beats
    beats_per_second = bpm / 60.0
    window_size = beats_per_second
    left_idx = 0
    peak_nps = 0
    window_densities = []
    for right_idx in range(total_notes):
        while notes_sorted[right_idx].b - notes_sorted[left_idx].b > window_size:
            left_idx += 1
        count = right_idx - left_idx + 1
        peak_nps = max(peak_nps, count)
        window_densities.append(count)

    top20 = sorted(window_densities, reverse=True)[:20]
    weighted_peak_sum = sum(top20) / len(top20) if top20 else 0.0

    left_notes = [n for n in notes_sorted if int(n.c) == 0]
    right_notes = [n for n in notes_sorted if int(n.c) == 1]

    l_dist, l_ang, l_stream = _analyze_hand_legacy(left_notes, bpm)
    r_dist, r_ang, r_stream = _analyze_hand_legacy(right_notes, bpm)

    complexity_score = (l_dist + r_dist) / 2
    angle_strain = (l_ang + r_ang) / 2
    stream_ratio = (l_stream + r_stream) / 2

    l_curve = compute_strain_curve(left_notes, bpm)
    r_curve = compute_strain_curve(right_notes, bpm)
    l_peak, l_vol = peak_stats(l_curve)
    r_peak, r_vol = peak_stats(r_curve)
    peak_strain = (l_peak + r_peak) / 2
    strain_volatility = (l_vol + r_vol) / 2

    center_notes = sum(1 for n in notes_sorted if n.x in (1, 2) and n.y in (1, 2))
    vision_block_ratio = center_notes / total_notes

    alternation = sum(
        1 for i in range(1, total_notes) if int(notes_sorted[i].c) != int(notes_sorted[i - 1].c)
    )
    alternation_ratio = alternation / total_notes

    peak_ratio = peak_nps / avg_nps if avg_nps > 0 else 0.0
    effective_nps = avg_nps / (bpm / 60.0) if bpm > 0 else 0.0
    tech_density = angle_strain * avg_nps

    return {
        "note_count": total_notes,
        "duration_seconds": round(duration_seconds, 2),
        "nps": round(avg_nps, 2),
        "peak_nps": round(float(peak_nps), 2),
        "weighted_peak_sum": round(weighted_peak_sum, 2),
        "effective_nps": round(effective_nps, 2),
        "peak_ratio": round(peak_ratio, 2),
        "complexity_score": round(complexity_score, 2),
        "angle_strain": round(angle_strain, 2),
        "tech_density": round(tech_density, 2),
        "stream_ratio": round(stream_ratio, 2),
        "alternation_ratio": round(alternation_ratio, 2),
        "vision_block_ratio": round(vision_block_ratio, 2),
        "peak_strain": round(peak_strain, 4),
        "strain_volatility": round(strain_volatility, 4),
        "map_version": version,
        "bomb_count": len(bombs),
        "obstacle_count": len(obstacles),
        # Brutos usados pelo orchestrator/substars
        "_bpm": bpm,
    }
