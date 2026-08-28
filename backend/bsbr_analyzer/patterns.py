"""
Análise de padrões — porte direto de references/BSStarAnalyzer/pattern_analyzer.py.

Todas as features recebem prefixo `pat_` e limiares idênticos à referência.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .parser.enums import NoteCutDirection
from .parser.objects import Note, Obstacle

# ─────────────────────────────────────────────────────────
# Constantes e limiares (idênticos à referência)
# ─────────────────────────────────────────────────────────

SIMULTANEOUS_THRESHOLD_SEC = 0.020  # 20ms
STREAM_BEAT_THRESHOLD = 0.27  # ~1/4 beat + tolerância
DOUBLE_BEAT_THRESHOLD = 0.13  # ~1/8 beat + tolerância
STREAM_MIN_LENGTH = 5

LEFT_CROSSOVER_COL = 2   # ≥ esta coluna = crossover para esquerda (mão 0)
RIGHT_CROSSOVER_COL = 1  # ≤ esta coluna = crossover para direita (mão 1)

GRID_COLS = 4
GRID_ROWS = 3

LINEAR_DIRECTIONS = {
    NoteCutDirection.UP,
    NoteCutDirection.DOWN,
    NoteCutDirection.LEFT,
    NoteCutDirection.RIGHT,
    NoteCutDirection.ANY,
}

DIR_TO_ANGLE: Dict[int, float] = {
    0: 180.0,
    1: 0.0,
    2: 270.0,
    3: 90.0,
    4: 225.0,
    5: 135.0,
    6: 315.0,
    7: 45.0,
    8: -1.0,
}

# Parity simplificada: direções opostas têm boa paridade de corte
NATURAL_FLOW: Dict[int, int] = {
    0: 1, 1: 0,   # UP <-> DOWN
    2: 3, 3: 2,   # LEFT <-> RIGHT
    4: 7, 7: 4,   # UP_LEFT <-> DOWN_RIGHT
    5: 6, 6: 5,   # UP_RIGHT <-> DOWN_LEFT
    8: 8,         # ANY sempre ok
}


# ─────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────

def beats_to_seconds(beats: float, bpm: float) -> float:
    if bpm <= 0:
        return 0.0
    return (beats / bpm) * 60.0


def angle_diff(a1: float, a2: float) -> float:
    diff = abs(a1 - a2) % 360.0
    return min(diff, 360.0 - diff)


def grid_distance(n1: Note, n2: Note) -> float:
    dx, dy = n1.x - n2.x, n1.y - n2.y
    return math.sqrt(dx * dx + dy * dy)


def is_same_time(b1: float, b2: float, bpm: float) -> bool:
    return beats_to_seconds(abs(b1 - b2), bpm) <= SIMULTANEOUS_THRESHOLD_SEC


# ─────────────────────────────────────────────────────────
# Detecção de Padrões
# ─────────────────────────────────────────────────────────

def detect_streams(hand_notes: List[Note], bpm: float) -> Dict[str, Any]:
    """
    Detecta streams: sequências de notas rápidas (≤ STREAM_BEAT_THRESHOLD beats por nota).
    """
    empty = {
        "stream_count": 0,
        "avg_stream_length": 0.0,
        "max_stream_length": 0,
        "stream_note_ratio": 0.0,
        "stream_bpm_avg": 0.0,
    }
    if len(hand_notes) < STREAM_MIN_LENGTH:
        return dict(empty)

    streams: List[List[Note]] = []
    current_stream: List[Note] = [hand_notes[0]]

    for i in range(1, len(hand_notes)):
        beat_diff = hand_notes[i].b - hand_notes[i - 1].b
        if beat_diff <= STREAM_BEAT_THRESHOLD:
            current_stream.append(hand_notes[i])
        else:
            if len(current_stream) >= STREAM_MIN_LENGTH:
                streams.append(current_stream)
            current_stream = [hand_notes[i]]

    if len(current_stream) >= STREAM_MIN_LENGTH:
        streams.append(current_stream)

    if not streams:
        return dict(empty)

    stream_lengths = [len(s) for s in streams]
    stream_notes_total = sum(stream_lengths)

    # BPM efetivo dos streams (baseado no intervalo médio entre notas)
    stream_bpms = []
    for s in streams:
        if len(s) >= 2:
            intervals = [s[i].b - s[i - 1].b for i in range(1, len(s))]
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval > 0:
                stream_bpms.append(bpm / avg_interval)

    return {
        "stream_count": len(streams),
        "avg_stream_length": sum(stream_lengths) / len(stream_lengths),
        "max_stream_length": max(stream_lengths),
        "stream_note_ratio": stream_notes_total / len(hand_notes),
        "stream_bpm_avg": sum(stream_bpms) / len(stream_bpms) if stream_bpms else 0.0,
    }


def detect_jumps(all_notes: List[Note], bpm: float) -> Dict[str, Any]:
    """
    Jumps: ambas as mãos simultâneas com distância grande na grid (≥ 2).
    """
    jump_count = 0
    jump_distances: List[float] = []

    i = 0
    while i < len(all_notes) - 1:
        n1 = all_notes[i]
        n2 = all_notes[i + 1]

        if n1.c == n2.c:
            i += 1
            continue

        if is_same_time(n1.b, n2.b, bpm):
            dist = grid_distance(n1, n2)
            jump_count += 1
            jump_distances.append(dist)
            i += 2
        else:
            i += 1

    return {
        "jump_count": jump_count,
        "avg_jump_distance": sum(jump_distances) / len(jump_distances) if jump_distances else 0.0,
        "max_jump_distance": max(jump_distances) if jump_distances else 0.0,
        "jump_density": jump_count / (len(all_notes) / 2) if all_notes else 0.0,
    }


def detect_crossovers(hand_notes: List[Note], hand: int) -> Dict[str, Any]:
    crossover_count = 0
    for note in hand_notes:
        if hand == 0 and note.x >= LEFT_CROSSOVER_COL:
            crossover_count += 1
        elif hand == 1 and note.x <= RIGHT_CROSSOVER_COL:
            crossover_count += 1

    return {
        "crossover_count": crossover_count,
        "crossover_ratio": crossover_count / len(hand_notes) if hand_notes else 0.0,
    }


def detect_doubles(hand_notes: List[Note]) -> Dict[str, Any]:
    double_count = 0
    for i in range(1, len(hand_notes)):
        if hand_notes[i].b - hand_notes[i - 1].b <= DOUBLE_BEAT_THRESHOLD:
            double_count += 1

    return {
        "double_count": double_count,
        "double_ratio": double_count / len(hand_notes) if hand_notes else 0.0,
    }


def detect_stacks(all_notes: List[Note], bpm: float) -> Dict[str, Any]:
    """Stacks/Towers: múltiplas notas na mesma posição quase ao mesmo tempo."""
    stack_count = 0
    i = 0
    while i < len(all_notes) - 1:
        n1 = all_notes[i]
        j = i + 1
        while j < len(all_notes) and is_same_time(n1.b, all_notes[j].b, bpm):
            n2 = all_notes[j]
            if n1.x == n2.x and n1.y == n2.y:
                stack_count += 1
            j += 1
        i += 1

    return {"stack_count": stack_count}


def detect_parity_breaks(hand_notes: List[Note]) -> Dict[str, Any]:
    """
    Parity breaks: direção de corte quebra o fluxo natural (resets de pulso).
    """
    if len(hand_notes) < 2:
        return {"parity_break_count": 0, "parity_break_ratio": 0.0, "reset_intensity": 0.0}

    breaks = 0
    reset_angles: List[float] = []

    for i in range(1, len(hand_notes)):
        prev_d = int(hand_notes[i - 1].d)
        curr_d = int(hand_notes[i].d)

        # Dot notes (ANY) não têm paridade definida
        if prev_d == 8 or curr_d == 8:
            continue

        natural_next = NATURAL_FLOW.get(prev_d, -1)
        if natural_next != curr_d:
            breaks += 1
            a1 = DIR_TO_ANGLE.get(prev_d, -1.0)
            a2 = DIR_TO_ANGLE.get(curr_d, -1.0)
            if a1 >= 0 and a2 >= 0:
                reset_angles.append(angle_diff(a1, a2))

    total_with_parity = sum(1 for n in hand_notes if int(n.d) != 8)

    return {
        "parity_break_count": breaks,
        "parity_break_ratio": breaks / total_with_parity if total_with_parity > 0 else 0.0,
        "reset_intensity": sum(reset_angles) / len(reset_angles) if reset_angles else 0.0,
    }


def detect_linear_vs_tech(all_notes: List[Note]) -> Dict[str, Any]:
    """
    Linear vs Tech: linear = cortes nas 4 direções principais ou dot;
    tech = diagonais + angleOffset.
    """
    linear_count = 0
    tech_count = 0
    angle_offset_sum = 0.0

    for note in all_notes:
        if int(note.d) in (8,):  # dot
            linear_count += 1
        elif note.d in LINEAR_DIRECTIONS:
            linear_count += 1
        else:
            tech_count += 1
        angle_offset_sum += abs(getattr(note, "a", 0))

    total = len(all_notes)
    return {
        "linear_count": linear_count,
        "tech_count": tech_count,
        "tech_ratio": tech_count / total if total > 0 else 0.0,
        "avg_angle_offset": angle_offset_sum / total if total > 0 else 0.0,
    }


def detect_hand_dominance(left_notes: List[Note], right_notes: List[Note]) -> Dict[str, Any]:
    l, r = len(left_notes), len(right_notes)
    total = l + r
    if total == 0:
        return {"hand_dominance": 0.0, "left_ratio": 0.5, "right_ratio": 0.5}

    dominance = abs(l - r) / total
    return {
        "hand_dominance": round(dominance, 4),
        "left_ratio": round(l / total, 4),
        "right_ratio": round(r / total, 4),
    }


def detect_obstacle_density(obstacles: List[Obstacle], duration_seconds: float) -> Dict[str, Any]:
    duck_walls = sum(1 for o in obstacles if o.y > 0)      # paredes acima do chão
    side_walls = sum(1 for o in obstacles if o.w < GRID_COLS)  # paredes parciais
    total = len(obstacles)

    obs_per_second = total / duration_seconds if duration_seconds > 0 else 0.0

    return {
        "obstacle_count": total,
        "duck_wall_count": duck_walls,
        "side_wall_count": side_walls,
        "obstacle_density": round(obs_per_second, 4),
    }


def detect_bomb_density(bombs: List[Note], duration_seconds: float) -> Dict[str, Any]:
    bps = len(bombs) / duration_seconds if duration_seconds > 0 else 0.0
    return {
        "bomb_count": len(bombs),
        "bomb_density": round(bps, 4),
    }


def detect_vision_blocks_advanced(all_notes: List[Note], bpm: float) -> Dict[str, Any]:
    """
    Vision blocks avançado: nota central seguida por nota não-central
    dentro de uma janela curta (difícil de ver a tempo).
    """
    if not all_notes:
        return {"advanced_vision_block_count": 0, "vision_block_severity": 0.0}

    WINDOW_SEC = 0.3
    vb_count = 0
    severity_scores: List[float] = []

    for i, note in enumerate(all_notes):
        if note.x not in (1, 2) or note.y not in (1, 2):
            continue
        j = i + 1
        while j < len(all_notes):
            dt = beats_to_seconds(all_notes[j].b - note.b, bpm)
            if dt > WINDOW_SEC:
                break
            blocked = all_notes[j]
            if blocked.x not in (1, 2) or blocked.y not in (1, 2):
                vb_count += 1
                severity_scores.append(1.0 - (dt / WINDOW_SEC))
            j += 1

    return {
        "advanced_vision_block_count": vb_count,
        "vision_block_severity": sum(severity_scores) / len(severity_scores)
        if severity_scores
        else 0.0,
    }


# ─────────────────────────────────────────────────────────
# Análise de Padrão Completa
# ─────────────────────────────────────────────────────────

def analyze_patterns(
    notes: List[Note],
    bombs: List[Note],
    obstacles: List[Obstacle],
    bpm: float,
    duration_seconds: float,
    version: str = "2.0.0",
    raw_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Ponto de entrada principal: recebe objetos parseados e retorna
    um dicionário completo de padrões (prefixo pat_).
    """
    if not notes:
        return {}

    notes_sorted = sorted(notes, key=lambda n: n.b)
    left_notes = [n for n in notes_sorted if int(n.c) == 0]
    right_notes = [n for n in notes_sorted if int(n.c) == 1]

    # ── Streams (por mão, média entre mãos) ──
    left_streams = detect_streams(left_notes, bpm)
    right_streams = detect_streams(right_notes, bpm)
    stream_metrics = {
        "stream_count": (left_streams["stream_count"] + right_streams["stream_count"]) / 2,
        "avg_stream_length": (
            left_streams["avg_stream_length"] + right_streams["avg_stream_length"]
        )
        / 2,
        "max_stream_length": max(
            left_streams["max_stream_length"], right_streams["max_stream_length"]
        ),
        "stream_note_ratio": (
            left_streams["stream_note_ratio"] + right_streams["stream_note_ratio"]
        )
        / 2,
        "stream_bpm_avg": (left_streams["stream_bpm_avg"] + right_streams["stream_bpm_avg"]) / 2,
    }

    # ── Demais detectores ──
    jump_metrics = detect_jumps(notes_sorted, bpm)

    l_cross = detect_crossovers(left_notes, 0)
    r_cross = detect_crossovers(right_notes, 1)
    crossover_metrics = {
        "crossover_count": l_cross["crossover_count"] + r_cross["crossover_count"],
        "crossover_ratio": (l_cross["crossover_ratio"] + r_cross["crossover_ratio"]) / 2,
    }

    l_doubles = detect_doubles(left_notes)
    r_doubles = detect_doubles(right_notes)
    double_metrics = {
        "double_count": l_doubles["double_count"] + r_doubles["double_count"],
        "double_ratio": (l_doubles["double_ratio"] + r_doubles["double_ratio"]) / 2,
    }

    stack_metrics = detect_stacks(notes_sorted, bpm)

    l_parity = detect_parity_breaks(left_notes)
    r_parity = detect_parity_breaks(right_notes)
    parity_metrics = {
        "parity_break_count": l_parity["parity_break_count"] + r_parity["parity_break_count"],
        "parity_break_ratio": (l_parity["parity_break_ratio"] + r_parity["parity_break_ratio"])
        / 2,
        "reset_intensity": (l_parity["reset_intensity"] + r_parity["reset_intensity"]) / 2,
    }

    lt_metrics = detect_linear_vs_tech(notes_sorted)
    dominance_metrics = detect_hand_dominance(left_notes, right_notes)
    obstacle_metrics = detect_obstacle_density(obstacles, duration_seconds)
    bomb_metrics = detect_bomb_density(bombs, duration_seconds)
    vb_metrics = detect_vision_blocks_advanced(notes_sorted, bpm)

    # ── Arcs / Chains (V3 only) ──
    arc_count = 0
    chain_count = 0
    if raw_data and version.startswith("3"):
        arc_count = len(raw_data.get("sliders", []) or raw_data.get("arcs", []))
        chain_count = len(raw_data.get("burstSliders", []) or raw_data.get("chains", []))

    arc_metrics = {
        "arc_count": arc_count,
        "chain_count": chain_count,
        "arc_density": (arc_count + chain_count) / duration_seconds
        if duration_seconds > 0
        else 0.0,
    }

    # ── Complexidade agregada de padrão ──
    pattern_complexity = (
        stream_metrics["stream_note_ratio"] * 2.0
        + jump_metrics["jump_density"] * 1.5
        + crossover_metrics["crossover_ratio"] * 2.5
        + double_metrics["double_ratio"] * 3.0
        + parity_metrics["parity_break_ratio"] * 2.0
        + lt_metrics["tech_ratio"] * 1.8
        + vb_metrics["vision_block_severity"] * 1.2
        + obstacle_metrics["obstacle_density"] * 0.5
        + bomb_metrics["bomb_density"] * 0.3
    )

    result: Dict[str, Any] = {}
    for metrics in (
        stream_metrics,
        jump_metrics,
        crossover_metrics,
        double_metrics,
        stack_metrics,
        parity_metrics,
        lt_metrics,
        dominance_metrics,
        obstacle_metrics,
        bomb_metrics,
        vb_metrics,
        arc_metrics,
    ):
        for k, v in metrics.items():
            result[f"pat_{k}"] = round(v, 4)
    result["pat_pattern_complexity"] = round(pattern_complexity, 4)
    # Métricas separadas por mão (assimetria)
    result["pat_left_stream_ratio"] = round(left_streams["stream_note_ratio"], 4)
    result["pat_right_stream_ratio"] = round(right_streams["stream_note_ratio"], 4)
    result["pat_left_crossover_ratio"] = round(l_cross["crossover_ratio"], 4)
    result["pat_right_crossover_ratio"] = round(r_cross["crossover_ratio"], 4)

    return result


# ─────────────────────────────────────────────────────────
# Classificador de tipo de mapa (heurístico)
# ─────────────────────────────────────────────────────────

KNOWN_STYLES = {"stream", "tech", "jump", "crossover", "speed", "obstacle", "balanced"}


def classify_map_style(pattern_metrics: Dict[str, Any]) -> List[str]:
    """
    Classifica o estilo do mapa baseado nos padrões detectados.
    Pode retornar múltiplas categorias; fallback "balanced".
    """
    styles = []
    p = pattern_metrics

    if p.get("pat_stream_note_ratio", 0) >= 0.35 or p.get("pat_stream_bpm_avg", 0) >= 160:
        styles.append("stream")
    if p.get("pat_tech_ratio", 0) >= 0.25 or p.get("pat_parity_break_ratio", 0) >= 0.2:
        styles.append("tech")
    if p.get("pat_jump_density", 0) >= 0.15 and p.get("pat_avg_jump_distance", 0) >= 2.0:
        styles.append("jump")
    if p.get("pat_crossover_ratio", 0) >= 0.12:
        styles.append("crossover")
    if p.get("pat_double_ratio", 0) >= 0.08:
        styles.append("speed")
    if p.get("pat_obstacle_density", 0) >= 0.5:
        styles.append("obstacle")
    if not styles:
        styles.append("balanced")

    return styles
