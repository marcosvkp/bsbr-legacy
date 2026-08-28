"""Agregação ponderada dos scores do jogador (Plan.md §3.3).

    playerPP_x = sum(subPP_x_i * 0.965^i), i = posição após ordenar por totalPP desc.

Os componentes agregam separadamente com a MESMA ordem (totalPP desc), então a
soma das partes reconstrói o PP geral do jogador.
"""

from __future__ import annotations

from .curve import WEIGHT_COEFFICIENT  # noqa: F401  (reexportado p/ conveniência)
from .pp import SubPP


def weighted_pp(pps: list[float], coefficient: float = WEIGHT_COEFFICIENT) -> float:
    """Soma ponderada ``sum(pp_i * coefficient^i)`` com pps ordenado desc.

    A ordem de entrada é irrelevante: os melhores scores (maior pp) recebem os
    maiores pesos. Idêntico ao ``get_total_weighted_pp`` do legado sobre a
    lista já ordenada.
    """
    return sum(
        coefficient**idx * pp for idx, pp in enumerate(sorted(pps, reverse=True))
    )


_COMPONENT_KEYS = ("pp_acc", "pp_tech", "pp_speed")


def aggregate_components(scores: list[SubPP]) -> dict[str, float]:
    """Agrega uma lista de sub-PPs de scores num resumo do jogador.

    Cada score é um ``SubPP`` (saída de ``decompose_pp``). Os scores são
    ordenados por ``pp_total`` desc (mesma ordem do ranking geral) e cada
    componente é agregado com o mesmo peso 0.965^i.

    Retorna ``{"pp_total", "pp_acc", "pp_tech", "pp_speed"}`` onde
    ``pp_acc + pp_tech + pp_speed == pp_total`` (a menos de erro de ponto
    flutuante).
    """
    ordered = sorted(scores, key=lambda s: s["pp_total"], reverse=True)
    result = {key: weighted_pp([s[key] for s in ordered]) for key in _COMPONENT_KEYS}
    result["pp_total"] = weighted_pp([s["pp_total"] for s in ordered])
    return result


__all__ = ["weighted_pp", "aggregate_components"]
