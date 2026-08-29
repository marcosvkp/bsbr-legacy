"""Persistência de scores ao vivo — mesmo padrão de upsert do sync.

Um score ao vivo só é persistido se a dificuldade for conhecida no banco
(match por ss_leaderboard_id). Players desconhecidos são criados com o nome
do payload (o sync completo preenche country/avatar depois).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Difficulty, Map, MapStatus, Player, Score
from app.services.pp_engine import decompose_pp

from .messages import LiveScore

logger = logging.getLogger(__name__)


async def persist_live_score(session: AsyncSession, live: LiveScore) -> dict | None:
    """Upsert de um score ao vivo; None se fora do escopo do feed.

    O feed "Ao Vivo" só aceita jogadas de jogadores BR em dificuldades
    rankeadas: país do payload deve ser BR e o mapa precisa ter status RANKED
    (candidatos/qualificados e jogadores de outros países ficam fora).
    """
    if (live.player_country or "").upper() != "BR":
        return {"ignored": "not_br"}

    difficulty = (
        await session.scalars(
            select(Difficulty)
            .join(Map, Difficulty.map_id == Map.id)
            .options(joinedload(Difficulty.map))
            .where(Difficulty.ss_leaderboard_id == live.leaderboard_id)
            .where(Map.status == MapStatus.RANKED)
            .where(Difficulty.is_ranked.is_(True))
        )
    ).first()
    if difficulty is None:
        return {"ignored": "not_ranked"}

    player = (
        await session.scalars(select(Player).where(Player.ss_id == live.player_id))
    ).first()
    if player is None:
        player = Player(
            ss_id=live.player_id,
            name=live.player_name or live.player_id,
            country=live.player_country,
        )
        session.add(player)
        await session.flush()

    time_set = live.time_set
    existing = (
        await session.scalars(
            select(Score).where(
                Score.player_id == player.id,
                Score.difficulty_id == difficulty.id,
            )
        )
    ).first()

    is_new = existing is None
    if is_new:
        existing = Score(player_id=player.id, difficulty_id=difficulty.id, time_set=time_set)
        session.add(existing)
    else:
        # mesmo jogador na mesma dificuldade: o score ao vivo (mais recente) substitui
        existing.time_set = time_set

    existing.score = live.score
    existing.acc = live.acc
    existing.modifiers = live.mods or None
    existing.full_combo = live.full_combo
    existing.leaderboard_rank = live.rank

    # PP calculado como no sync (sub-stars da dificuldade); fallback pp do feed
    if difficulty.total_stars and live.acc is not None:
        shares = _shares_of(difficulty)
        sub = decompose_pp(
            float(difficulty.total_stars),
            live.acc * 100,
            share_acc=shares[0],
            share_tech=shares[1],
            share_speed=shares[2],
        )
        existing.pp = sub["pp_total"]
        existing.pp_acc = sub["pp_acc"]
        existing.pp_tech = sub["pp_tech"]
        existing.pp_speed = sub["pp_speed"]
    elif live.pp is not None:
        existing.pp = live.pp

    # 1 score por (player, difficulty): remove os anteriores do mesmo jogador.
    # flush antes garante id real do score atual (Score.id != None vira
    # "IS NOT NULL" no SQL e deletaria tudo).
    await session.flush()
    await session.execute(
        delete(Score).where(
            Score.player_id == player.id,
            Score.difficulty_id == difficulty.id,
            Score.id != existing.id,
        )
    )

    await session.commit()
    result = {"inserted" if is_new else "updated": existing.id}
    result["pp"] = existing.pp
    result["acc"] = existing.acc
    # Enriquecimento para o feed: hash/nome/capa do catálogo (o song_hash do
    # payload do ScoreSaber pode não bater com Map.hash) e avatar do jogador.
    result["map_hash"] = difficulty.map.hash
    result["map_name"] = difficulty.map.name
    result["cover_url"] = difficulty.map.cover_url
    result["avatar_url"] = player.avatar_url
    result["difficulty_name"] = difficulty.name
    return result


def _shares_of(difficulty: Difficulty) -> tuple[float, float, float]:
    total = (
        float(difficulty.acc_stars or 0.0)
        + float(difficulty.tech_stars or 0.0)
        + float(difficulty.speed_stars or 0.0)
    )
    if total <= 0:
        return 1.0, 0.0, 0.0
    return (
        float(difficulty.acc_stars or 0.0) / total,
        float(difficulty.tech_stars or 0.0) / total,
        float(difficulty.speed_stars or 0.0) / total,
    )
