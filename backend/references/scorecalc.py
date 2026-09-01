from dataclasses import dataclass
from typing import List
import math


def clamp(value, min_value, max_value):
    return max(min_value, min(value, max_value))


def lerp(a, b, t):
    return a + (b - a) * t


@dataclass
class CurvePoint:
    acc: float
    multiplier: float

    def getAcc(self):
        return self.acc

    def getMultiplier(self):
        return self.multiplier


WEIGHT_COEFFICIENT = 0.965
STAR_MULTIPLIER = 42.117208413

curve_points = [
    CurvePoint(0, 0),
    CurvePoint(0.6, 0.18223233667439062),
    CurvePoint(0.65, 0.5866010012767576),
    CurvePoint(0.7, 0.6125565959114954),
    CurvePoint(0.75, 0.6451808210101443),
    CurvePoint(0.8, 0.6872268862950283),
    CurvePoint(0.825, 0.7150465663454271),
    CurvePoint(0.85, 0.7462290664143185),
    CurvePoint(0.875, 0.7816934560296046),
    CurvePoint(0.9, 0.825756123560842),
    CurvePoint(0.91, 0.8488375988124467),
    CurvePoint(0.92, 0.8728710341448851),
    CurvePoint(0.93, 0.9039994071865736),
    CurvePoint(0.94, 0.9417362980580238),
    CurvePoint(0.95, 1),
    CurvePoint(0.955, 1.0388633331418984),
    CurvePoint(0.96, 1.0871883573850478),
    CurvePoint(0.965, 1.1552120359501035),
    CurvePoint(0.97, 1.2485807759957321),
    CurvePoint(0.9725, 1.3090333065057616),
    CurvePoint(0.975, 1.3807102743105126),
    CurvePoint(0.9775, 1.4664726399289512),
    CurvePoint(0.98, 1.5702410055532239),
    CurvePoint(0.9825, 1.697536248647543),
    CurvePoint(0.985, 1.8563887693647105),
    CurvePoint(0.9875, 2.058947159052738),
    CurvePoint(0.99, 2.324506282149922),
    CurvePoint(0.99125, 2.4902905794106913),
    CurvePoint(0.9925, 2.685667856592722),
    CurvePoint(0.99375, 2.9190155639254955),
    CurvePoint(0.995, 3.2022017597337955),
    CurvePoint(0.99625, 3.5526145337555373),
    CurvePoint(0.9975, 3.996793606763322),
    CurvePoint(0.99825, 4.325027383589547),
    CurvePoint(0.999, 4.715470646416203),
    CurvePoint(0.9995, 5.019543595874787),
    CurvePoint(1, 5.367394282890631),
]

def get_modifier(accuracy: float) -> float:
    accuracy = clamp(accuracy, 0, 100) / 100

    if accuracy <= 0:
        return 0

    if accuracy >= 1:
        return curve_points[-1].getMultiplier()

    for i in range(len(curve_points) - 1):
        p = curve_points[i]
        n = curve_points[i + 1]

        if p.getAcc() <= accuracy <= n.getAcc():
            t = (accuracy - p.getAcc()) / (n.getAcc() - p.getAcc())
            return lerp(p.getMultiplier(), n.getMultiplier(), t)

    return 0


def get_pp(stars: float, accuracy: float) -> float:
    if accuracy <= 1:
        accuracy *= 100

    base_pp = stars * STAR_MULTIPLIER
    return get_modifier(accuracy) * base_pp


def get_total_weighted_pp(pp_array: List[float], start_idx: int = 0) -> float:
    return sum(
        math.pow(WEIGHT_COEFFICIENT, idx + start_idx) * pp
        for idx, pp in enumerate(pp_array)
    )


def calc_raw_pp_at_idx(bottom_scores: List[float], idx: int, expected: float) -> float:
    old_bottom = get_total_weighted_pp(bottom_scores, idx)
    new_bottom = get_total_weighted_pp(bottom_scores, idx + 1)

    return (expected + old_bottom - new_bottom) / math.pow(WEIGHT_COEFFICIENT, idx)


def calc_raw_pp_for_expected_pp(scores_pps: List[float], expected_pp: float = 1) -> float:
    left = 0
    right = len(scores_pps) - 1
    boundary_idx = -1

    while left <= right:
        mid = (left + right) // 2
        bottom_slice = scores_pps[mid:]

        bottom_pp = get_total_weighted_pp(bottom_slice, mid)

        modified_slice = bottom_slice.copy()
        modified_slice.insert(0, scores_pps[mid])

        modified_pp = get_total_weighted_pp(modified_slice, mid)
        diff = modified_pp - bottom_pp

        if diff > expected_pp:
            boundary_idx = mid
            left = mid + 1
        else:
            right = mid - 1

    if boundary_idx == -1:
        return calc_raw_pp_at_idx(scores_pps, 0, expected_pp)

    return calc_raw_pp_at_idx(
        scores_pps[boundary_idx + 1:],
        boundary_idx + 1,
        expected_pp
    )


def get_raw_pp_for_weighted_pp_gain(scores_pps: List[float], expected_pp: float) -> float:
    if not scores_pps:
        return expected_pp

    new_scores = scores_pps.copy()
    insert_idx = next((i for i, pp in enumerate(new_scores) if expected_pp > pp), len(new_scores))
    new_scores.insert(insert_idx, expected_pp)

    old_total = get_total_weighted_pp(scores_pps)
    new_total = get_total_weighted_pp(new_scores)

    return new_total - old_total


"""pp = get_pp(stars=8.5, accuracy=97.88)
print(pp)

print(get_total_weighted_pp([
    100,
    100
]))

scores = [450, 420, 400, 380, 300, 1200]
raw_needed = calc_raw_pp_for_expected_pp(scores, expected_pp=5)
print(raw_needed)"""