"""Curva empírica expected-acc × estrelas, derivada do dataset de referência.

O `star_reference` guarda, por fonte (scoresaber/beatleader), a acc mediana
dos top scores de leaderboards rankeados. `load_curve()` agrega essas bandas
em um cache de processo; `expected_median_acc()` (em algorithm.py) consulta a
curva da fonte do mapa e cai para a fórmula do legado onde a banda é esparsa
ou o dataset não foi coletado.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StarReference

BAND_SIZE = 0.5
DEFAULT_SOURCE = "scoresaber"
# Amostra mínima de leaderboards por banda para a banda contar na curva;
# abaixo disso a banda é considerada esparsa e o reweight usa a fórmula.
MIN_SAMPLES_PER_BAND = 5

_CURVE: dict[str, dict[float, float]] = {}  # source -> banda (0,5★) -> acc mediana


def band_for(stars: float) -> float:
    """Banda de 0,5★ da estrela (5.3 → 5.5, 5.2 → 5.0)."""
    return round(stars / BAND_SIZE) * BAND_SIZE


def empirical_expected_acc(stars: float, source: str = DEFAULT_SOURCE) -> float | None:
    """Acc empírica da banda; None se a banda não está na curva carregada."""
    return _CURVE.get(source, {}).get(band_for(stars))


def reset_curve() -> None:
    """Limpa o cache (testes / reload do dataset)."""
    _CURVE.clear()


async def load_curve(session: AsyncSession, *, refresh: bool = False) -> None:
    """Agrega `star_reference` na curva por fonte/banda (mediana das medianas)."""
    if _CURVE and not refresh:
        return
    rows = (
        await session.scalars(
            select(StarReference).where(StarReference.median_top_acc.is_not(None))
        )
    ).all()
    by_band: dict[str, dict[float, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.sample_n is None or row.sample_n < MIN_SAMPLES_PER_BAND:
            continue
        by_band[row.source][band_for(row.stars)].append(float(row.median_top_acc))
    curve: dict[str, dict[float, float]] = {}
    for source, bands in by_band.items():
        source_curve: dict[float, float] = {}
        for band, accs in bands.items():
            source_curve[band] = statistics.median(accs)
        curve[source] = source_curve
    reset_curve()
    _CURVE.update(curve)
