"""CLI de coleta do dataset de referência de estrelas (star_reference).

Coleta a lista de mapas/dificuldades rankeados + amostra estratificada de
acc por banda de 0,5★ no ScoreSaber (escala do ranking BSBR, 0→14,58★) e no
BeatLeader (escala mais alta, ancorando até ~15,8★), grava em star_reference
e carrega a curva empírica expected-acc × estrelas.

Uso (a partir de backend/):
    python -m app.scripts.build_star_dataset [--sample-per-band 10] [--pages-per-lb 2]

Refresh é MANUAL: o batch semanal nunca re-crawlea este dataset.
ASCII puro (console Windows cp1252).
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  # registra mappers no Base.metadata
from app.core.config import get_settings
from app.core.db import Base
from app.integrations.beatleader import BeatLeaderClient
from app.integrations.scoresaber import ScoreSaberClient
from app.models import StarReference
from app.services.reweight import curve
from app.services.sync import parse_leaderboard_score

SS_SOURCE = "scoresaber"
BL_SOURCE = "beatleader"
MIN_SAMPLE = 5  # amostra mínima de acc por leaderboard para gravar median_top_acc

# O /api/v2/leaderboards do SS não traz o nome da dificuldade, só o código
# numérico (difficulty.difficulty). Mapa padrão do ScoreSaber.
_SS_DIFFICULTY_NAMES = {
    1: "Easy",
    3: "Normal",
    5: "Hard",
    7: "Expert",
    9: "ExpertPlus",
}


def eprint(*args) -> None:
    print(*args, file=sys.stderr)


def _median(values: list[float]) -> float:
    return statistics.median(values)


async def _upsert_list(session, rows: list[StarReference]) -> None:
    if not rows:
        return
    source = rows[0].source
    ids = [r.leaderboard_id for r in rows]
    existing = (
        await session.scalars(
            select(StarReference).where(
                StarReference.source == source,
                StarReference.leaderboard_id.in_(ids),
            )
        )
    ).all()
    by_key = {(r.source, r.leaderboard_id): r for r in existing}
    for row in rows:
        cur = by_key.get((row.source, row.leaderboard_id))
        if cur is None:
            session.add(row)
            continue
        cur.stars = row.stars
        cur.hash = row.hash
        cur.song_name = row.song_name
        cur.difficulty_name = row.difficulty_name
        cur.total_scores = row.total_scores
        cur.max_score = row.max_score
    await session.commit()


async def _set_sample(session, source: str, leaderboard_id: str, acc: float, n: int) -> None:
    row = (
        await session.scalars(
            select(StarReference).where(
                StarReference.source == source,
                StarReference.leaderboard_id == leaderboard_id,
            )
        )
    ).first()
    if row is None:
        row = StarReference(source=source, leaderboard_id=leaderboard_id)
        session.add(row)
    row.median_top_acc = acc
    row.sample_n = n
    await session.commit()


async def collect_scoresaber(session, client: ScoreSaberClient, args) -> list[dict]:
    eprint("[scoresaber] lista completa de rankeados (sortBy=stars)...")
    full: list[dict] = []
    page = 1
    while True:
        data, total = await client.ranked_leaderboards(
            sort_by="stars", sort_direction="desc", limit=100, page=page
        )
        if not data:
            break
        rows = []
        for lb in data:
            realm = lb.get("realm") or {}
            map_ = lb.get("map") or {}
            diff_code = (lb.get("difficulty") or {}).get("difficulty")
            rows.append(
                StarReference(
                    source=SS_SOURCE,
                    leaderboard_id=str(lb.get("id") or ""),
                    hash=map_.get("hash"),
                    song_name=map_.get("songName"),
                    difficulty_name=_SS_DIFFICULTY_NAMES.get(diff_code),
                    stars=float(realm.get("stars") or 0),
                    total_scores=lb.get("totalScores"),
                    max_score=lb.get("maxScore"),
                )
            )
            full.append(
                {
                    "id": str(lb.get("id") or ""),
                    "stars": float(realm.get("stars") or 0),
                    "max_score": lb.get("maxScore"),
                    "total_scores": lb.get("totalScores") or 0,
                }
            )
        await _upsert_list(session, rows)
        eprint(f"  pagina {page}: {len(rows)} (total {total})")
        if total is not None and len(full) >= total:
            break
        if len(data) < 100:
            break
        page += 1

    eprint("[scoresaber] amostra estratificada por banda de 0,5★...")
    max_stars = max((r["stars"] for r in full), default=0.0)
    band = 0.0
    sampled = 0
    while band <= max_stars:
        candidates = [
            r
            for r in full
            if band <= r["stars"] < band + 0.5 and r["total_scores"] >= 30
        ]
        candidates.sort(key=lambda r: r["total_scores"], reverse=True)
        for cand in candidates[: args.sample_per_band]:
            result = await client.leaderboard_scores_by_id_with_status(
                cand["id"], country=None, max_pages=args.pages_per_lb
            )
            if not result.transport_ok:
                continue
            accs = []
            for raw in result.scores:
                item = parse_leaderboard_score(raw, cand["max_score"])
                if item is not None and item["acc"]:
                    accs.append(item["acc"])
            if len(accs) >= MIN_SAMPLE:
                await _set_sample(session, SS_SOURCE, cand["id"], _median(accs), len(accs))
                sampled += 1
        band += 0.5
    eprint(f"[scoresaber] amostra gravada em {sampled} leaderboards")
    return full


async def collect_beatleader(session, client: BeatLeaderClient, args) -> None:
    eprint("[beatleader] lista completa de rankeados (sortBy=stars)...")
    full: list[dict] = []
    page = 1
    while True:
        data, total = await client.ranked_leaderboards(
            sort_by="stars", order="desc", count=100, page=page
        )
        if not data:
            break
        rows = []
        for lb in data:
            diff = lb.get("difficulty") or {}
            song = lb.get("song") or {}
            if diff.get("status") != 3:  # 3 = Ranked
                continue
            stars = diff.get("stars")
            if stars is None:
                continue
            # total_scores fica NULL no BL: nem a listagem nem o endpoint de
            # scores expõem a contagem (plays/attempts/totalScores vêm None).
            rows.append(
                StarReference(
                    source=BL_SOURCE,
                    leaderboard_id=str(lb.get("id") or ""),
                    hash=song.get("hash"),
                    song_name=song.get("name"),
                    difficulty_name=diff.get("difficultyName"),
                    stars=float(stars),
                    max_score=diff.get("maxScore"),
                )
            )
            full.append(
                {
                    "id": str(lb.get("id") or ""),
                    "stars": float(stars),
                    "max_score": diff.get("maxScore"),
                }
            )
        await _upsert_list(session, rows)
        eprint(f"  pagina {page}: {len(rows)} (total {total})")
        if total is not None and len(full) >= total:
            break
        if len(data) < 100:
            break
        page += 1

    eprint("[beatleader] amostra estratificada por banda de 0,5★...")
    max_stars = max((r["stars"] for r in full), default=0.0)
    band = 0.0
    sampled = 0
    while band <= max_stars:
        candidates = [r for r in full if band <= r["stars"] < band + 0.5]
        for cand in candidates[: args.sample_per_band]:
            scores = await client.leaderboard_scores(
                cand["id"], country=None, page=1, count=50
            )
            accs = [float(s.get("accuracy") or 0) for s in scores if s.get("accuracy")]
            accs = [a for a in accs if 0 < a <= 1.05]
            if len(accs) >= MIN_SAMPLE:
                await _set_sample(session, BL_SOURCE, cand["id"], _median(accs), len(accs))
                sampled += 1
        band += 0.5
    eprint(f"[beatleader] amostra gravada em {sampled} leaderboards")


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    ss = ScoreSaberClient()
    bl = BeatLeaderClient()
    try:
        async with maker() as session:
            await collect_scoresaber(session, ss, args)
            await collect_beatleader(session, bl, args)
            await curve.load_curve(session, refresh=True)
        eprint("curva empírica carregada por fonte/banda.")
    finally:
        await ss.close()
        await bl.close()
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta o dataset de referência de estrelas")
    parser.add_argument("--sample-per-band", type=int, default=10, help="leaderboards amostrados por banda (default 10)")
    parser.add_argument("--pages-per-lb", type=int, default=2, help="páginas de scores por leaderboard no SS (default 2)")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
