"""Série de PP do jogador ao longo do tempo (progressão baseada nos scores).

Cada score rankeado tem ``time_set`` (quando foi jogado) e o PP calculado na
ingestão. Caminhando cronologicamente, inserimos cada score e recalculamos o
total ponderado do jogador (mesmo critério do ranking) — cada evento gera um
ponto (tempo, PP).

Como o sync mantém 1 score por (player, difficulty) (o mais recente substitui
o anterior), o ``time_set`` reflete a última vez que o score foi setado; a
série é uma aproximação do histórico real. Trechos sem dados (gaps grandes ou
a borda inicial sem scores) são interpolados linearmente e marcados como
``estimated`` — no gráfico ficam tracejados e o tooltip mostra "(estimado)".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Difficulty, Map, MapStatus, Player, Score
from app.services.pp_engine import weighted_pp

MIN_DAYS = 7
MAX_DAYS = 180
DEFAULT_DAYS = 180

#: Gaps entre eventos reais acima disso ganham amostras estimadas (tracejado).
ESTIMATE_GAP_DAYS = 14
#: Passo das amostras estimadas interpoladas dentro dos gaps.
ESTIMATE_SAMPLE_DAYS = 7


async def build_pp_history(
    session: AsyncSession,
    player: Player,
    days: int = DEFAULT_DAYS,
) -> dict:
    """Série (ts, pp) da progressão de PP do jogador em `days` (clamp 7..180)."""
    days = max(MIN_DAYS, min(MAX_DAYS, int(days)))
    now = _now()
    window_start = now - timedelta(days=days)

    rows = (
        (
            await session.execute(
                select(Score)
                .join(Difficulty, Score.difficulty_id == Difficulty.id)
                .join(Map, Difficulty.map_id == Map.id)
                .where(
                    Score.player_id == player.id,
                    Map.status == MapStatus.RANKED,
                    Difficulty.is_ranked.is_(True),
                    Score.pp.is_not(None),
                )
                .order_by(Score.time_set)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return {"ss_id": player.ss_id, "days": days, "now": now.isoformat(), "current_pp_total": None, "points": []}

    # Estado inicial: scores anteriores à janela já contavam no total do início.
    initial: list[dict] = []
    window_events: list[dict] = []
    for s in rows:
        entry = {"pp": float(s.pp), "pp_acc": s.pp_acc, "pp_tech": s.pp_tech, "pp_speed": s.pp_speed}
        if s.time_set is None or s.time_set < window_start:
            initial.append(entry)
        else:
            window_events.append((s.time_set, entry))

    inserted = list(initial)
    # (ts, totais, estimated) — o ponto 0 da borda sem scores é estimado (leading tracejado).
    real: list[tuple[datetime, dict, bool]] = []
    if initial:
        real.append((window_start, _totals(inserted), False))
    else:
        real.append(
            (window_start, {"pp_total": 0.0, "pp_acc": 0.0, "pp_tech": 0.0, "pp_speed": 0.0}, True)
        )

    # Eventos da janela: colapsa o mesmo dia (mantém o último do dia).
    prev_day: object | None = None
    for ts, entry in window_events:
        inserted.append(entry)
        if ts.date() == prev_day:
            real[-1] = (ts, _totals(inserted), False)
        else:
            real.append((ts, _totals(inserted), False))
        prev_day = ts.date()

    points: list[dict] = [
        {"ts": ts.isoformat(), "estimated": est, **totals} for ts, totals, est in real
    ]

    # Estimativas: interpola linearmente os gaps entre pontos (> 14 dias).
    if len(real) >= 2:
        interpolated: list[dict] = []
        for i in range(len(real) - 1):
            ts_prev, tot_prev, _ = real[i]
            ts_curr, tot_curr, _ = real[i + 1]
            gap = (ts_curr - ts_prev).days
            if gap > ESTIMATE_GAP_DAYS:
                step = timedelta(days=ESTIMATE_SAMPLE_DAYS)
                t = ts_prev + step
                while t < ts_curr:
                    frac = (t - ts_prev) / (ts_curr - ts_prev)
                    interpolated.append(
                        {
                            "ts": t.isoformat(),
                            "estimated": True,
                            "pp_total": _lerp(tot_prev["pp_total"], tot_curr["pp_total"], frac),
                            "pp_acc": _lerp(tot_prev["pp_acc"], tot_curr["pp_acc"], frac),
                            "pp_tech": _lerp(tot_prev["pp_tech"], tot_curr["pp_tech"], frac),
                            "pp_speed": _lerp(tot_prev["pp_speed"], tot_curr["pp_speed"], frac),
                        }
                    )
                    t += step
        if interpolated:
            points = _merge_interpolated(points, interpolated)

    # Ponto final "Agora" (real, sempre presente quando há scores).
    points.append(
        {
            "ts": now.isoformat(),
            "estimated": False,
            "pp_total": float(player.pp_total or 0.0),
            "pp_acc": float(player.pp_acc or 0.0),
            "pp_tech": float(player.pp_tech or 0.0),
            "pp_speed": float(player.pp_speed or 0.0),
        }
    )

    return {
        "ss_id": player.ss_id,
        "days": days,
        "now": now.isoformat(),
        "current_pp_total": float(player.pp_total) if player.pp_total is not None else None,
        "points": points,
    }


def _totals(scores: list[dict]) -> dict:
    """Totais ponderados no mesmo critério do ranking (weighted_pp por lista)."""
    return {
        "pp_total": weighted_pp([s["pp"] for s in scores]),
        "pp_acc": weighted_pp([s["pp_acc"] or 0.0 for s in scores]),
        "pp_tech": weighted_pp([s["pp_tech"] or 0.0 for s in scores]),
        "pp_speed": weighted_pp([s["pp_speed"] or 0.0 for s in scores]),
    }


def _lerp(a: float, b: float, frac: float) -> float:
    return a + (b - a) * frac


def _merge_interpolated(points: list[dict], interpolated: list[dict]) -> list[dict]:
    """Mistura as amostras estimadas com os pontos reais, ordenado por ts."""
    merged = {p["ts"]: p for p in points}
    for p in interpolated:
        merged.setdefault(p["ts"], p)
    return [merged[ts] for ts in sorted(merged)]


def _now() -> datetime:
    # time_set é naive-UTC no banco (sync normaliza); manter naive para comparar.
    return datetime.now(timezone.utc).replace(tzinfo=None)
