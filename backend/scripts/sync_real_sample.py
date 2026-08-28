"""Sync real limitado de dados do ScoreSaber (desenvolvimento).

Puxa alguns mapas rankeados reais (cria Map/Difficulty com ss_leaderboard_id
e stars oficiais), popula jogadores do ranking BR e sincroniza scores BR
(1 página por leaderboard). Uso: `docker compose exec api python scripts/sync_real_sample.py`.

Nao destrutivo: faz upsert (nao apaga o seed). Limite por env:
  SYNC_MAX_MAPS (padrao 10), SYNC_MAX_PLAYER_PAGES (padrao 2).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import SessionLocal
from app.integrations.scoresaber import ScoreSaberClient
from app.models import Difficulty, Map, MapStatus, Player
from app.services.sync import sync_difficulty_scores, upsert_players
from bsbr_analyzer.dataset import get_ranked_entries

MAX_MAPS = int(os.environ.get("SYNC_MAX_MAPS", "10"))
MAX_PLAYER_PAGES = int(os.environ.get("SYNC_MAX_PLAYER_PAGES", "2"))

DIFF_RANK_TO_NAME = {1: "Easy", 3: "Normal", 5: "Hard", 7: "Expert", 9: "ExpertPlus"}


async def sync_players_br(client: ScoreSaberClient) -> int:
    """Popular o ranking BR com jogadores reais (paginas iniciais)."""
    async with SessionLocal() as session:
        raw = await client.players_by_country("BR", max_pages=MAX_PLAYER_PAGES)
        if not raw:
            return 0
        players = await upsert_players(session, raw)
        await session.commit()
        return len(players)


async def sync_maps_and_scores() -> dict:
    client = ScoreSaberClient()
    entries = await asyncio.to_thread(get_ranked_entries, 60)
    print(f"ScoreSaber: {len(entries)} entries rankeadas obtidas")

    # Agrupa por hash e pega ate MAX_MAPS mapas unicos (mantem variedade de dificuldades)
    by_hash: dict[str, list[dict]] = {}
    for e in entries:
        by_hash.setdefault(e.get("songHash"), []).append(e)
    hashes = list(by_hash.keys())[:MAX_MAPS]

    stats = {"maps": 0, "difficulties": 0, "scores_fetched": 0, "players_br": 0}
    async with SessionLocal() as session:
        for h in hashes:
            map_entries = by_hash[h]
            first = map_entries[0]
            song = first.get("song") or {}
            m = (
                await session.scalars(select(Map).where(Map.hash == h))
            ).first()
            if m is None:
                m = Map(hash=h, status=MapStatus.RANKED)
                session.add(m)
            m.name = song.get("name") or first.get("songName") or h[:12]
            m.mapper = song.get("author") or first.get("levelAuthorName") or "?"
            m.cover_url = first.get("coverImage") or m.cover_url
            await session.flush()

            for entry in map_entries:
                diff_num = (entry.get("difficulty") or {}).get("difficulty")
                diff_name = DIFF_RANK_TO_NAME.get(diff_num)
                if diff_name is None:
                    continue
                ss_lb_id = str(entry.get("id"))
                d = (
                    await session.scalars(
                        select(Difficulty).where(Difficulty.ss_leaderboard_id == ss_lb_id)
                    )
                ).first()
                if d is None:
                    d = Difficulty(
                        map_id=m.id,
                        characteristic="Standard",
                        name=diff_name,
                        ss_leaderboard_id=ss_lb_id,
                        ranked_at=datetime.now(timezone.utc),
                    )
                    session.add(d)
                d.total_stars = entry.get("stars")
                d.max_score = entry.get("maxScore")
                await session.flush()
                stats["difficulties"] += 1

            await session.commit()

        # Sincroniza scores BR (1 pagina por leaderboard)
        for h in hashes:
            diffs = (
                await session.scalars(
                    select(Difficulty).join(Map).where(Map.hash == h)
                )
            ).all()
            for d in diffs:
                if not d.ss_leaderboard_id or d.total_stars is None:
                    continue
                s = await sync_difficulty_scores(session, d.id, client=client, max_pages=1)
                stats["scores_fetched"] += s.fetched
                await session.commit()
                print(f"  {d.name} lb={d.ss_leaderboard_id}: {s.fetched} scores, {s.inserted} novos")

        stats["maps"] = len(hashes)
        stats["players_br"] = await sync_players_br(client)

    await client.close()
    return stats


async def main() -> None:
    print("Sync real limitado (dev)...")
    stats = await sync_maps_and_scores()
    print(f"\nConcluido: {stats['maps']} mapas | {stats['difficulties']} dificuldades | "
          f"{stats['scores_fetched']} scores BR | {stats['players_br']} players BR")


if __name__ == "__main__":
    asyncio.run(main())
