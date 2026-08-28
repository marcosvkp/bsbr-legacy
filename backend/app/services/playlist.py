"""Gerador da playlist BSBR Ranked (.bplist) — formato do legado.

v2 não precisa resolver hash via API: ``maps.hash`` já é a fonte.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Difficulty, Map, MapStatus

_PLAYLIST_TITLE = "BSBR Ranked Maps"
_PLAYLIST_TITLE_NEW = "BSBR Ranked Maps (Novos)"
_PLAYLIST_AUTHOR = "BSBR Team"

# Ordem canônica das dificuldades na playlist
_DIFF_ORDER = {"Easy": 0, "Normal": 1, "Hard": 2, "Expert": 3, "ExpertPlus": 4, "Expert+": 4}


def _normalize_diff(name: str) -> str:
    name = (name or "").replace(" ", "")
    return "ExpertPlus" if name == "Expert+" else name


async def generate_bsbr_playlist(
    session: AsyncSession,
    *,
    sync_url: str = "",
    title: str | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """Monta o dict da playlist com os mapas rankeados e suas dificuldades.

    ``days`` limita aos mapas com alguma dificuldade rankeada no período
    (playlist da "batch atual" de novos mapas).
    """
    query = (
        select(Map)
        .where(Map.status == MapStatus.RANKED)
        .options(selectinload(Map.difficulties))
        .order_by(Map.name)
    )
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        subq = exists(select(Difficulty.id).where(
            Difficulty.map_id == Map.id,
            Difficulty.ranked_at >= cutoff,
        ))
        query = query.where(subq)
    rows = (await session.execute(query)).scalars().all()

    songs_by_hash: dict[str, dict[str, Any]] = {}
    for m in rows:
        diffs = sorted(
            (d for d in m.difficulties if d.characteristic == "Standard"),
            key=lambda d: (_DIFF_ORDER.get(_normalize_diff(d.name), 99), d.name),
        )
        if not diffs:
            continue
        entry = songs_by_hash.setdefault(
            m.hash,
            {
                "songName": m.name,
                "levelAuthorName": m.mapper or "",
                "hash": m.hash,
                "levelid": f"custom_level_{m.hash}",
                "difficulties": [],
            },
        )
        for d in diffs:
            entry["difficulties"].append(
                {"characteristic": "Standard", "name": _normalize_diff(d.name)}
            )

    return {
        "playlistTitle": title or (_PLAYLIST_TITLE_NEW if days else _PLAYLIST_TITLE),
        "playlistAuthor": _PLAYLIST_AUTHOR,
        "customData": {"syncURL": sync_url},
        "songs": list(songs_by_hash.values()),
        "image": "",
    }


async def render_bsbr_playlist(
    session: AsyncSession,
    *,
    sync_url: str = "",
    title: str | None = None,
    days: int | None = None,
) -> str:
    data = await generate_bsbr_playlist(session, sync_url=sync_url, title=title, days=days)
    return json.dumps(data, indent=2, ensure_ascii=False)
