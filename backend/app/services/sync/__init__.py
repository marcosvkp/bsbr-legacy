"""Sincronização ScoreSaber → banco local.

v1 (Plan.md F3): para cada dificuldade rankeada com ``ss_leaderboard_id``,
busca os scores do leaderboard (BR), faz upsert de players e scores,
calculando PP/sub-PP na ingestão via pp_engine.

Convenções herdadas do legado:
- scores com modificador NF são descartados;
- acc = baseScore / max_score (baseScore evita distorção de modifiers que
  multiplicam o score final, ex. DA);
- PP calculado pela curva do legado com os sub-stars da dificuldade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.scoresaber import ScoreSaberClient
from app.models import Difficulty, Map, MapStatus, Player, Score
from app.services.pp_engine import decompose_pp


@dataclass
class SyncStats:
    difficulty_id: int
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_nf: int = 0
    errors: list[str] = field(default_factory=list)


async def upsert_players(session: AsyncSession, raw_players: list[dict]) -> dict[str, Player]:
    """Upsert de players por ss_id (payload /players). Retorna mapa ss_id → Player."""
    ss_ids = [str(p.get("id")) for p in raw_players if p.get("id")]
    existing = {
        p.ss_id: p
        for p in (await session.scalars(select(Player).where(Player.ss_id.in_(ss_ids)))).all()
    }
    for raw in raw_players:
        ss_id = str(raw["id"])
        player = existing.get(ss_id)
        if player is None:
            player = Player(ss_id=ss_id)
            session.add(player)
            existing[ss_id] = player
        player.name = raw.get("name") or player.name or ss_id
        player.country = raw.get("country") or player.country
        player.avatar_url = raw.get("profilePicture") or player.avatar_url
    await session.flush()
    return existing


def parse_leaderboard_score(raw: dict, max_score: int | None) -> dict | None:
    """Extrai campos relevantes de um score do ScoreSaber; None se inválido/NF."""
    info = raw.get("leaderboardPlayerInfo") or {}
    modifiers = raw.get("modifiers") or ""
    if "NF" in modifiers:
        return None
    base = int(raw.get("baseScore") or 0)
    if base <= 0:
        return None
    acc = (base / max_score) if max_score else None
    time_set_raw = raw.get("timeSet")
    if time_set_raw:
        dt = datetime.fromisoformat(time_set_raw.replace("Z", "+00:00"))
        # Normaliza para naive-UTC: SQLite/PG devolvem sem tz e a chave única
        # (player, difficulty, time_set) precisa bater entre syncs
        time_set = dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        time_set = datetime.utcnow()
    return {
        "ss_player_id": str(info.get("id") or ""),
        "player_name": str(info.get("name") or "") or None,
        "avatar_url": str(info.get("profilePicture") or "") or None,
        "score": int(raw.get("modifiedScore") or base),
        "acc": acc,
        "modifiers": modifiers or None,
        "full_combo": bool(raw.get("fullCombo")),
        "leaderboard_rank": int(raw.get("rank") or 0) or None,
        "time_set": time_set,
        "ss_player_pp": float(info.get("pp") or 0) or None,
    }


async def sync_difficulty_scores(
    session: AsyncSession,
    difficulty_id: int,
    *,
    client: ScoreSaberClient | None = None,
    country: str = "BR",
    max_pages: int | None = None,
) -> SyncStats:
    """Busca e persiste scores de um leaderboard rankeado."""
    own_client = client is None
    client = client or ScoreSaberClient()
    stats = SyncStats(difficulty_id=difficulty_id)
    try:
        difficulty = await session.get(Difficulty, difficulty_id)
        if difficulty is None:
            stats.errors.append(f"difficulty {difficulty_id} não encontrada")
            return stats
        if not difficulty.ss_leaderboard_id:
            stats.errors.append(f"difficulty {difficulty_id} sem ss_leaderboard_id")
            return stats
        if difficulty.total_stars is None:
            stats.errors.append(f"difficulty {difficulty_id} sem total_stars")
            return stats

        raw_scores = await client.leaderboard_scores_by_id(
            difficulty.ss_leaderboard_id, country=country, max_pages=max_pages
        )
        stats.fetched = len(raw_scores)

        parsed: list[dict] = []
        for raw in raw_scores:
            item = parse_leaderboard_score(raw, difficulty.max_score)
            if item is None:
                stats.skipped_nf += 1
                continue
            parsed.append(item)

        # Garante players existentes (nomes vindos do payload do score)
        players_by_ss: dict[str, Player] = {}
        missing_ids = {p["ss_player_id"] for p in parsed}
        if missing_ids:
            found = {
                p.ss_id: p
                for p in (
                    await session.scalars(select(Player).where(Player.ss_id.in_(missing_ids)))
                ).all()
            }
            item_names = {p["ss_player_id"]: p["player_name"] for p in parsed}
            item_avatars = {p["ss_player_id"]: p["avatar_url"] for p in parsed}
            for ss_id in missing_ids - set(found):
                player = Player(ss_id=ss_id, name=item_names.get(ss_id) or ss_id)
                # sync é filtrado por país (default BR) — players novos ganham o país
                if country and country != "global":
                    player.country = country.upper()
                player.avatar_url = item_avatars.get(ss_id) or player.avatar_url
                session.add(player)
                found[ss_id] = player
            await session.flush()
            players_by_ss = found

        total = float(difficulty.total_stars)
        share_acc, share_tech, share_speed = _shares_of(difficulty)

        # Upsert por chave única (player_id, difficulty_id, time_set).
        # Normaliza para naive-UTC: no Postgres (timestamptz) o SELECT devolve
        # datetime com tz e o parse gera naive — sem normalizar a chave nunca casa.
        def _naive(dt: datetime) -> datetime:
            return dt.replace(tzinfo=None) if dt.tzinfo else dt

        existing_rows = {
            (s.player_id, _naive(s.time_set)): s
            for s in (
                await session.scalars(select(Score).where(Score.difficulty_id == difficulty_id))
            ).all()
        }

        for item in parsed:
            player = players_by_ss[item["ss_player_id"]]
            if player.avatar_url is None and item.get("avatar_url"):
                player.avatar_url = item["avatar_url"]
            sub = decompose_pp(
                total,
                (item["acc"] or 0.0) * 100,
                share_acc=share_acc,
                share_tech=share_tech,
                share_speed=share_speed,
            )
            row = existing_rows.get((player.id, _naive(item["time_set"])))
            if row is None:
                row = Score(player_id=player.id, difficulty_id=difficulty_id, time_set=item["time_set"])
                session.add(row)
                stats.inserted += 1
            else:
                stats.updated += 1
            row.score = item["score"]
            row.acc = item["acc"]
            row.modifiers = item["modifiers"]
            row.full_combo = item["full_combo"]
            row.leaderboard_rank = item["leaderboard_rank"]
            row.pp = sub["pp_total"]
            row.pp_acc = sub["pp_acc"]
            row.pp_tech = sub["pp_tech"]
            row.pp_speed = sub["pp_speed"]
            row.leaderboard_rank = item["leaderboard_rank"]
            row.ss_player_pp = item["ss_player_pp"]

        await session.commit()
        return stats
    finally:
        if own_client:
            await client.close()


def _shares_of(difficulty: Difficulty) -> tuple[float, float, float]:
    total_share = (
        float(difficulty.acc_stars or 0.0)
        + float(difficulty.tech_stars or 0.0)
        + float(difficulty.speed_stars or 0.0)
    )
    if total_share <= 0:
        # Sem decomposição definida: tudo em acc (comportamento neutro do legado)
        return 1.0, 0.0, 0.0
    return (
        float(difficulty.acc_stars or 0.0) / total_share,
        float(difficulty.tech_stars or 0.0) / total_share,
        float(difficulty.speed_stars or 0.0) / total_share,
    )


async def sync_all_ranked_difficulties(
    session: AsyncSession,
    *,
    country: str = "BR",
    max_pages: int | None = None,
) -> list[SyncStats]:
    """Sync completo dos mapas rankeados (usado pelo batch semanal)."""
    client = ScoreSaberClient()
    try:
        rows = (
            (
                await session.execute(
                    select(Difficulty)
                    .join(Map, Difficulty.map_id == Map.id)
                    .where(Map.status == MapStatus.RANKED)
                    .where(Difficulty.ss_leaderboard_id.is_not(None))
                )
            )
            .scalars()
            .all()
        )
        results = []
        for difficulty in rows:
            results.append(
                await sync_difficulty_scores(
                    session,
                    difficulty.id,
                    client=client,
                    country=country,
                    max_pages=max_pages,
                )
            )
        return results
    finally:
        await client.close()
