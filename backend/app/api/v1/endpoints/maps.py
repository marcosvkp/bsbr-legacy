"""GET /maps e /maps/{hash} — catálogo rankeado com decomposição de stars."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache
from app.core.db import get_db
from app.models import Difficulty, Map, MapStatus, Player, RatingHistory, Score

router = APIRouter()

_DIFF_ORDER = {"ExpertPlus": 4, "Expert": 3, "Hard": 2, "Normal": 1, "Easy": 0}


def _map_summary(m: Map) -> dict:
    diffs = sorted(
        (
            d
            for d in m.difficulties
            if d.characteristic == "Standard" and d.total_stars is not None and d.is_ranked
        ),
        key=lambda d: d.total_stars or 0,
        reverse=True,
    )
    return {
        "hash": m.hash,
        "beatsaver_id": m.beatsaver_id,
        "name": m.name,
        "song_author": m.song_author,
        "mapper": m.mapper,
        "bpm": m.bpm,
        "cover_url": m.cover_url,
        "tags": m.tags,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "difficulties": [
            {
                "name": d.name,
                "total_stars": d.total_stars,
                "acc_stars": d.acc_stars,
                "tech_stars": d.tech_stars,
                "speed_stars": d.speed_stars,
                "style_tags": d.style_tags,
                "max_pp": round((d.total_stars or 0.0) * 42.117208413, 2),
            }
            for d in diffs
        ],
    }


def _escape_like(value: str) -> str:
    """Escapa curingas do LIKE para busca literal (%, _, \\)."""
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def _maps_filters(q: str | None, min_stars: float | None) -> list:
    filters = [Map.status == MapStatus.RANKED]
    if q:
        pattern = f"%{_escape_like(q)}%"
        filters.append(
            or_(
                Map.name.ilike(pattern, escape="\\"),
                Map.mapper.ilike(pattern, escape="\\"),
            )
        )
    if min_stars is not None:
        max_stars = (
            select(func.max(Difficulty.total_stars))
            .where(Difficulty.map_id == Map.id, Difficulty.is_ranked.is_(True))
            .scalar_subquery()
        )
        filters.append(max_stars >= min_stars)
    return filters


@router.get("/maps")
async def list_maps(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    sort: str = Query("stars", pattern="^(stars|recent|name)$"),
    q: str | None = Query(None, max_length=80, description="Busca por nome do mapa ou mapper"),
    min_stars: float | None = Query(None, ge=0, le=20, description="Filtra mapas com pelo menos N estrelas"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cache_key = f"maps:{sort}:{page}:{page_size}:{q or ''}:{min_stars or 0}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    filters = _maps_filters(q, min_stars)
    total = (
        await db.execute(select(func.count()).select_from(Map).where(*filters))
    ).scalar_one()

    order = {
        # Ordena por melhor dificuldade: subquery do max(total_stars)
        "stars": (
            select(func.max(Difficulty.total_stars))
            .where(Difficulty.map_id == Map.id, Difficulty.is_ranked.is_(True))
            .scalar_subquery()
            .desc()
        ),
        "recent": Map.created_at.desc(),
        "name": Map.name.asc(),
    }[sort]

    rows = (
        (
            await db.execute(
                select(Map)
                .where(*filters)
                .options(selectinload(Map.difficulties))
                .order_by(order)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )

    payload = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [_map_summary(m) for m in rows],
    }
    await cache.set_json(cache_key, payload, ttl=60)
    return payload


@router.get("/maps/qualification")
async def list_qualification(db: AsyncSession = Depends(get_db)) -> dict:
    """Fila pública de qualificação: mapas sugeridos (candidatos) e qualificados."""
    rows = (
        (
            await db.execute(
                select(Map)
                .where(Map.status.in_([MapStatus.CANDIDATE, MapStatus.QUALIFIED]))
                .options(selectinload(Map.difficulties))
                .order_by(Map.id.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": m.id,
                "hash": m.hash,
                "name": m.name,
                "mapper": m.mapper,
                "bpm": m.bpm,
                "cover_url": m.cover_url,
                "status": m.status.value,
                "submitted_by": m.submitted_by,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "difficulties": [
                    {
                        "name": d.name,
                        "total_stars": d.total_stars,
                        "ss_leaderboard_id": d.ss_leaderboard_id,
                        "is_ranked": d.is_ranked,
                    }
                    for d in sorted(
                        (d for d in m.difficulties if d.characteristic == "Standard"),
                        key=lambda d: _DIFF_ORDER.get(d.name, -1),
                        reverse=True,
                    )
                ],
            }
            for m in rows
        ],
    }


@router.get("/leaderboard/{map_hash}")
async def get_leaderboard_by_difficulty(
    map_hash: str,
    difficulty: str = Query(..., description="Nome exato da dificuldade (ex. ExpertPlus)"),
    characteristic: str = Query("Standard"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, description="Deslocamento para paginação (top 10 por página)"),
    player_id: str | None = Query(
        None, description="ss_id do jogador local (destaca a própria linha no painel)"
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Top scores de uma dificuldade específica — usado pelo plugin in-game.

    O plugin manda o hash em MAIÚSCULAS (vem de `custom_level_<HASH>`); aqui
    normalizamos para lowercase. O `player` (rank do próprio jogador) é
    calculado por request e não entra no cache. `offset`/`total`/`has_more`
    alimentam as setas de paginação do painel (top 10 por página).
    """
    hash_key = map_hash.lower()
    cache_key = f"lb:{hash_key}:{characteristic}:{difficulty}:{limit}:{offset}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        payload = cached
    else:
        d = (
            await db.scalars(
                select(Difficulty)
                .join(Map, Difficulty.map_id == Map.id)
                .where(
                    Map.hash == hash_key,
                    Map.status == MapStatus.RANKED,
                    Difficulty.is_ranked.is_(True),
                    Difficulty.characteristic == characteristic,
                    Difficulty.name == difficulty,
                )
            )
        ).first()
        if d is None:
            raise HTTPException(status_code=404, detail="leaderboard não encontrado")
        m = await db.get(Map, d.map_id)

        total = (
            await db.scalars(
                select(func.count()).select_from(Score).where(Score.difficulty_id == d.id)
            )
        ).one()

        rows = (
            (
                await db.execute(
                    select(Score, Player.name, Player.ss_id)
                    .join(Player, Score.player_id == Player.id)
                    .where(Score.difficulty_id == d.id)
                    .order_by(Score.pp.desc().nulls_last())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .all()
        )

        payload = {
            "hash": m.hash,
            "map_name": m.name,
            "difficulty": d.name,
            "characteristic": d.characteristic,
            "total_stars": d.total_stars,
            "difficulty_id": d.id,
            "total": total,
            "has_more": offset + len(rows) < total,
            "scores": [
                {
                    "rank": offset + idx + 1,
                    "player_name": name,
                    "player_ss_id": ss_id,
                    "score": s.score,
                    "acc": s.acc,
                    "pp": round(s.pp or 0.0, 2),
                    "full_combo": s.full_combo,
                    "modifiers": s.modifiers,
                    "leaderboard_rank": s.leaderboard_rank,
                }
                for idx, (s, name, ss_id) in enumerate(rows)
            ],
            "player": None,
        }
        await cache.set_json(cache_key, payload, ttl=60)

    # rank 1-based do próprio jogador nessa difficulty (fora do cache)
    if player_id:
        difficulty_id = payload.get("difficulty_id")
        player = (await db.scalars(select(Player).where(Player.ss_id == player_id))).first()
        if player is not None and difficulty_id is not None:
            own = (
                await db.scalars(
                    select(Score).where(
                        Score.difficulty_id == difficulty_id,
                        Score.player_id == player.id,
                    )
                )
            ).first()
            if own is not None and own.pp is not None:
                higher = (
                    await db.scalars(
                        select(func.count())
                        .select_from(Score)
                        .where(Score.difficulty_id == difficulty_id, Score.pp > own.pp)
                    )
                ).one()
                payload["player"] = {
                    "ss_id": player.ss_id,
                    "name": player.name,
                    "rank": higher + 1,
                }
    return payload


@router.get("/maps/{map_hash}")
async def get_map(map_hash: str, db: AsyncSession = Depends(get_db)) -> dict:
    cache_key = f"map:{map_hash}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    m = (
        await db.scalars(
            select(Map).where(Map.hash == map_hash).options(selectinload(Map.difficulties))
        )
    ).first()
    if m is None:
        raise HTTPException(status_code=404, detail="mapa não encontrado")

    difficulties = [
        d for d in m.difficulties if d.characteristic == "Standard" and d.is_ranked
    ]
    difficulty_ids = [d.id for d in difficulties] or [0]

    top_scores = (
        (
            await db.execute(
                select(Score, Player.name, Difficulty.name, Player.ss_id, Player.avatar_url)
                .join(Player, Score.player_id == Player.id)
                .join(Difficulty, Score.difficulty_id == Difficulty.id)
                .where(Difficulty.map_id == m.id, Difficulty.is_ranked.is_(True))
                .order_by(Score.pp.desc().nulls_last())
                .limit(50)
            )
        )
        .all()
    )

    history = (
        (
            await db.scalars(
                select(RatingHistory)
                .where(RatingHistory.difficulty_id.in_(difficulty_ids))
                .order_by(RatingHistory.applied_at.desc())
                .limit(10)
            )
        )
        .all()
    )

    diff_names = {d.id: d.name for d in difficulties}

    payload = {
        **_map_summary(m),
        "difficulties_detail": [
            {
                "name": d.name,
                "njs": d.njs,
                "max_score": d.max_score,
                "total_stars": d.total_stars,
                "acc_stars": d.acc_stars,
                "tech_stars": d.tech_stars,
                "speed_stars": d.speed_stars,
                "style_tags": d.style_tags,
                "ranked_at": d.ranked_at.isoformat() if d.ranked_at else None,
            }
            for d in sorted(difficulties, key=lambda x: (_DIFF_ORDER.get(x.name, 99), x.name))
        ],
        "leaderboard": [
            {
                "player_name": name,
                "player_ss_id": ss_id,
                "avatar_url": avatar_url,
                "difficulty": diff_name,
                "score": s.score,
                "acc": s.acc,
                "full_combo": s.full_combo,
                "pp": round(s.pp or 0.0, 2),
                "pp_acc": round(s.pp_acc or 0.0, 2),
                "pp_tech": round(s.pp_tech or 0.0, 2),
                "pp_speed": round(s.pp_speed or 0.0, 2),
                "leaderboard_rank": s.leaderboard_rank,
            }
            for s, name, diff_name, ss_id, avatar_url in top_scores
        ],
        "rating_history": [
            {
                "difficulty_id": h.difficulty_id,
                "difficulty_name": diff_names.get(h.difficulty_id),
                "total_before": h.total_stars_before,
                "total_after": h.total_stars_after,
                "acc_before": h.acc_stars_before,
                "acc_after": h.acc_stars_after,
                "tech_before": h.tech_stars_before,
                "tech_after": h.tech_stars_after,
                "speed_before": h.speed_stars_before,
                "speed_after": h.speed_stars_after,
                "reason": h.reason,
                "applied_by": h.applied_by,
                "applied_at": h.applied_at.isoformat() if h.applied_at else None,
            }
            for h in history
        ],
    }
    await cache.set_json(cache_key, payload, ttl=60)
    return payload
