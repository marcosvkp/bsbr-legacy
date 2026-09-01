"""Testes de contrato da API v1 (TestClient + SQLite em arquivo por teste)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import Base
from app.main import app
from app.models import Difficulty, Map, MapStatus, Player, Score
from app.services.pp_engine import get_pp


@pytest.fixture(autouse=True)
def _admin_token():
    # get_settings() é lru_cache: patch na instância compartilhada garante
    # independência da ordem de import entre módulos de teste
    get_settings().admin_token = "test-token"
    yield
    get_settings().admin_token = None


@pytest.fixture
async def client(tmp_path, monkeypatch):
    # Aponta o engine global para sqlite temporário ANTES do TestClient abrir lifespan
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/api.db")
    import app.core.db as dbmod

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/api.db")
    dbmod.engine = engine
    dbmod.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    await engine.dispose()


@pytest.fixture
async def seeded(client):
    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        m = Map(hash="h1", name="Musica", status=MapStatus.RANKED, mapper="Mapper")
        s.add(m)
        await s.flush()
        d = Difficulty(
            map_id=m.id,
            characteristic="Standard",
            name="ExpertPlus",
            total_stars=5.0,
            acc_stars=2.5,
            tech_stars=1.5,
            speed_stars=1.0,
            max_score=1000000,
            ranked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        s.add(d)
        p = Player(ss_id="ss1", name="Jogador BR", country="BR", rank=1, pp_total=148.25,
                   pp_acc=29.65, pp_tech=88.95, pp_speed=29.65)
        s.add(p)
        await s.flush()
        s.add(
            Score(
                player_id=p.id,
                difficulty_id=d.id,
                score=950000,
                acc=0.95,
                pp=get_pp(5.0, 95.0),
                pp_acc=get_pp(5.0, 95.0) * 0.2,
                pp_tech=get_pp(5.0, 95.0) * 0.6,
                pp_speed=get_pp(5.0, 95.0) * 0.2,
                ss_player_pp=8000.0,
                leaderboard_rank=1,
                time_set=datetime(2026, 8, 20, 12, 0),
            )
        )
        await s.commit()
    return m.hash


async def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "ok"


async def test_player_pp_history_endpoint(client, seeded):
    r = client.get("/api/v1/players/ss1/pp-history?days=180")
    assert r.status_code == 200
    body = r.json()
    assert body["ss_id"] == "ss1"
    assert body["days"] == 180
    assert body["current_pp_total"] is not None
    assert body["points"]
    for pt in body["points"]:
        assert "ts" in pt and "pp_total" in pt and "estimated" in pt

    # janela fora do limite → 422 (validação do Query)
    assert client.get("/api/v1/players/ss1/pp-history?days=5").status_code == 422
    assert client.get("/api/v1/players/ss1/pp-history?days=999").status_code == 422
    # jogador inexistente → 404
    assert client.get("/api/v1/players/nao-existe/pp-history?days=30").status_code == 404


async def test_calc_matches_legacy_curve(client):
    r = client.post("/api/v1/calc", json={"stars": 8.5, "accuracy": 97.88})
    assert r.status_code == 200
    body = r.json()
    assert body["pp_total"] == pytest.approx(get_pp(8.5, 97.88), abs=1e-3)
    assert body["pp_total"] == pytest.approx(body["pp_acc"] + body["pp_tech"] + body["pp_speed"], abs=1e-2)


async def test_rankings_component_validation(client):
    assert client.get("/api/v1/rankings?component=foo").status_code == 422
    r = client.get("/api/v1/rankings?component=tech")
    assert r.status_code == 200 and r.json()["component"] == "tech"


async def test_rankings_returns_seeded_player(client, seeded):
    r = client.get("/api/v1/rankings")
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["name"] == "Jogador BR" and item["rank"] == 1
    assert item["pp_total"] == 148.25


async def test_player_profile_and_scores(client, seeded):
    profile = client.get("/api/v1/players/ss1").json()
    assert profile["pp_total"] == 148.25
    assert profile["medals"]["total"] == 10  # rank 1 no único mapa

    scores = client.get("/api/v1/players/ss1/scores").json()
    assert scores["items"][0]["map_name"] == "Musica"
    assert scores["items"][0]["tech_stars"] == 1.5


async def test_maps_list_and_detail(client, seeded):
    listed = client.get("/api/v1/maps").json()
    assert listed["total"] == 1
    item = listed["items"][0]
    assert item["difficulties"][0]["total_stars"] == 5.0

    detail = client.get(f"/api/v1/maps/{seeded}").json()
    assert detail["leaderboard"][0]["player_name"] == "Jogador BR"
    assert detail["leaderboard"][0]["pp"] == pytest.approx(get_pp(5.0, 95.0), abs=1e-2)


async def test_map_catalog_excludes_unranked_difficulties(client, seeded):
    """Dificuldade com is_ranked=False some do catálogo, do detail e do max-stars."""
    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        s.add(
            Difficulty(
                map_id=1,
                characteristic="Standard",
                name="Easy",
                total_stars=9.0,  # maior que a ExpertPlus rankeada (5.0)
                acc_stars=2.7,
                tech_stars=2.7,
                speed_stars=3.6,
                max_score=500000,
                ranked_at=None,
                ss_leaderboard_id=None,
                is_ranked=False,
            )
        )
        await s.commit()

    listed = client.get("/api/v1/maps?page_size=30").json()
    assert listed["total"] == 1
    assert [d["name"] for d in listed["items"][0]["difficulties"]] == ["ExpertPlus"]

    detail = client.get("/api/v1/maps/h1").json()
    assert [d["name"] for d in detail["difficulties_detail"]] == ["ExpertPlus"]

    # max-stars do mapa ignora a Easy desativada (9.0 fora do filtro)
    assert client.get("/api/v1/maps", params={"min_stars": 6.0}).json()["total"] == 0


async def test_maps_search_by_name_or_mapper(client, seeded):
    assert client.get("/api/v1/maps", params={"q": "music"}).json()["total"] == 1
    assert client.get("/api/v1/maps", params={"q": "MAPP"}).json()["total"] == 1
    assert client.get("/api/v1/maps", params={"q": "zzz-inexistente"}).json()["total"] == 0


async def test_maps_filter_by_min_stars(client, seeded):
    assert client.get("/api/v1/maps", params={"min_stars": 4.0}).json()["total"] == 1
    assert client.get("/api/v1/maps", params={"min_stars": 6.0}).json()["total"] == 0


async def test_playlist_download(client, seeded):
    r = client.get("/api/v1/playlists/ranked.bplist")
    assert r.status_code == 200
    assert "playlist.bplist" in r.headers["content-disposition"]
    data = r.json()
    assert data["playlistTitle"] == "BSBR Ranked Maps"
    assert data["songs"][0]["hash"] == seeded
    assert data["songs"][0]["difficulties"] == [{"characteristic": "Standard", "name": "ExpertPlus"}]
    assert data["customData"]["syncURL"].endswith("/api/v1/playlists/ranked.bplist")


async def test_latest_playlist_download(client, seeded):
    """Playlist da batch atual (novos) — mesma estrutura, título diferente."""
    r = client.get("/api/v1/playlists/latest.bplist")
    assert r.status_code == 200
    assert "playlist-novos.bplist" in r.headers["content-disposition"]
    data = r.json()
    assert data["playlistTitle"] == "BSBR Ranked Maps (Novos)"
    assert data["customData"]["syncURL"].endswith("/api/v1/playlists/latest.bplist")


async def test_admin_requires_token(client):
    assert client.get("/api/v1/admin/reweight/suggestions").status_code == 403
    assert (
        client.get(
            "/api/v1/admin/reweight/suggestions", headers={"X-Admin-Token": "errado"}
        ).status_code
        == 403
    )


async def test_admin_suggestions_lists_existing(client, seeded):
    """Sugestões existentes retornam o mapa (eager load do Map — não deve dar 500)."""
    from app.core.db import SessionLocal
    from app.models import Difficulty, ReweightSuggestion

    headers = {"X-Admin-Token": "test-token"}
    async with SessionLocal() as s:
        d = (await s.scalars(
            select(Difficulty).where(Difficulty.map_id == 1)
        )).one()
        s.add(ReweightSuggestion(
            difficulty_id=d.id, status="pending",
            suggested_stars=4.8, delta_stars=-0.2, sample_size=12,
            observed_acc=0.91, expected_acc=0.905, confidence="low", reason="teste",
        ))
        await s.commit()

    r = client.get("/api/v1/admin/reweight/suggestions", headers=headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["map_name"] == "Musica"
    assert items[0]["difficulty"] == "ExpertPlus"


async def test_admin_flow_with_token(client, seeded):
    headers = {"X-Admin-Token": "test-token"}
    empty = client.get("/api/v1/admin/reweight/suggestions", headers=headers).json()
    assert empty["items"] == []

    # batch manual roda ponta a ponta (sync contra API real falha silenciosamente → 0 scores)
    run = client.post("/api/v1/admin/batch/run", headers=headers)
    assert run.status_code == 200
    assert run.json()["players_updated"] == 1


async def test_admin_batches_requires_token_and_lists(client, seeded):
    headers = {"X-Admin-Token": "test-token"}
    assert client.get("/api/v1/admin/batches").status_code == 403

    run_resp = client.post("/api/v1/admin/batch/run", headers=headers)
    assert run_resp.status_code == 200, run_resp.text
    body = client.get("/api/v1/admin/batches", headers=headers).json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["kind"] == "weekly"
    assert item["running"] is False
    assert item["finished_at"] is not None
    assert item["stats"]["players_updated"] == 1


def test_live_recent_endpoint(client):
    """Sem Redis no teste, /live/recent retorna lista vazia (não quebra)."""
    body = client.get("/api/v1/live/recent").json()
    assert body == {"items": []}


async def test_stars_bands_scope_filter(client, seeded):
    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        m2 = Map(hash="h2", name="Mapa Gringo", status=MapStatus.RANKED, mapper="Mapper2")
        s.add(m2)
        await s.flush()
        d2 = Difficulty(
            map_id=m2.id, characteristic="Standard", name="ExpertPlus",
            total_stars=6.3, acc_stars=1.0, tech_stars=1.0, speed_stars=4.3,
            max_score=1000000,
            ranked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        s.add(d2)
        p2 = Player(ss_id="ss2", name="Gringo", country="US", rank=1, pp_total=300.0)
        s.add(p2)
        await s.flush()
        s.add(Score(
            player_id=p2.id, difficulty_id=d2.id, score=980000, acc=0.98,
            pp=get_pp(6.3, 98.0), ss_player_pp=9000.0, leaderboard_rank=1,
            time_set=datetime(2026, 8, 21, 12, 0),
        ))
        await s.commit()

    br = client.get("/api/v1/stars-bands?scope=br").json()
    assert br["scope"] == "br" and br["step"] == 0.5
    assert len(br["bands"]) == 1
    band = br["bands"][0]
    assert band["min"] == 5.0 and band["max"] == 5.5
    assert band["score_count"] == 1
    assert band["top"]["player_name"] == "Jogador BR"
    assert band["top"]["map_name"] == "Musica"

    # scope inválido → 422; global inclui o score do player US
    assert client.get("/api/v1/stars-bands?scope=foo").status_code == 422
    globe = client.get("/api/v1/stars-bands?scope=global").json()
    assert len(globe["bands"]) == 2
    bands_by_min = {b["min"]: b for b in globe["bands"]}
    assert bands_by_min[6.0]["top"]["player_name"] == "Gringo"
    assert bands_by_min[6.0]["top"]["stars"] == 6.3


async def test_admin_candidates_and_qualify_flow(client, seeded):
    """Fila de qualificação: CANDIDATE -> candidates list -> qualify -> approve."""
    headers = {"X-Admin-Token": "test-token"}
    from app.core.db import SessionLocal

    # cria um candidato direto no banco
    async with SessionLocal() as s:
        m = Map(hash="cand1", name="Mapa Candidato", status=MapStatus.CANDIDATE, mapper="M")
        s.add(m)
        await s.flush()
        s.add(Difficulty(
            map_id=m.id, characteristic="Standard", name="ExpertPlus",
            total_stars=6.0, acc_stars=1.0, tech_stars=1.0, speed_stars=4.0,
            max_score=1000000, ranked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ))
        await s.commit()
        cand_id = m.id

    body = client.get("/api/v1/admin/maps/candidates", headers=headers).json()
    ids = [c["id"] for c in body["items"]]
    assert cand_id in ids
    cand_payload = next(c for c in body["items"] if c["id"] == cand_id)
    assert cand_payload["status"] == "candidate"

    # colocar na fila de qualify (CANDIDATE -> QUALIFIED)
    q = client.post(f"/api/v1/admin/maps/{cand_id}/qualify", headers=headers)
    assert q.status_code == 200
    assert q.json()["status"] == "qualified"

    # repetir deve dar 422 (não é mais candidato)
    assert client.post(f"/api/v1/admin/maps/{cand_id}/qualify", headers=headers).status_code == 422

    # approve sem ss_leaderboard_id -> 422 (dificuldade sem leaderboard)
    a = client.post(
        f"/api/v1/admin/maps/{cand_id}/approve",
        headers={**headers, "Content-Type": "application/json"},
        json={"ss_leaderboard_ids": {}, "reviewer": "staff"},
    )
    assert a.status_code == 422
    assert "ss_leaderboard_id ausente" in a.json()["detail"]

    # sem token -> 403
    assert client.get("/api/v1/admin/maps/candidates").status_code == 403
    assert client.post("/api/v1/admin/maps/999/qualify", headers=headers).status_code == 404


async def test_admin_reject_and_stars_override(client, seeded):
    """Recusar candidato (-> removed) e ajuste manual de stars no qualify."""
    headers = {"X-Admin-Token": "test-token"}
    from app.core.db import SessionLocal

    async with SessionLocal() as s:
        m = Map(hash="cand2", name="Mapa Recusavel", status=MapStatus.CANDIDATE, mapper="M")
        s.add(m)
        await s.flush()
        s.add(Difficulty(
            map_id=m.id, characteristic="Standard", name="ExpertPlus",
            total_stars=5.0, acc_stars=1.0, tech_stars=1.0, speed_stars=3.0,
            max_score=1000000, ranked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ))
        await s.commit()
        cand_id = m.id

    # ajuste de stars ao colocar na fila (4.5 -> 6.0): substars escalam por razão
    q = client.post(
        f"/api/v1/admin/maps/{cand_id}/qualify",
        headers={**headers, "Content-Type": "application/json"},
        json={"stars_override": {"ExpertPlus": 6.0}},
    )
    assert q.status_code == 200
    assert q.json()["status"] == "qualified"

    async with SessionLocal() as s:
        d = (await s.scalars(
            select(Difficulty).where(Difficulty.map_id == cand_id)
        )).one()
        assert d.total_stars == 6.0
        assert d.speed_stars == round(3.0 * 6.0 / 5.0, 2)

    # recusar -> removed
    r = client.post(f"/api/v1/admin/maps/{cand_id}/reject", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "removed"

    # recusar de novo é idempotente (200, continua removed)
    again = client.post(f"/api/v1/admin/maps/{cand_id}/reject", headers=headers)
    assert again.status_code == 200
    assert again.json()["status"] == "removed"


async def test_og_player_image(client, seeded):
    """OG do jogador gera PNG 1200x630 com avatar/PP."""
    r = client.get("/api/v1/og/players/ss1.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    data = r.content
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # magic PNG
    assert len(data) > 1000


async def test_og_map_image(client, seeded):
    """OG do mapa gera PNG 1200x630 com cover/stars."""
    r = client.get("/api/v1/og/maps/h1.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(r.content) > 1000


async def test_og_unknown_returns_404(client, seeded):
    assert client.get("/api/v1/og/players/nao-existe.png").status_code == 404
    assert client.get("/api/v1/og/maps/xyz.png").status_code == 404
