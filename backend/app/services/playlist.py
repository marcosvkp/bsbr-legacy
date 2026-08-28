"""Gerador da playlist BSBR Ranked (.bplist) — formato do legado.

v2 não precisa resolver hash via API: ``maps.hash`` já é a fonte.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Difficulty, Map, MapStatus

_PLAYLIST_TITLE = "BSBR Ranked Maps"
_PLAYLIST_AUTHOR = "BSBR Team"

# Ordem canônica das dificuldades na playlist
_DIFF_ORDER = {"Easy": 0, "Normal": 1, "Hard": 2, "Expert": 3, "ExpertPlus": 4, "Expert+": 4}


def _normalize_diff(name: str) -> str:
    name = (name or "").replace(" ", "")
    return "ExpertPlus" if name == "Expert+" else name


async def generate_bsbr_playlist(session: AsyncSession, *, sync_url: str = "") -> dict[str, Any]:
    """Monta o dict da playlist com os mapas rankeados e suas dificuldades."""
    rows = (
        (
            await session.execute(
                select(Map)
                .where(Map.status == MapStatus.RANKED)
                .options(selectinload(Map.difficulties))
                .order_by(Map.name)
            )
        )
        .scalars()
        .all()
    )

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
        "playlistTitle": _PLAYLIST_TITLE,
        "playlistAuthor": _PLAYLIST_AUTHOR,
        "customData": {"syncURL": sync_url},
        "songs": list(songs_by_hash.values()),
        "image": "",
    }


async def render_bsbr_playlist(session: AsyncSession, *, sync_url: str = "") -> str:
    data = await generate_bsbr_playlist(session, sync_url=sync_url)
    return json.dumps(data, indent=2, ensure_ascii=False)
