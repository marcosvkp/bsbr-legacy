"""Recálculo de PP agregado e rankings (Plan.md §3.3).

- PP do jogador = Σ ppᵢ × 0.965ⁱ sobre scores de mapas RANKED, ordenados por pp desc.
- Componentes (pp_acc/pp_tech/pp_speed) agregam na MESMA ordem (por pp_total desc),
  igual ao comportamento do BeatLeader.
- Rank = posição por pp_total. Snapshots semanais idempotentes por (week, player).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Difficulty, Map, MapStatus, Player, RankSnapshot, Score
from app.services.pp_engine import weighted_pp


def medal_from_rank(rank: int) -> int:
    """Medalhas do legado: 1º=10, 2º=8, 3º=6, 4º=5, 5º=4, 6º=3, 7º=2, demais=1."""
    table = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2}
    return table.get(rank, 1)


@dataclass
class RankingSummary:
    players_updated: int
    week: str


async def recompute_all_rankings(session: AsyncSession) -> RankingSummary:
    """Recalcula pp_total/componentes e rank de todos os players com score ranked."""
    rows = (
        await session.execute(
            select(Score, Player.id)
            .join(Player, Score.player_id == Player.id)
            .join(Difficulty, Score.difficulty_id == Difficulty.id)
            .join(Map, Difficulty.map_id == Map.id)
            .where(Map.status == MapStatus.RANKED, Difficulty.is_ranked.is_(True))
        )
    ).all()

    by_player: dict[int, list[Score]] = {}
    for score, player_id in rows:
        if score.pp is None:
            continue
        by_player.setdefault(player_id, []).append(score)

    ranked: list[tuple[float, int, float, float, float]] = []  # (pp_total, player_id, acc, tech, speed)
    for player_id, scores in by_player.items():
        scores.sort(key=lambda s: s.pp or 0.0, reverse=True)
        total = weighted_pp([s.pp for s in scores])
        acc = weighted_pp([s.pp_acc or 0.0 for s in scores])
        tech = weighted_pp([s.pp_tech or 0.0 for s in scores])
        speed = weighted_pp([s.pp_speed or 0.0 for s in scores])
        for player in await _players(session, [player_id]):
            player.pp_total = round(total, 4)
            player.pp_acc = round(acc, 4)
            player.pp_tech = round(tech, 4)
            player.pp_speed = round(speed, 4)
        ranked.append((total, player_id, acc, tech, speed))

    ranked.sort(reverse=True)
    for position, (total, player_id, *_rest) in enumerate(ranked, start=1):
        for player in await _players(session, [player_id]):
            player.rank = position

    await session.commit()
    return RankingSummary(players_updated=len(ranked), week=iso_week())


async def _players(session: AsyncSession, ids: list[int]) -> list[Player]:
    if not ids:
        return []
    return list((await session.scalars(select(Player).where(Player.id.in_(ids)))).all())


def iso_week(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


async def write_weekly_snapshot(session: AsyncSession, week: str | None = None) -> int:
    """Snapshot do ranking atual. Idempotente: substitui a semana existente."""
    week = week or iso_week()
    await session.execute(delete(RankSnapshot).where(RankSnapshot.week == week))
    players = (
        await session.scalars(select(Player).where(Player.rank.is_not(None)).order_by(Player.rank))
    ).all()
    for p in players:
        session.add(
            RankSnapshot(
                week=week,
                player_id=p.id,
                rank=p.rank,
                pp_total=p.pp_total,
                pp_acc=p.pp_acc,
                pp_tech=p.pp_tech,
                pp_speed=p.pp_speed,
            )
        )
    await session.commit()
    return len(players)


async def medals_for_player(session: AsyncSession, player_id: int) -> dict[str, int]:
    """Medalhas totais do jogador nos leaderboards rankeados (feature do legado).

    Usa a melhor posição de cada mapa/dificuldade (leaderboard_rank mínimo).
    """
    rows = (
        await session.execute(
            select(Score.difficulty_id, func.min(Score.leaderboard_rank).label("best"))
            .join(Difficulty, Score.difficulty_id == Difficulty.id)
            .join(Map, Difficulty.map_id == Map.id)
            .where(
                Score.player_id == player_id,
                Score.leaderboard_rank.is_not(None),
                Map.status == MapStatus.RANKED,
                Difficulty.is_ranked.is_(True),
            )
            .group_by(Score.difficulty_id)
        )
    ).all()
    bests = [int(best) for _, best in rows if best is not None]
    # Legado: só posições 1º–10º rendem medalha (8º/9º/10º = 1)
    scoring = [r for r in bests if r <= 10]
    return {
        "total": sum(medal_from_rank(r) for r in scoring),
        "maps_in_top10": len(scoring),
        "best_rank": min(bests) if bests else 0,
    }
