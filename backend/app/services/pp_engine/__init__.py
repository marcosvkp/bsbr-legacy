"""Motor de PP do BSBR v2 — pacote puro (stdlib apenas, sem I/O).

Contract público consumido pelas demais fases:

- ``STAR_MULTIPLIER``, ``WEIGHT_COEFFICIENT``, ``CALIBRATION_ACC``
- ``get_modifier(acc_fraction)``
- ``get_pp(stars, accuracy)``
- ``decompose_pp(total_stars, accuracy, share_acc, share_tech, share_speed)``
- ``weighted_pp(pps, coefficient=WEIGHT_COEFFICIENT)``
- ``raw_pp_for_expected_gain(scores_pps, expected_pp=1.0)``
"""

from .curve import (
    CALIBRATION_ACC,
    STAR_MULTIPLIER,
    WEIGHT_COEFFICIENT,
    get_modifier,
)
from .calculator import (
    calc_raw_pp_at_idx,
    calc_raw_pp_for_expected_pp,
    get_raw_pp_for_weighted_pp_gain,
)
from .aggregate import weighted_pp
from .pp import SubPP, decompose_pp, get_pp

#: Alias do contract para a calculadora +1pp.
raw_pp_for_expected_gain = calc_raw_pp_for_expected_pp

__all__ = [
    "STAR_MULTIPLIER",
    "WEIGHT_COEFFICIENT",
    "CALIBRATION_ACC",
    "get_modifier",
    "get_pp",
    "decompose_pp",
    "SubPP",
    "weighted_pp",
    "raw_pp_for_expected_gain",
    "calc_raw_pp_at_idx",
    "calc_raw_pp_for_expected_pp",
    "get_raw_pp_for_weighted_pp_gain",
]
