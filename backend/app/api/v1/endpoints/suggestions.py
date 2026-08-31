"""Sugestões de mapas por jogadores logados (login Steam).

POST cria uma sugestão pending (sem rodar o ML — só metadata do BeatSaver);
o jogador tem no máximo 3 ativas. Admin revisa em ``/admin/suggestions``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_user
from app.core.db import get_db
from app.models import MapSuggestion, MapSuggestionStatus
from app.services.suggestions import (
    count_pending,
    duplicate_pending,
    fetch_metadata_light,
    ip_can_suggest,
    map_is_ranked,
    normalize_beat_saver_source,
)

router = APIRouter()

MAX_PENDING_PER_PLAYER = 3


class SuggestRequest(BaseModel):
    source: str
    note: str | None = None


def _item(s: MapSuggestion) -> dict:
    return {
        "id": s.id,
        "hash": s.hash,
        "beatsaver_id": s.beatsaver_id,
        "name": s.name,
        "mapper": s.mapper,
        "bpm": s.bpm,
        "cover_url": s.cover_url,
        "note": s.note,
        "status": s.status.value,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.post("/suggestions", status_code=201)
async def create_suggestion(
    body: SuggestRequest,
    request: Request,
    ss_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ip = request.client.host if request.client else "unknown"
    if not await ip_can_suggest(ip):
        raise HTTPException(status_code=429, detail="limite de sugestões por hora excedido")

    try:
        source = normalize_beat_saver_source(body.source)
    except ValueError:
        raise HTTPException(status_code=422, detail="source inválido (use id, hash ou URL do BeatSaver)")

    if await count_pending(db, ss_id) >= MAX_PENDING_PER_PLAYER:
        raise HTTPException(status_code=422, detail="limite de 3 sugestões ativas")

    metadata = await fetch_metadata_light(source)
    song_hash = metadata.get("hash")
    if not song_hash:
        raise HTTPException(status_code=422, detail="mapa não encontrado no BeatSaver")

    if await map_is_ranked(db, song_hash):
        raise HTTPException(status_code=422, detail="mapa já está rankeado")

    if await duplicate_pending(db, ss_id, song_hash):
        raise HTTPException(status_code=409, detail="você já sugeriu esse mapa")

    suggestion = MapSuggestion(
        ss_id=ss_id,
        hash=song_hash,
        beatsaver_id=metadata.get("beatsaver_id"),
        name=metadata["name"],
        song_author=metadata.get("song_author"),
        mapper=metadata.get("mapper"),
        bpm=metadata.get("bpm"),
        cover_url=metadata.get("cover_url"),
        note=(body.note or "").strip()[:280] or None,
        status=MapSuggestionStatus.PENDING,
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    return _item(suggestion)


@router.get("/suggestions/me")
async def my_suggestions(
    ss_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    where = MapSuggestion.ss_id == ss_id
    total = (await db.scalar(select(func.count()).select_from(MapSuggestion).where(where))) or 0
    active = (
        await db.scalar(
            select(func.count()).select_from(MapSuggestion).where(
                where, MapSuggestion.status == MapSuggestionStatus.PENDING
            )
        )
    ) or 0
    rows = (
        await db.scalars(
            select(MapSuggestion)
            .where(where)
            .order_by(MapSuggestion.created_at.desc(), MapSuggestion.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "active_count": active,
        "max_active": MAX_PENDING_PER_PLAYER,
        "total": total,
        "page": offset // limit,
        "page_size": limit,
        "items": [_item(s) for s in rows],
    }
