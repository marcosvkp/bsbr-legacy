"""Qualificação de mapas novos (Plan.md §3.4).

submissão → análise (bsbr_analyzer em thread) → mapa fica CANDIDATE com
stars/sub-stars/features previstos → staff aprova com os ss_leaderboard_id
de cada dificuldade → vira RANKED com rating_history inicial.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Difficulty, Map, MapStatus, RatingHistory


def _status_value(status: MapStatus) -> str:
    return status.value if hasattr(status, "value") else str(status)


async def qualify_source(
    session: AsyncSession,
    source: str,
    *,
    submitted_by: str | None = None,
    stars_override: dict[str, float] | None = None,
) -> dict:
    """Baixa/analis o mapa do BeatSaver e persiste como candidato.

    Retorna preview completo para revisão de staff. Re-análise de hash já
    existente atualiza as predições sem mudar status.
    """
    from bsbr_analyzer import analyze_map  # import tardio: pacote pesado
    from bsbr_analyzer.beatsaver import fetch_map_metadata

    analysis = await asyncio.to_thread(analyze_map, source)

    # Capa do mapa (BeatSaver: versions[0].coverURL) para a UI
    cover_url = None
    try:
        metadata = await asyncio.to_thread(fetch_map_metadata, source)
        versions = metadata.get("versions") or []
        if versions:
            cover_url = versions[0].get("coverURL")
    except Exception:
        cover_url = None

    m = (
        await session.scalars(select(Map).where(Map.hash == analysis.hash).limit(1))
    ).first() if analysis.hash else None
    created = False
    if m is None:
        m = Map(
            hash=analysis.hash or f"bsid:{analysis.map_id}",
            beatsaver_id=analysis.map_id,
            name=analysis.name,
            status=MapStatus.CANDIDATE,
            bpm=analysis.bpm,
            mapper=analysis.mapper,
            cover_url=cover_url,
            submitted_by=submitted_by,
        )
        session.add(m)
        created = True
    else:
        m.beatsaver_id = analysis.map_id
        m.name = analysis.name
        m.mapper = analysis.mapper or m.mapper
        m.bpm = analysis.bpm or m.bpm
        if cover_url:
            m.cover_url = cover_url
        # Re-análise de um mapa recusado reabre como candidato (staff pode
        # reanalisar com ajuste de estrelas após recusar)
        if m.status == MapStatus.REMOVED:
            m.status = MapStatus.CANDIDATE
    await session.flush()

    # Preenche ss_leaderboard_id e max_score automaticamente: busca os
    # leaderboards do ScoreSaber (v2) para este hash e mapeia por dificuldade.
    ss_by_diff: dict[str, dict] = {}
    try:
        from bsbr_analyzer.dataset import SS_DIFF_RANK_TO_NAME, fetch_ss_leaderboards

        ss_entries = await asyncio.to_thread(fetch_ss_leaderboards, analysis.hash or "")
        for entry in ss_entries:
            diff_num = (entry.get("difficulty") or {}).get("difficulty")
            diff_name = SS_DIFF_RANK_TO_NAME.get(diff_num)
            if diff_name and str(entry.get("id")):
                ss_by_diff[diff_name] = {
                    "id": str(entry["id"]),
                    "max_score": entry.get("maxScore"),
                }
    except Exception:
        ss_by_diff = {}

    # Preenche bl_leaderboard_id automaticamente (opcional): busca os
    # leaderboards do BeatLeader para o hash e mapeia por difficultyName.
    bl_by_diff: dict[str, str] = {}
    try:
        from app.integrations.beatleader import BeatLeaderClient

        client = BeatLeaderClient()
        try:
            bl_entries = await client.leaderboards_by_hash(analysis.hash or "")
        finally:
            await client.close()
        for entry in bl_entries:
            diff_name = (entry.get("difficulty") or {}).get("difficultyName")
            if diff_name and str(entry.get("id")):
                bl_by_diff.setdefault(diff_name, str(entry["id"]))
    except Exception:
        bl_by_diff = {}

    diffs_payload = []
    for d in analysis.difficulties:
        existing = (
            await session.scalars(
                select(Difficulty).where(
                    Difficulty.map_id == m.id,
                    Difficulty.characteristic == d.characteristic,
                    Difficulty.name == d.difficulty,
                )
            )
        ).first()
        if existing is None:
            existing = Difficulty(map_id=m.id, characteristic=d.characteristic, name=d.difficulty)
            session.add(existing)
        existing.njs = d.njs
        # Ajuste manual de estrelas (staff pode pedir ao ML um teto/sobreposição)
        total_stars = round(d.total_stars, 2)
        base_acc, base_tech, base_speed = d.acc_stars, d.tech_stars, d.speed_stars
        if stars_override and d.difficulty in stars_override:
            override = float(stars_override[d.difficulty])
            if override > 0 and override != total_stars:
                ratio = override / total_stars if total_stars else 1.0
                base_acc *= ratio
                base_tech *= ratio
                base_speed *= ratio
                total_stars = round(override, 2)
        existing.total_stars = total_stars
        existing.acc_stars = round(base_acc, 2)
        existing.tech_stars = round(base_tech, 2)
        existing.speed_stars = round(base_speed, 2)
        existing.features = d.features
        existing.style_tags = d.style_tags
        existing.model_version = "model-v0" if d.stars_source == "model" else "heuristic-v1"
        ss_info = ss_by_diff.get(d.difficulty)
        if ss_info:
            if not existing.ss_leaderboard_id:
                existing.ss_leaderboard_id = ss_info["id"]
            if not existing.max_score and ss_info.get("max_score"):
                existing.max_score = int(ss_info["max_score"])
        bl_id = bl_by_diff.get(d.difficulty)
        if bl_id and not existing.bl_leaderboard_id:
            existing.bl_leaderboard_id = bl_id
        diffs_payload.append(existing)

    await session.commit()
    return {
        "created": created,
        "map": {
            "id": m.id,
            "hash": m.hash,
            "name": m.name,
            "mapper": m.mapper,
            "bpm": m.bpm,
            "cover_url": m.cover_url,
            "status": _status_value(m.status),
        },
        "difficulties": [
            {
                "id": d.id,
                "name": d.name,
                "total_stars": d.total_stars,
                "acc_stars": d.acc_stars,
                "tech_stars": d.tech_stars,
                "speed_stars": d.speed_stars,
                "style_tags": d.style_tags,
                "ss_leaderboard_id": d.ss_leaderboard_id,
                "bl_leaderboard_id": d.bl_leaderboard_id,
                "nps": d.features.get("nps") if d.features else None,
                "notes": d.features.get("note_count") or d.features.get("notes") if d.features else None,
            }
            for d in diffs_payload
        ],
    }


async def approve_map(
    session: AsyncSession,
    map_id: int,
    *,
    ss_leaderboard_ids: dict[str, str],
    reviewer: str,
    excluded_difficulties: list[str] | None = None,
) -> Map:
    """Promove candidato/qualificado a rankeado, exigindo leaderboard por diff.

    Dificuldades em ``excluded_difficulties`` são marcadas is_ranked=False e não
    entram no ranking (não precisam de leaderboard, não geram RatingHistory).
    """
    excluded = set(excluded_difficulties or ())
    m = await session.get(Map, map_id)
    if m is None:
        raise ValueError(f"mapa {map_id} não encontrado")
    if m.status == MapStatus.RANKED:
        raise ValueError(f"mapa {map_id} já está rankeado")

    difficulties = (
        (
            await session.scalars(select(Difficulty).where(Difficulty.map_id == map_id))
        )
        .all()
    )
    if not difficulties:
        raise ValueError("mapa sem dificuldades analisadas - rode a análise antes")

    # ss_leaderboard_ids vazios: usa os já preenchidos (auto-fetch do qualify)
    for d in difficulties:
        ss_leaderboard_ids.setdefault(d.name, d.ss_leaderboard_id or "")
    missing = [
        d.name for d in difficulties if d.name not in excluded and not ss_leaderboard_ids.get(d.name)
    ]
    if missing:
        raise ValueError(f"ss_leaderboard_id ausente para: {', '.join(missing)}")

    now = datetime.now(timezone.utc)
    for d in difficulties:
        if d.name in excluded:
            d.is_ranked = False
            d.ss_leaderboard_id = None
            d.ranked_at = None
            continue
        d.is_ranked = True
        before = d.total_stars
        d.ss_leaderboard_id = str(ss_leaderboard_ids[d.name])
        d.ranked_at = now
        session.add(
            RatingHistory(
                difficulty_id=d.id,
                total_stars_before=None,
                total_stars_after=d.total_stars,
                acc_stars_before=None,
                acc_stars_after=d.acc_stars,
                tech_stars_before=None,
                tech_stars_after=d.tech_stars,
                speed_stars_before=None,
                speed_stars_after=d.speed_stars,
                reason="Ranqueamento inicial (qualificação)",
                applied_by=reviewer,
            )
        )
    m.status = MapStatus.RANKED
    await session.commit()
    return m
