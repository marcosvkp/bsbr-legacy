"""Swing-based features portadas do beatleader-analyzer (C# → Python).

Núcleo: agrupa notas em swings, prevê paridade (DP), calcula strain angular,
repositioning/rotation, classifica multi-note (Stack/Tower/Window/Slider/
CurvedSlider) e walls (Dodge/Crouch), e produz ratings determinísticos
(PassRating/TechRating/MultiRating/PeakSustainedEBPM).

Referência: references/beatleader-analyzer/beatleader-analyzer/BeatmapScanner/

Simplificações vs BL (v1.5):
- Bomb avoidance simulation (% (FlagBombAvoidance) — complexa e marginal;
  bomb_count já existe como feature. Futuro: portar AnalyzeBombInfluence.
- NormalizeAngle/VerifyMultiNotes simplificados (sem clamp de tolerância).
- Strict angle tolerance: sempre: sempre default (não-strict).

Porte 1:1 do resto (constantes, fórmulas, DP, classifiers, ratings).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .parser.beatmap import Beatmap
from .parser.enums import NoteColor, NoteCutDirection
from .parser.objects import Note, Obstacle


# ─────────────────────────────────────────────────────────
# Constantes (Common.cs, GridPosition.cs, AngleTolerance.cs)
# ─────────────────────────────────────────────────────────

LANE_SPACING = 0.6
NOTE_SIZE = 0.3

# cut direction →1 → graus: 0=Up, 1=Down, 2=Left, 3=Right, 4=UpLeft, ...
DIRECTION_TO_DEGREE = (90, 270, 180, 0, 135, 45, 225, 315, 270)

# GridPosition.cs
X_SPACING = 0.6
Y_NOTE_HALF_HEIGHT = 0.275
Y_BOTTOM_TO_MIDDLE = 0.55
Y_MIDDLE_TO_TOP = 0.5

# AngleTolerance.cs
DEFAULT_TOLERANCE = 60.0
STRICT_TOLERANCE = 40.0
TOLERANCE_MARGIN = 8.0

# AnalyzeMap.cs
PASS_CALIBRATION_FACTOR = 0.825
ONE_SABER_NERF = 0.5
BALANCED_TECH_SCALER = 14.0

# Difficulty.cs
STRESS_FALLOFF = 2.0
DISTANCE_FALLOFF = 2.668
SPEED_FALLOFF_BASE = 1.4
PARITY_ERROR_MULTIPLIER = 2.0
STREAM_BONUS = 1.05
WALL_EXTRA_DURATION = 0.5
DODGE_WALL_BUFF = 1.1
CROUCH_WALL_BUFF = 1.2

# AngleStrain.cs
LEFT_FOREHAND_NEUTRAL = 292.5
RIGHT_FOREHAND_NEUTRAL = 247.5
LEFT_BACKHAND_NEUTRAL = 112.5
RIGHT_BACKHAND_NEUTRAL = 67.5

# Multi-note values (AnalyzeMap.cs:197-208)
STACK_VALUE = 1.05
TOWER_VALUE = 1.1
SLIDER_VALUE = 1.05
CURVED_SLIDER_VALUE = 1.5
WINDOW_VALUE = 1.1

# Window sizes para pass diff (AnalyzeMap.cs:75)
PASS_WINDOW_SIZES = (8, 16, 32, 64, 128)

# PreprocessNotes.cs
SIMULTANEOUS_THRESHOLD_SEC = 0.020


# ─────────────────────────────────────────────────────────
# Helpers (Common.cs, GridPosition.cs, AngleTolerance.cs)
# ─────────────────────────────────────────────────────────

def _mod(x: float, m: float) -> float:
    return (x % m + m) % m


def _angle_diff(a: float, b: float) -> float:
    """Diferença de ângulo com sinal (b - a), tratando wrapping."""
    return (b - a + 540) % 360 - 180


def _reverse_cut_dir(direction: float) -> float:
    return direction - 180 if direction >= 180 else direction + 180


def _is_same_dir(before: float, after: float, degree: float = 67.5) -> bool:
    before = _mod(before, 360)
    after = _mod(after, 360)
    diff = abs(before - after)
    if diff <= 180:
        return diff < degree
    return (360 - diff) < degree


def _grid_x_to_meters(grid_x: float) -> float:
    return (grid_x - 1.5) * X_SPACING


def _grid_y_to_meters(grid_y: float) -> float:
    if grid_y < 0:
        return -Y_NOTE_HALF_HEIGHT
    if grid_y > 2:
        return Y_BOTTOM_TO_MIDDLE + Y_MIDDLE_TO_TOP + Y_NOTE_HALF_HEIGHT
    if grid_y <= 1.0:
        return grid_y * Y_BOTTOM_TO_MIDDLE
    return Y_BOTTOM_TO_MIDDLE + (grid_y - 1.0) * Y_MIDDLE_TO_TOP


def _grid_to_meters(grid_x: float, grid_y: float) -> tuple[float, float]:
    return (_grid_x_to_meters(grid_x), _grid_y_to_meters(grid_y))


def _get_tolerance(strict_angles: bool) -> float:
    if strict_angles:
        return STRICT_TOLERANCE - TOLERANCE_MARGIN
    return DEFAULT_TOLERANCE - TOLERANCE_MARGIN


def _sim_swing_pos(x: float, y: float, direction: float, distance: float = 1.5) -> tuple[float, float]:
    mx, my = _grid_to_meters(x, y)
    dist_m = distance * 0.6
    rad = math.radians(direction)
    return (mx + dist_m * math.cos(rad), my + dist_m * math.sin(rad))


def _find_angle_via_pos(
    cur_x: int, cur_y: int, prev_x: int, prev_y: int, guide_angle: float, is_same_swing: bool,
) -> float:
    cur_pos = _grid_to_meters(cur_x, cur_y)
    if is_same_swing:
        start_pos = _grid_to_meters(prev_x, prev_y)
    else:
        start_pos = _sim_swing_pos(prev_x, prev_y, guide_angle)

    if abs(start_pos[0] - cur_pos[0]) < 0.001 and abs(start_pos[1] - cur_pos[1]) < 0.001:
        return guide_angle if is_same_swing else _reverse_cut_dir(guide_angle)

    dx = cur_pos[0] - start_pos[0]
    dy = cur_pos[1] - start_pos[1]
    spatial = _mod(math.degrees(math.atan2(dy, dx)), 360)
    calc = spatial

    if is_same_swing:
        if not _is_same_dir(spatial, guide_angle):
            calc = _reverse_cut_dir(spatial)
            if not _is_same_dir(calc, guide_angle):
                calc = guide_angle
    else:
        if _is_same_dir(spatial, guide_angle):
            calc = _reverse_cut_dir(spatial)
    return calc


def _get_initial_position(x: int, y: int, is_right_hand: bool) -> float:
    """Direção inicial para primeira nota dot (heurística de posição)."""
    if is_right_hand:
        if x >= 2:
            return 0.0  # Right
        if x <= 1:
            return 180.0  # Left
    else:
        if x <= 1:
            return 0.0  # Right (mão esquerda vai pra direita)
        if x >= 2:
            return 180.0  # Left
    if y == 2:
        return 270.0  # Down
    return 90.0  # Up


# ─────────────────────────────────────────────────────────
# Cube (wrapper de Note com metadata de análise)
# ─────────────────────────────────────────────────────────

@dataclass
class Cube:
    """Note com metadata de análise (porte de Cube.cs)."""
    note: Note
    bpm_time: float
    x: int
    y: int
    type: int  # 0=red/left, 1=blue/right
    cut_direction: int
    angle_offset: float
    direction: float
    head: bool = False
    tail: bool = False
    pattern: bool = False
    forehand: bool = True
    parity_error: bool = False

    @classmethod
    def from_note(cls, note: Note) -> "Cube":
        d = int(note.d)
        direction = -1.0 if d == 8 else _mod(DIRECTION_TO_DEGREE[d] + note.a, 360)
        return cls(
            note=note,
            bpm_time=float(note.b),
            x=int(note.x),
            y=int(note.y),
            type=int(note.c),
            cut_direction=d,
            angle_offset=float(note.a),
            direction=direction,
        )


# ─────────────────────────────────────────────────────────
# PreprocessNotes (agrupamento em swings + direção de dots)
# ─────────────────────────────────────────────────────────

def _create_note_groups(cubes: list[Cube]) -> list[list[int]]:
    """Agrupa notas próximas no tempo (swings/multi-note). Porte de CreateNoteGroups."""
    groups: list[list[int]] = []
    i = 0
    n = len(cubes)
    while i < n:
        group: list[int] = [i]
        j = i + 1
        while j < n:
            dt = cubes[j].note.b - cubes[j - 1].note.b
            if dt <= 0 and abs(cubes[j].bpm_time - cubes[i].bpm_time) < 1e-9:
                group.append(j)
                j += 1
            else:
                break
        # Reordena por bpm_time se necessário
        if len(group) > 1:
            group.sort(key=lambda idx: cubes[idx].bpm_time)
        groups.append(group)
        i = j
    return groups


def _validate_sliders(prev: Cube, cur: Cube) -> bool:
    """Valida se prev→cur forma um slider (mesmo swing). Porte de ValidateSliders."""
    # Dot spam na mesma posição = slider
    if cur.cut_direction == 8 and prev.x == cur.x and prev.y == cur.y:
        return True

    line_diff = cur.x - prev.x
    layer_diff = cur.y - prev.y
    if line_diff == 0 and layer_diff == 0:
        return False

    geometric = math.degrees(math.atan2(layer_diff, line_diff))
    if geometric < 0:
        geometric += 360.0

    # Case 0: ambos dots
    if prev.cut_direction == 8 and cur.cut_direction == 8:
        prev.direction = geometric
        cur.direction = geometric
        return True
    # Case 1: prev arrow, cur dot
    if prev.cut_direction != 8 and cur.cut_direction == 8:
        if _is_same_dir(geometric, prev.direction):
            cur.direction = prev.direction
            return True
    # Case 2: prev dot, cur arrow
    if prev.cut_direction == 8 and cur.cut_direction != 8:
        if _is_same_dir(geometric, cur.direction):
            prev.direction = cur.direction
            return True
    # Case 3: ambos arrows
    if prev.cut_direction != 8 and cur.cut_direction != 8:
        if not _is_same_dir(prev.direction, cur.direction):
            return False
        if _is_same_dir(geometric, cur.direction) or _is_same_dir(geometric, prev.direction):
            return True
    return False


def _set_initial_directions(cubes: list[Cube], groups: list[list[int]], is_right_hand: bool) -> None:
    """Seta direção do HEAD de cada grupo. Porte simplificado (sem bomb avoidance)."""
    previous_direction = 270.0
    previous_cube_index = 0

    for g_idx, group in enumerate(groups):
        head_idx = group[0]
        head = cubes[head_idx]

        if head.cut_direction != 8:
            pass  # arrow: direção já é literal
        else:
            if g_idx == 0:
                head.direction = _get_initial_position(head.x, head.y, is_right_hand)
            else:
                # Dot: direção baseada no swing anterior (reverte direção)
                head.direction = _find_angle_via_pos(
                    head.x, head.y,
                    cubes[previous_cube_index].x, cubes[previous_cube_index].y,
                    previous_direction, False,
                )

        # Marca pattern/head/tail dentro do grupo
        if len(group) == 1:
            cubes[group[0]].head = True
            cubes[group[0]].tail = True
            cubes[group[0]].pattern = False
        else:
            for k, idx in enumerate(group):
                cubes[idx].head = (k == 0)
                cubes[idx].tail = (k == len(group) - 1)
                cubes[idx].pattern = True

        previous_direction = head.direction
        previous_cube_index = head_idx


def _validate_and_correct_group_angles(cubes: list[Cube], groups: list[list[int]]) -> None:
    """Valida sliders dentro de cada grupo e corrige direções. Porte simplificado."""
    for group in groups:
        if len(group) < 2:
            continue
        for k in range(1, len(group)):
            _validate_sliders(cubes[group[k - 1]], cubes[group[k]])


def preprocess_notes(cubes: list[Cube], is_right_hand: bool) -> None:
    """Detecta padrões e seta direções. Porte de PreprocessNotes.Detect (sem bombs)."""
    groups = _create_note_groups(cubes)
    _set_initial_directions(cubes, groups, is_right_hand)
    _validate_and_correct_group_angles(cubes, groups)


# ─────────────────────────────────────────────────────────
# ParityPredictor (DP — Viterbi-like)
# ─────────────────────────────────────────────────────────

def predict_parity(cubes: list[Cube], is_right_hand: bool) -> None:
    """Prevê paridade forehand/backhand via DP. Porte de ParityPredictor.Predict.

    DP: cost[i][parity] = min cost para chegar no swing i com paridade (0=backhand, 1=forehand).
    Transition cost = angle strain entre swings com paridades dadas.
    """
    # Índices dos swings (heads ou non-pattern notes)
    swing_indices = [i for i, c in enumerate(cubes) if not c.pattern or c.head]
    n = len(swing_indices)
    if n <= 1:
        return

    INF = float("inf")
    cost = [[INF, INF] for _ in range(n)]
    parent = [[False, False] for _ in range(n)]

    # Init: primeira swing — preferência porBbackhand se UP, forehand senão
    first_dir = cubes[swing_indices[0]].direction
    if _is_same_dir(first_dir, 90.0):  # UP → backhand start
        cost[0][0] = 0.0
    else:
        cost[0][1] = 0.0

    # Forward pass
    for i in range(1, n):
        cur = cubes[swing_indices[i]]
        prev = cubes[swing_indices[i - 1]]
        for cur_parity in (False, True):
            for prev_parity in (False, True):
                if cost[i - 1][prev_parity] == INF:
                    continue
                strain = _parity_angle_strain(prev, cur, prev_parity, cur_parity, is_right_hand)
                total = cost[i - 1][prev_parity] + strain
                if total < cost[i][cur_parity]:
                    cost[i][cur_parity] = total
                    parent[i][cur_parity] = prev_parity

    # Backtrack: escolhe melhor paridade final
    best_final = 0 if cost[n - 1][0] <= cost[n - 1][1] else 1
    parities = [False] * n
    parities[n - 1] = bool(best_final)
    for i in range(n - 1, 0, -1):
        parities[i - 1] = parent[i][int(parities[i])]

    # Aplica paridades e detecta errors (mesma paridade consecutiva = reset)
    prev_parity = None
    for i, idx in enumerate(swing_indices):
        cubes[idx].forehand = parities[i]
        if i > 0 and parities[i] == parities[i - 1]:
            cubes[idx].parity_error = True


def _parity_angle_strain(prev: Cube, cur: Cube, prev_forehand: bool, cur_forehand: bool, is_right_hand: bool) -> float:
    """Strain entre dois swings com paridades dadas. Porte de ParityAngleStrainCalc."""
    neutral = _neutral_angle(cur_forehand, is_right_hand)
    deviation = _angle_deviation(neutral, cur.direction)
    strain = (deviation / 180.0) ** 2

    # Falloff temporal
    dt = abs(cur.bpm_time - prev.bpm_time)
    if dt >= 0.25:
        strain *= math.exp((0.25 - dt) * math.log(4.0))
    return strain


def _neutral_angle(forehand: bool, is_right_hand: bool) -> float:
    if forehand:
        return RIGHT_FOREHAND_NEUTRAL if is_right_hand else LEFT_FOREHAND_NEUTRAL
    return RIGHT_BACKHAND_NEUTRAL if is_right_hand else LEFT_BACKHAND_NEUTRAL


def _angle_deviation(a1: float, a2: float) -> float:
    diff = abs(a1 - a2)
    return 180 - abs(diff - 180)


# ─────────────────────────────────────────────────────────
# SwingData + SwingCreation
# ─────────────────────────────────────────────────────────

@dataclass
class SwingData:
    cubes: list[Cube]
    bpm_time: float
    direction: float
    forehand: bool
    entry_position: tuple[float, float] = (0.0, 0.0)
    exit_position: tuple[float, float] = (0.0, 0.0)
    angle_strain: float = 0.0
    repositioning_distance: float = 0.0
    rotation_amount: float = 0.0
    swing_frequency: float = 0.0
    hit_distance: float = 0.0
    swing_diff: float = 0.0
    swing_tech: float = 0.0
    njs_buff: float = 1.0
    wall_buff: float = 1.0
    is_linear: bool = False
    is_stream: bool = False
    pattern_type: str = "Single"


def _calc_entry_exit(swing: SwingData) -> None:
    head = swing.cubes[0]
    hx, hy = _grid_to_meters(head.x, head.y)
    angle = head.direction
    rad = math.radians(angle)
    cos_v = math.cos(rad)
    sin_v = math.sin(rad)
    swing.entry_position = (hx - cos_v * NOTE_SIZE, hy - sin_v * NOTE_SIZE)
    swing.exit_position = (hx + cos_v * NOTE_SIZE, hy + sin_v * NOTE_SIZE)


def _swing_angle_strain_calc(cur: SwingData, prev: SwingData | None, is_right_hand: bool) -> float:
    if prev is None:
        return 0.0
    neutral = _neutral_angle(cur.forehand, is_right_hand)
    deviation = _angle_deviation(neutral, cur.direction)
    strain = (deviation / 180.0) ** 2
    dt = abs(cur.cubes[0].bpm_time - prev.cubes[-1].bpm_time)
    if dt >= 0.25:
        strain *= math.exp((0.25 - dt) * math.log(4.0))
    return strain


def create_swings(cubes: list[Cube], is_right_hand: bool) -> list[SwingData]:
    """Cria SwingData a partir dos cubes. Porte de SwingCreation.Process."""
    if not cubes:
        return []

    groups: list[list[Cube]] = []
    current: list[Cube] = []
    for cube in cubes:
        if cube.head:
            if current:
                groups.append(current)
            current = [cube]
        else:
            if not current:
                current = [cube]
                groups.append(current)
                current = []
            else:
                current.append(cube)
    if current:
        groups.append(current)

    swings: list[SwingData] = []
    for group in groups:
        head = group[0]
        swing = SwingData(
            cubes=group,
            bpm_time=head.bpm_time,
            direction=head.direction,
            forehand=head.forehand,
        )
        _calc_entry_exit(swing)
        swings.append(swing)

    # Swing frequency
    for i in range(1, len(swings)):
        dt = swings[i].bpm_time - swings[i - 1].bpm_time
        if dt > 0:
            swings[i].swing_frequency = 1.0 / dt

    # Angle strain + linear detection
    if swings:
        swings[0].angle_strain = _swing_angle_strain_calc(swings[0], None, is_right_hand) * 4.0
    is_linear = True
    for i in range(1, len(swings)):
        swings[i].angle_strain = _swing_angle_strain_calc(swings[i], swings[i - 1], is_right_hand) * 4.0

        target = _reverse_cut_dir(swings[i - 1].direction)
        direction_matches = _is_same_dir(target, swings[i].direction, 22.5)
        prev_pos = swings[i - 1].cubes[-1]
        curr_pos = swings[i].cubes[0]
        dx = curr_pos.x - prev_pos.x
        dy = curr_pos.y - prev_pos.y
        geometric = _mod(math.degrees(math.atan2(dy, dx)), 360) if (dx or dy) else 0.0
        movement_matches = _is_same_dir(target, geometric, 22.5)
        if direction_matches and (movement_matches or (dx == 0 and dy == 0)):
            if is_linear:
                swings[i].is_linear = True
            is_linear = True
        else:
            is_linear = False

    # Hit distance
    for i in range(1, len(swings)):
        dx = swings[i].entry_position[0] - swings[i - 1].entry_position[0]
        dy = swings[i].entry_position[1] - swings[i - 1].entry_position[1]
        swings[i].hit_distance = math.sqrt(dx * dx + dy * dy)

    return swings


# ─────────────────────────────────────────────────────────
# SwingMovement (repositioning + rotation)
# ─────────────────────────────────────────────────────────

def calc_swing_movement(swings: list[SwingData]) -> None:
    """Calcula repositioning distance e rotation amount. Porte de SwingMovement.Calc."""
    if len(swings) < 2:
        return

    for i in range(1, len(swings)):
        cur = swings[i]
        prev = swings[i - 1]

        # Repositioning: componente perpendicular ao swing direction
        dx = cur.entry_position[0] - prev.exit_position[0]
        dy = cur.entry_position[1] - prev.exit_position[1]
        rad = math.radians(cur.direction)
        perp_x = -math.sin(rad)
        perp_y = math.cos(rad)
        repositioning = abs(dx * perp_x + dy * perp_y) * 0.6875

        # Média 2-swing (suaviza)
        if i >= 2:
            prev2 = swings[i - 2]
            dx2 = cur.entry_position[0] - prev2.exit_position[0]
            dy2 = cur.entry_position[1] - prev2.exit_position[1]
            repositioning += abs(dx2 * perp_x + dy2 * perp_y) * 0.0625

        cur.repositioning_distance = repositioning

        # Rotation amount: Δangle ajustado por paridade
        rotation = abs(_angle_diff(prev.direction, cur.direction))
        if prev.forehand != cur.forehand:
            rotation = abs(rotation - 180.0)
        cur.rotation_amount = rotation


# ─────────────────────────────────────────────────────────
# MultiNoteClassifier (Stack/Tower/Window/Slider/CurvedSlider)
# ─────────────────────────────────────────────────────────

@dataclass
class MultiNoteStats:
    stacks: int = 0
    towers: int = 0
    sliders: int = 0
    curved_sliders: int = 0
    windows: int = 0
    slanted_windows: int = 0


def classify_multi_note(swing: SwingData, stats: MultiNoteStats) -> str:
    """Classifica um swing multi-note. Porte de MultiNoteClassifier."""
    cubes = swing.cubes
    if len(cubes) < 2:
        return "Single"

    head = cubes[0]
    tail = cubes[-1]

    # Slider: ≥2 notas sequenciais
    is_slider = len(cubes) >= 2
    # Curved slider: notas não colineares (cross product ≠ 0)
    is_curved = False
    if len(cubes) >= 3:
        for k in range(2, len(cubes)):
            v1x = cubes[1].x - cubes[0].x
            v1y = cubes[1].y - cubes[0].y
            v2x = cubes[k].x - cubes[0].x
            v2y = cubes[k].y - cubes[0].y
            if v1x * v2y - v1y * v2x != 0:
                is_curved = True
                break

    # Stack: 2 notas adjacentes alinhadas no swing direction
    is_stack = False
    if len(cubes) == 2:
        dx = tail.x - head.x
        dy = tail.y - head.y
        rad = math.radians(swing.direction)
        dir_x = math.cos(rad)
        dir_y = math.sin(rad)
        dot = dx * dir_x + dy * dir_y
        if dot > 0 and abs(dx) <= 1 and abs(dy) <= 1:
            is_stack = True

    # Tower: 3 notas em linha (vertical/horizontal/diagonal)
    is_tower = False
    if len(cubes) == 3:
        v1x = cubes[1].x - cubes[0].x
        v1y = cubes[1].y - cubes[0].y
        v2x = cubes[2].x - cubes[1].x
        v2y = cubes[2].y - cubes[1].y
        if v1x == v2x and v1y == v2y and (v1x or v1y):
            is_tower = True

    # Window: 2 notas com gap, alinhadas
    is_window = False
    is_slanted_window = False
    if len(cubes) == 2:
        dx = tail.x - head.x
        dy = tail.y - head.y
        if abs(dx) > 1 or abs(dy) > 1:
            geometric = math.degrees(math.atan2(dy, dx)) if (dx or dy) else 0.0
            if _is_same_dir(geometric, swing.direction, 22.5):
                is_window = True
            else:
                is_slanted_window = True

    #' Conta e classifica
    if is_curved:
        stats.curved_sliders += 1
        return "CurvedSlider"
    if is_tower:
        stats.towers += 1
        return "Tower"
    if is_stack:
        stats.stacks += 1
        return "Stack"
    if is_slanted_window:
        stats.slanted_windows += 1
        return "SlantedWindow"
    if is_window:
        stats.windows += 1
        return "Window"
    if is_slider:
        stats.sliders += 1
        return "Slider"
    return "Single"


# ─────────────────────────────────────────────────────────
# WallClassifier (Dodge vs Crouch)
# ─────────────────────────────────────────────────────────

@dataclass
class ClassifiedWalls:
    dodge_walls: list[Obstacle] = field(default_factory=list)
    crouch_walls: list[Obstacle] = field(default_factory=list)


def classify_walls(walls: list[Obstacle]) -> ClassifiedWalls:
    """Classifica walls em dodge (em pé) e crouch (overhead). Porte de WallClassifier."""
    result = ClassifiedWalls()
    if not walls:
        return result

    sorted_walls = sorted(walls, key=lambda w: w.b)
    last_dodge_b = None
    last_crouch_b = None
    DODGE_COOLDOWN = 1.0

    for w in sorted_walls:
        # Só conta walls que cobrem o centro
        covers_center = (w.x <= 1 and w.x + w.w > 1) or (w.x == 2 and w.h >= 1)
        if not covers_center:
            continue

        is_overhead = (w.y + w.h > 2) and (w.y == 2)
        blocks_standing = (w.h + w.y >= 3)

        if is_overhead and not blocks_standing:
            if last_crouch_b is None or (w.b - last_crouch_b) > DODGE_COOLDOWN:
                result.crouch_walls.append(w)
                last_crouch_b = w.b
        elif blocks_standing:
            if last_dodge_b is None or (w.b - last_dodge_b) > DODGE_COOLDOWN:
                result.dodge_walls.append(w)
                last_dodge_b = w.b

    return result


# ─────────────────────────────────────────────────────────
# NjsBuff
# ─────────────────────────────────────────────────────────

def calculate_njs_buff(njs: float, speed_mult: float = 1.0, njs_mult: float = 1.0) -> float:
    """Porte de NjsBuff.CalculateNjsBuff."""
    njs = njs * speed_mult * njs_mult
    if njs > 24:
        return 1.0 + 0.01 * (njs - 24)
    return 1.0


# ─────────────────────────────────────────────────────────
# AnalyzeMap (orquestração + ratings)
# ─────────────────────────────────────────────────────────

@dataclass
class SwingAnalysis:
    swings: list[SwingData]
    stats: MultiNoteStats
    walls: ClassifiedWalls
    pass_rating: float
    tech_rating: float
    multi_rating: float
    peak_sustained_ebpm: float
    low_note_nerf: float
    one_saber_ratio: float
    linear_percentage: float
    parity_error_count: int
    bomb_avoidance_count: int  # sempre 0 em v1.5 (sem sim)


def analyze_swings(
    beatmap: Beatmap,
    bpm: float,
    njs: float = 0.0,
    speed_mult: float = 1.0,
    njs_mult: float = 1.0,
) -> SwingAnalysis | None:
    """Análise swing-based completa. Porte de AnalyzeMap.UseAlgorithm."""
    # Split por mão
    red_notes = [n for n in beatmap.notes if int(n.c) == 0]
    blue_notes = [n for n in beatmap.notes if int(n.c) == 1]

    if len(red_notes) < 2 and len(blue_notes) < 2:
        return None

    all_swings: list[SwingData] = []
    parity_errors = 0

    for notes, is_right in ((red_notes, False), (blue_notes, True)):
        if len(notes) < 2:
            continue
        cubes = [Cube.from_note(n) for n in notes]
        cubes.sort(key=lambda c: c.bpm_time)

        preprocess_notes(cubes, is_right)
        predict_parity(cubes, is_right)
        swings = create_swings(cubes, is_right)
        calc_swing_movement(swings)

        # Njs buff por swing
        buff = calculate_njs_buff(njs, speed_mult, njs_mult)
        for s in swings:
            s.njs_buff = buff

        all_swings.extend(swings)
        parity_errors += sum(1 for c in cubes if c.parity_error)

    if not all_swings:
        return None

    # Multi-note classification
    mn_stats = MultiNoteStats()
    for s in all_swings:
        s.pattern_type = classify_multi_note(s, mn_stats)

    # Wall classification
    walls = classify_walls(beatmap.obstacles)
    # Aplica wall buff nos swings próximos
    for w in walls.dodge_walls:
        for s in all_swings:
            if abs(s.bpm_time - w.b) < 1.0:
                s.wall_buff *= DODGE_WALL_BUFF
    for w in walls.crouch_walls:
        for s in all_swings:
            if abs(s.bpm_time - w.b) < 1.0:
                s.wall_buff *= CROUCH_WALL_BUFF

    # Pass diff (multi-window)
    pass_diff = _calc_pass_diff(all_swings, bpm * speed_mult)

    # Swing diff e tech por swing
    for i, s in enumerate(all_swings):
        swing_speed = s.swing_frequency * (bpm * speed_mult / 60.0)
        stress = (s.angle_strain * 0.05 + s.repositioning_distance * 0.3 + s.rotation_amount * 0.2)
        stress *= (s.hit_distance / (s.hit_distance + DISTANCE_FALLOFF) + 1.0)
        stress_mult = STRESS_FALLOFF * stress / (stress + STRESS_FALLOFF) + 1.0
        low_speed_falloff = 1.0 - SPEED_FALLOFF_BASE ** (-swing_speed) if swing_speed > 0 else 0.0
        stream_bonus = STREAM_BONUS if i > 0 and all_swings[i - 1].forehand != s.forehand else 1.0
        parity_mult = PARITY_ERROR_MULTIPLIER if s.cubes[0].parity_error else 1.0

        s.swing_diff = swing_speed * low_speed_falloff * stress_mult * s.njs_buff * stream_bonus * s.wall_buff
        s.swing_tech = stress_mult * s.njs_buff * parity_mult * s.wall_buff

    # Ratings
    pass_combined = sum(s.swing_diff for s in all_swings) / len(all_swings)
    total_notes = len(beatmap.notes)
    low_note_nerf = 0.6 + (max(20, min(200, total_notes)) - 20) / 450.0

    # One-saber nerf
    red_count = len(red_notes)
    blue_count = len(blue_notes)
    if red_count + blue_count > 0:
        hands_ratio = abs(red_count - blue_count) / (red_count + blue_count)
    else:
        hands_ratio = 0.0
    nerf_mult = 1.0 if hands_ratio < 0.7 else ONE_SABER_NERF

    pass_rating = pass_combined * nerf_mult * low_note_nerf * PASS_CALIBRATION_FACTOR

    # Tech: top 75% swing_tech médio, acoplado ao pass
    tech_sorted = sorted((s.swing_tech for s in all_swings), reverse=True)
    top_75 = tech_sorted[: max(1, int(len(tech_sorted) * 0.75))]
    tech_avg = sum(top_75) / len(top_75) if top_75 else 0.0
    tech_rating = tech_avg * (1.0 - SPEED_FALLOFF_BASE ** (-pass_combined)) * BALANCED_TECH_SCALER

    # Multi rating
    swing_count = len(all_swings)
    multi_rating = (
        mn_stats.stacks * STACK_VALUE
        + mn_stats.towers * TOWER_VALUE
        + mn_stats.sliders * SLIDER_VALUE
        + mn_stats.curved_sliders * CURVED_SLIDER_VALUE
        + mn_stats.windows * WINDOW_VALUE
    ) / swing_count if swing_count else 0.0

    # Peak sustained EBPM (janela 4 swings)
    peak_sustained = _peak_sustained_ebpm(all_swings, bpm * speed_mult)

    # Linear percentage
    linear_pct = sum(1 for s in all_swings if s.is_linear) / swing_count if swing_count else 0.0

    return SwingAnalysis(
        swings=all_swings,
        stats=mn_stats,
        walls=walls,
        pass_rating=pass_rating,
        tech_rating=tech_rating,
        multi_rating=multi_rating,
        peak_sustained_ebpm=peak_sustained,
        low_note_nerf=low_note_nerf,
        one_saber_ratio=hands_ratio,
        linear_percentage=linear_pct,
        parity_error_count=parity_errors,
        bomb_avoidance_count=0,
    )


def _calc_pass_diff(swings: list[SwingData], modified_bpm: float) -> float:
    """Pass diff médio em 5 janelas. Porte de AnalyzeMap (multi-window)."""
    if not swings:
        return 0.0
    bps = modified_bpm / 60.0
    if bps <= 0:
        return 0.0
    diffs = []
    for window in PASS_WINDOW_SIZES:
        window_secs = window / bps
        total = 0.0
        count = 0
        for s in swings:
            in_window = [o for o in swings if 0 <= o.bpm_time - s.bpm_time <= window_secs]
            if in_window:
                total += sum(o.swing_diff for o in in_window)
                count += 1
        if count:
            diffs.append(total / count)
    return sum(diffs) / len(diffs) if diffs else 0.0


def _peak_sustained_ebpm(swings: list[SwingData], modified_bpm: float) -> float:
    """Pico de EBPM sustentado (janela 4 swings). Porte de AnalyzeMap.cs:213."""
    if len(swings) < 4:
        return 0.0
    peak = 0.0
    for i in range(len(swings) - 3):
        window = swings[i : i + 4]
        dt = window[-1].bpm_time - window[0].bpm_time
        if dt > 0:
            ebpm = 4.0 / dt * modified_bpm
            peak = max(peak, ebpm)
    return peak


# ─────────────────────────────────────────────────────────
# API pública — features para o ML
# ─────────────────────────────────────────────────────────

def compute_swing_features(beatmap: Beatmap, bpm: float, njs: float = 0.0) -> dict[str, float]:
    """Computa features swing-based para o ML. Retorna dict de chaves pat_swing_*.

    Retorna dict vazio se o mapa tem <2 notas por mão (análise não vale).
    Todas as features são finitas e não-negativas.
    """
    analysis = analyze_swings(beatmap, bpm, njs)
    if analysis is None:
        return {}

    swings = analysis.swings
    n = len(swings)
    if n == 0:
        return {}

    def avg(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def peak(vals: list[float]) -> float:
        return max(vals) if vals else 0.0

    freqs = [s.swing_frequency for s in swings if s.swing_frequency > 0]
    hits = [s.hit_distance for s in swings if s.hit_distance > 0]
    repositionings = [s.repositioning_distance for s in swings]
    rotations = [s.rotation_amount for s in swings]
    angle_strains = [s.angle_strain for s in swings]
    njs_buffs = [s.njs_buff for s in swings]

    return {
        "pat_swing_count": float(n),
        "pat_swing_frequency_avg": avg(freqs),
        "pat_swing_frequency_peak": peak(freqs),
        "pat_hit_distance_avg": avg(hits),
        "pat_hit_distance_peak": peak(hits),
        "pat_repositioning_distance_avg": avg(repositionings),
        "pat_repositioning_distance_peak": peak(repositionings),
        "pat_rotation_amount_avg": avg(rotations),
        "pat_rotation_amount_peak": peak(rotations),
        "pat_angle_strain_avg": avg(angle_strains),
        "pat_angle_strain_peak": peak(angle_strains),
        "pat_linear_swing_ratio": analysis.linear_percentage,
        "pat_parity_error_count_dp": float(analysis.parity_error_count),
        "pat_parity_error_ratio_dp": analysis.parity_error_count / n,
        "pat_bomb_avoidance_count": float(analysis.bomb_avoidance_count),
        "pat_stack_count": float(analysis.stats.stacks),
        "pat_tower_count": float(analysis.stats.towers),
        "pat_slider_count": float(analysis.stats.sliders),
        "pat_curved_slider_count": float(analysis.stats.curved_sliders),
        "pat_window_count": float(analysis.stats.windows),
        "pat_slanted_window_count": float(analysis.stats.slanted_windows),
        "pat_dodge_wall_count": float(len(analysis.walls.dodge_walls)),
        "pat_crouch_wall_count": float(len(analysis.walls.crouch_walls)),
        "pat_njs_buff_avg": avg(njs_buffs),
        "pat_njs_max": float(njs),
        "pat_peak_sustained_ebpm": analysis.peak_sustained_ebpm,
        "pat_multi_rating_bl": analysis.multi_rating,
        "pat_low_note_nerf": analysis.low_note_nerf,
        "pat_one_saber_ratio": analysis.one_saber_ratio,
        "pat_pass_rating_bl": analysis.pass_rating,
        "pat_tech_rating_bl": analysis.tech_rating,
    }
