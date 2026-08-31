"""Service de sugestões de mapas (jogadores logados).

A sugestão NÃO roda o ML — só busca metadata leve do BeatSaver (nome,
capa, mapper, bpm) e valida que o mapa ainda não está rankeado. Limite:
3 sugestões pendentes por jogador (``pending``); aprovada vira um Map
candidate sem ML e recusada libera o slot.
"""

from __future__ import annotations

import asyncio
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import SlidingWindowLimiter
from app.models import Map, MapSuggestion, MapSuggestionStatus, MapStatus

# Rate-limit por IP: 10 POSTs de sugestão por hora (janela de 1h).
SUGGEST_IP_MAX = 10
SUGGEST_IP_PERIOD = 3600

MAX_PENDING_PER_PLAYER = 3

# Registry cacheia o limiter por IP para que o deque em memória (dev/testes)
# persista entre requests do mesmo IP.
_ip_limiters: dict[str, SlidingWindowLimiter] = {}

_SOURCE_URL_RE = re.compile(
    r"^https?://(?:www\.)?beatsaver\.com/(?:maps?|map)/([A-Za-z0-9]+)"
)


def _limiter_for(ip: str) -> SlidingWindowLimiter:
    limiter = _ip_limiters.get(ip)
    if limiter is None:
        limiter = SlidingWindowLimiter(f"suggest:{ip}", SUGGEST_IP_MAX, SUGGEST_IP_PERIOD)
        _ip_limiters[ip] = limiter
    return limiter


async def ip_can_suggest(ip: str) -> bool:
    """False se o IP estourou a janela de sugestões por hora."""
    return await _limiter_for(ip).try_acquire() == 0.0


def normalize_beat_saver_source(source: str) -> str:
    """Aceita ID curto, hash 40-hex ou URL do BeatSaver; devolve o ID/hash."""
    source = (source or "").strip()
    if not source:
        raise ValueError("source vazio")
    m = _SOURCE_URL_RE.match(source)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9]{1,64}", source):
        return source
    raise ValueError("source inválido")


async def fetch_metadata_light(source: str) -> dict:
    """Metadata do BeatSaver SEM o ML (bsbr_analyzer). Vazio se indisponível."""
    from bsbr_analyzer.beatsaver import fetch_map_metadata, map_hash, map_name_mapper

    try:
        metadata = await asyncio.to_thread(fetch_map_metadata, source)
    except Exception:
        return {}
    if not metadata:
        return {}
    versions = metadata.get("versions") or []
    cover_url = versions[0].get("coverURL") if versions else None
    name, mapper = map_name_mapper(metadata)
    meta = metadata.get("metadata") or {}
    return {
        "hash": map_hash(metadata),
        "beatsaver_id": metadata.get("id"),
        "name": name,
        "mapper": mapper,
        "song_author": meta.get("songAuthorName"),
        "bpm": meta.get("bpm"),
        "cover_url": cover_url,
    }


async def count_pending(db: AsyncSession, ss_id: str) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(MapSuggestion)
            .where(
                MapSuggestion.ss_id == ss_id,
                MapSuggestion.status == MapSuggestionStatus.PENDING,
            )
        )
        or 0
    )


async def map_is_ranked(db: AsyncSession, song_hash: str) -> bool:
    return (
        await db.scalar(
            select(Map.id).where(Map.hash == song_hash, Map.status == MapStatus.RANKED).limit(1)
        )
        is not None
    )


async def duplicate_pending(db: AsyncSession, ss_id: str, song_hash: str) -> bool:
    return (
        await db.scalar(
            select(MapSuggestion.id)
            .where(
                MapSuggestion.ss_id == ss_id,
                MapSuggestion.hash == song_hash,
                MapSuggestion.status == MapSuggestionStatus.PENDING,
            )
            .limit(1)
        )
        is not None
    )


async def create_map_from_suggestion(db: AsyncSession, suggestion: MapSuggestion) -> Map:
    """Cria o Map candidato a partir de uma sugestão aprovada (sem ML/difficulties)."""
    m = Map(
        hash=suggestion.hash,
        beatsaver_id=suggestion.beatsaver_id,
        name=suggestion.name,
        song_author=suggestion.song_author,
        mapper=suggestion.mapper,
        bpm=suggestion.bpm,
        cover_url=suggestion.cover_url,
        status=MapStatus.CANDIDATE,
        submitted_by=suggestion.ss_id,
    )
    db.add(m)
    await db.flush()
    return m
