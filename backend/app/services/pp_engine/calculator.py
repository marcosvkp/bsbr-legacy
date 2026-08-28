"""Calculadora "+1pp" — porte das funções de ganho do legado.

Responde: quanto PP cru (raw) um novo score precisa valer para adicionar
``expected_pp`` ao PP ponderado do jogador, dado seus PPs atuais.

Funções portadas 1:1 de ``references/bsbr/app/scorecalc/__init__.py``:
``calc_raw_pp_at_idx``, ``calc_raw_pp_for_expected_pp`` e
``get_raw_pp_for_weighted_pp_gain``.
"""

from __future__ import annotations

import math

from .curve import WEIGHT_COEFFICIENT


def calc_raw_pp_at_idx(
    bottom_scores: list[float], idx: int, expected: float
) -> float:
    """PP cru necessário na posição ``idx`` para ganhar ``expected`` ali.

    Inserir um score na posição ``idx`` desloca todos os scores abaixo uma
    casa (peso extra fator 0.965). A diferença old/new bottom é o ganho
    "grátis" do deslocamento; o restante vem do novo score.
    """
    old_bottom = _weighted_from(bottom_scores, idx)
    new_bottom = _weighted_from(bottom_scores, idx + 1)

    return (expected + old_bottom - new_bottom) / math.pow(WEIGHT_COEFFICIENT, idx)


def calc_raw_pp_for_expected_pp(
    scores_pps: list[float], expected_pp: float = 1
) -> float:
    """Menor PP cru que, inserido no lugar certo, adiciona ``expected_pp``.

    Busca binária pela fronteira de inserção mais fundo (posição mais baixa)
    que ainda produz ganho > expected_pp sozinho; nessa região o custo raw é
    dominado pelo próprio score, calculado via ``calc_raw_pp_at_idx``.
    """
    left = 0
    right = len(scores_pps) - 1
    boundary_idx = -1

    while left <= right:
        mid = (left + right) // 2
        bottom_slice = scores_pps[mid:]

        bottom_pp = _weighted_from(bottom_slice, mid)

        modified_slice = bottom_slice.copy()
        modified_slice.insert(0, scores_pps[mid])

        modified_pp = _weighted_from(modified_slice, mid)
        diff = modified_pp - bottom_pp

        if diff > expected_pp:
            boundary_idx = mid
            left = mid + 1
        else:
            right = mid - 1

    if boundary_idx == -1:
        return calc_raw_pp_at_idx(scores_pps, 0, expected_pp)

    return calc_raw_pp_at_idx(
        scores_pps[boundary_idx + 1 :],
        boundary_idx + 1,
        expected_pp,
    )


def get_raw_pp_for_weighted_pp_gain(
    scores_pps: list[float], expected_pp: float
) -> float:
    """Ganho real de PP ponderado se ``expected_pp`` fosse alcançado agora.

    Complemento da calculadora: dado um score de valor ``expected_pp``,
    retorna quanto ele efetivamente soma ao total ponderado atual (0 se o
    jogador já tem scores melhores que o empurram para posições sem peso).
    """
    if not scores_pps:
        return expected_pp

    new_scores = scores_pps.copy()
    insert_idx = next(
        (i for i, pp in enumerate(new_scores) if expected_pp > pp), len(new_scores)
    )
    new_scores.insert(insert_idx, expected_pp)

    old_total = _weighted_from(scores_pps, 0)
    new_total = _weighted_from(new_scores, 0)

    return new_total - old_total


def _weighted_from(pp_array: list[float], start_idx: int = 0) -> float:
    """``get_total_weighted_pp`` do legado: pesos 0.965^(idx + start_idx)."""
    return sum(
        math.pow(WEIGHT_COEFFICIENT, idx + start_idx) * pp
        for idx, pp in enumerate(pp_array)
    )


__all__ = [
    "calc_raw_pp_at_idx",
    "calc_raw_pp_for_expected_pp",
    "get_raw_pp_for_weighted_pp_gain",
]
