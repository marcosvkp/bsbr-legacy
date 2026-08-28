"""PP total e decomposição sub-PP (Plan.md §3.2).

O PP total usa a curva exata do legado (``curve.get_modifier``); os sub-PPs
são uma DECOMPOSIÇÃO do total, não uma fórmula nova:

    g_acc(acc)   = mod(acc) / mod(0.95)      # herda o comportamento BSBR
    g_tech(acc)  = exp(1.9 * (acc - 0.95))   # tech explode com acc alta
    g_speed(acc) = exp(1.2 * (acc - 0.95))   # speed sensível, menos que tech
    w_x          = share_x * g_x(acc)
    subPP_x      = totalPP * w_x / sum(w)    # normalização => sum(subPP) = totalPP

Em acc = 0.95 (calibração da curva, multiplicador 1.0), g_acc = 1.0 e os
sub-PPs saem exatamente proporcionais aos shares.
"""

from __future__ import annotations

import math

from .curve import CALIBRATION_ACC, STAR_MULTIPLIER, curve_calibration, get_modifier

#: Sub-PP retornado por ``decompose_pp``: chaves fixas, valores float.
SubPP = dict[str, float]

#: Sensibilidades dos estilos à acurácia (Plan.md §3.2).
TECH_SENSITIVITY = 1.9
SPEED_SENSITIVITY = 1.2


def get_pp(stars: float, accuracy: float) -> float:
    """PP de um score — IDÊNTICO ao ``get_pp`` legado.

    ``accuracy`` aceita 0..100 ou fração 0..1 (<= 1 é normalizado ×100).
    Fórmula: ``mod(acc) * stars * STAR_MULTIPLIER``.
    """
    if accuracy <= 1:
        accuracy *= 100

    base_pp = stars * STAR_MULTIPLIER
    return get_modifier(accuracy) * base_pp


def decompose_pp(
    total_stars: float,
    accuracy: float,
    share_acc: float,
    share_tech: float,
    share_speed: float,
) -> SubPP:
    """Decompõe o PP total em ``pp_acc / pp_tech / pp_speed``.

    - ``total_stars``: stars totais da dificuldade (> 0).
    - ``accuracy``: fração 0..1 (valores > 1 são tratados como percentual e
      divididos por 100).
    - shares: pesos de sub-stars (acc/tech/speed); valores negativos são
      rejeitados; a soma é normalizada internamente (não precisa somar 1).

    Garantia: ``pp_acc + pp_tech + pp_speed == pp_total`` (a menos de erro de
    ponto flutuante), pois a soma dos pesos é usada como normalizador.
    """
    if not total_stars > 0:
        raise ValueError("total_stars deve ser > 0")

    if accuracy > 1:
        accuracy /= 100

    shares = (share_acc, share_tech, share_speed)
    if any(s < 0 for s in shares):
        raise ValueError("shares devem ser >= 0")

    total_pp = get_pp(total_stars, accuracy)

    weights = (
        share_acc * curve_calibration(accuracy),
        share_tech * math.exp(TECH_SENSITIVITY * (accuracy - CALIBRATION_ACC)),
        share_speed * math.exp(SPEED_SENSITIVITY * (accuracy - CALIBRATION_ACC)),
    )
    weight_sum = sum(weights)

    if weight_sum == 0:
        # Todos os shares zerados: sem informação de estilo, devolve tudo em acc.
        return {
            "pp_total": total_pp,
            "pp_acc": total_pp,
            "pp_tech": 0.0,
            "pp_speed": 0.0,
        }

    return {
        "pp_total": total_pp,
        "pp_acc": total_pp * weights[0] / weight_sum,
        "pp_tech": total_pp * weights[1] / weight_sum,
        "pp_speed": total_pp * weights[2] / weight_sum,
    }


__all__ = [
    "SubPP",
    "get_pp",
    "decompose_pp",
]
