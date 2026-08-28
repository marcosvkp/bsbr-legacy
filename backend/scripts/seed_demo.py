"""Seed de demonstração: 2 mapas rankeados, 3 jogadores, scores com PP real.

Uso: cd backend && python scripts/seed_demo.py  (dev only — apaga storage/bsbr.db antes se quiser recomeçar)
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.models import Difficulty, Map, MapStatus, Player, Score  # noqa: E402
from app.services.pp_engine import decompose_pp  # noqa: E402


async def main() -> None:
    await init_db()
    async with SessionLocal() as s:
        if await s.get(Map, 1):
            print("Seed já aplicado.")
            return

        maps = [
            Map(id=1, hash="d" * 40, beatsaver_id="53c5a", name="Neon Genesis (BSBR)", mapper="MapperBR",
                bpm=150, status=MapStatus.RANKED, created_at=datetime(2026, 8, 1, tzinfo=timezone.utc)),
            Map(id=2, hash="e" * 40, beatsaver_id="5f6c1", name="Techstorm BR", mapper="MapperBR2",
                bpm=174, status=MapStatus.RANKED, created_at=datetime(2026, 8, 10, tzinfo=timezone.utc)),
        ]
        s.add_all(maps)
        await s.flush()

        diffs = [
            Difficulty(id=1, map_id=1, characteristic="Standard", name="ExpertPlus", max_score=1_000_000,
                       total_stars=7.0, acc_stars=1.0, tech_stars=5.0, speed_stars=1.0,
                       ss_leaderboard_id="9001", style_tags=["tech"], ranked_at=datetime(2026, 8, 1, tzinfo=timezone.utc)),
            Difficulty(id=2, map_id=1, characteristic="Standard", name="Expert", max_score=800_000,
                       total_stars=5.0, acc_stars=2.0, tech_stars=1.0, speed_stars=2.0,
                       ss_leaderboard_id="9002", style_tags=["balanced"], ranked_at=datetime(2026, 8, 1, tzinfo=timezone.utc)),
            Difficulty(id=3, map_id=2, characteristic="Standard", name="ExpertPlus", max_score=1_000_000,
                       total_stars=6.0, acc_stars=1.0, tech_stars=1.0, speed_stars=4.0,
                       ss_leaderboard_id="9003", style_tags=["speed"], ranked_at=datetime(2026, 8, 10, tzinfo=timezone.utc)),
        ]
        s.add_all(diffs)

        players = [
            Player(id=1, ss_id="ssA", name="LuizaBR", country="BR", pp_total=0),
            Player(id=2, ss_id="ssB", name="SpeedDemon", country="BR", pp_total=0),
            Player(id=3, ss_id="ssC", name="TechMaster", country="BR", pp_total=0),
        ]
        s.add_all(players)
        await s.flush()

        base = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
        plays = [
            # (player, diff, stars, shares, acc, rank, minutos)
            (1, 1, 0.97, 1), (2, 1, 0.94, 30), (3, 1, 0.96, 60),
            (3, 2, 0.95, 5), (1, 2, 0.92, 35), (2, 2, 0.90, 65),
            (2, 3, 0.96, 10), (1, 3, 0.93, 40), (3, 3, 0.91, 70),
        ]
        for i, (pid, did, acc, minutes) in enumerate(plays):
            d = diffs[did - 1]
            sub = decompose_pp(d.total_stars, acc * 100,
                               share_acc=d.acc_stars / d.total_stars,
                               share_tech=d.tech_stars / d.total_stars,
                               share_speed=d.speed_stars / d.total_stars)
            s.add(Score(player_id=pid, difficulty_id=did, score=int(acc * d.max_score), acc=acc,
                        pp=sub["pp_total"], pp_acc=sub["pp_acc"], pp_tech=sub["pp_tech"],
                        pp_speed=sub["pp_speed"], ss_player_pp=7000 - i * 100,
                        full_combo=acc > 0.95, leaderboard_rank=i + 1,
                        time_set=base + timedelta(minutes=minutes)))

        from app.services.ranking import recompute_all_rankings
        summary = await recompute_all_rankings(s)
        print(f"Seed ok — {summary.players_updated} jogadores rankeados.")


if __name__ == "__main__":
    asyncio.run(main())
