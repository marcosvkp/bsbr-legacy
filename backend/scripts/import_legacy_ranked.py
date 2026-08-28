"""Importa os mapas rankeados do legado (references/bsbr_ranked.json) com a análise do ML.

Para cada música do JSON:
1. Busca o mapa atual no BeatSaver por nome+mapper (detecta se o hash mudou);
2. Roda a análise ML (qualify_source) que preenche predições, cover e
   ss_leaderboard_id (API v2 do ScoreSaber);
3. Se TODAS as dificuldades tiverem ss_leaderboard_id -> aprova como RANKED
   (o sync de scores/PP só processa mapas rankeados); senão fica CANDIDATE
   para revisão.

Uso (host, com o venv — lê o JSON local e aponta para o Postgres do docker):
  DATABASE_URL=postgresql+asyncpg://bsbr:bsbr@localhost:15432/bsbr \
  .venv/Scripts/python -m scripts.import_legacy_ranked
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.db import SessionLocal
from app.models import Difficulty, MapStatus
from app.services.qualification import approve_map, qualify_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

REFS_DIR = Path(__file__).resolve().parents[2] / "references"
REFERENCE_FILE = REFS_DIR / "bsbr_ranked.json"

BEATSAVER_SEARCH = "https://api.beatsaver.com/search/text/0"
BEATSAVER_RATE_SLEEP = 1.0  # beatmaps API é tolerante; mantém ritmo seguro


def _normalize(value: str) -> str:
    """Lower + sem acentos + espaços colapsados (comparação entre fontes)."""
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def search_beatsaver(song_name: str, author: str) -> dict | None:
    """Compat: busca por nome apenas (usado fora do fluxo principal)."""
    return find_beatsaver(song_name, author, None)


def _load_reference() -> list[dict]:
    if not REFERENCE_FILE.exists():
        logger.error("referência não encontrada: %s", REFERENCE_FILE)
        sys.exit(1)
    data = json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))
    songs = data.get("songs") or []
    logger.info("referência: %d músicas do legado", len(songs))
    return songs


def find_beatsaver(song_name: str, author: str, legacy_hash: str | None) -> dict | None:
    """Localiza o mapa atual no BeatSaver.

    1. Busca pelo hash do legado (mapa não mudou) — via /maps/hash;
    2. Se 404 (mapa atualizado / hash mudou), busca por nome+mapper.
    """
    # 1) hash direto
    if legacy_hash:
        try:
            resp = httpx.get(
                f"https://api.beatsaver.com/maps/hash/{legacy_hash}",
                headers={"Accept": "application/json"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                versions = data.get("versions") or []
                return {
                    "id": data.get("id"),
                    "hash": versions[0].get("hash") if versions else legacy_hash,
                    "name": (data.get("metadata") or {}).get("songName"),
                    "author": (data.get("metadata") or {}).get("levelAuthorName"),
                }
        except httpx.HTTPError as exc:
            logger.warning("falha /maps/hash (%s): %s", song_name, exc)

    # 2) busca por nome + mapper (hash pode ter mudado)
    name_n = _normalize(song_name)
    author_n = _normalize(author)
    query = quote(song_name[:60])
    for _ in range(3):
        url = f"{BEATSAVER_SEARCH}?q={query}&sortOrder=Relevance"
        try:
            resp = httpx.get(url, headers={"Accept": "application/json"}, timeout=15)
            resp.raise_for_status()
            docs = resp.json().get("docs", [])
            for doc in docs:
                meta = doc.get("metadata") or {}
                if (
                    _normalize(meta.get("songName")) == name_n
                    and _normalize(meta.get("levelAuthorName")) == author_n
                ):
                    versions = doc.get("versions") or []
                    return {
                        "id": doc.get("id"),
                        "hash": versions[0].get("hash") if versions else None,
                        "name": meta.get("songName"),
                        "author": meta.get("levelAuthorName"),
                    }
            words = song_name.split()
            if len(words) <= 1:
                break
            query = quote(" ".join(words[:-1])[:60])
            time.sleep(BEATSAVER_RATE_SLEEP)
        except httpx.HTTPError as exc:
            logger.warning("falha na busca BeatSaver (%s): %s", song_name, exc)
            return None
    return None


async def import_one(session, song: dict) -> dict:
    name = song.get("songName", "?")
    author = song.get("levelAuthorName", "")
    legacy_hash = (song.get("hash") or "").upper()

    found = await asyncio.to_thread(find_beatsaver, name, author, legacy_hash)
    if found is None:
        return {"name": name, "outcome": "nao_encontrado_no_beatsaver"}

    current_hash = (found["hash"] or "").upper()
    hash_changed = legacy_hash and current_hash and current_hash != legacy_hash

    try:
        preview = await qualify_source(
            session, found["id"], submitted_by="legacy-import"
        )
    except Exception as exc:
        return {"name": name, "outcome": f"analise_falhou: {str(exc)[:80]}"}

    map_id = preview["map"]["id"]
    map_status = preview["map"]["status"]
    diffs = preview["difficulties"]
    missing = [d["name"] for d in diffs if not d.get("ss_leaderboard_id")]
    if map_status == "ranked":
        # já era rankeado (import anterior): apenas re-analisou/atualizou
        return {
            "name": name,
            "outcome": "ja_ranked_reanalisado",
            "hash_mudou": hash_changed,
            "hash_antigo": legacy_hash[:12] if hash_changed else None,
            "hash_novo": (current_hash or legacy_hash or "")[:12],
            "map_id": map_id,
            "diffs": len(diffs),
        }
    if not missing and diffs:
        try:
            m = await approve_map(session, map_id, ss_leaderboard_ids={}, reviewer="legacy-import")
            await session.commit()
            return {
                "name": name,
                "outcome": "importado_ranked",
                "hash_mudou": hash_changed,
                "hash_antigo": legacy_hash[:12] if hash_changed else None,
                "hash_novo": (current_hash or legacy_hash or "")[:12],
                "map_id": map_id,
                "diffs": len(diffs),
            }
        except Exception as exc:
            await session.rollback()
            return {"name": name, "outcome": f"aprovar_falhou: {str(exc)[:80]}"}
    await session.commit()
    return {
        "name": name,
        "outcome": "candidato_sem_ss_lb",
        "hash_mudou": hash_changed,
        "hash_antigo": legacy_hash[:12] if hash_changed else None,
        "hash_novo": (current_hash or legacy_hash or "")[:12],
        "map_id": map_id,
    }


async def main() -> None:
    songs = _load_reference()
    results = []
    async with SessionLocal() as session:
        for i, song in enumerate(songs, start=1):
            result = await import_one(session, song)
            results.append(result)
            logger.info("[%d/%d] %s -> %s", i, len(songs), result["name"][:40], result["outcome"])
            if i < len(songs):
                await asyncio.sleep(0.5)

    ranked = [r for r in results if r["outcome"] in ("importado_ranked", "ja_ranked_reanalisado")]
    candidate = [r for r in results if r["outcome"] == "candidato_sem_ss_lb"]
    failed = [r for r in results if r["outcome"] not in ("importado_ranked", "ja_ranked_reanalisado", "candidato_sem_ss_lb")]
    changed = [r for r in results if r.get("hash_mudou")]
    print("\n" + "=" * 60)
    print(f"Importados/Ranked      : {len(ranked)}")
    print(f"Candidatos (sem ss_lb): {len(candidate)}")
    print(f"Falhas / outros        : {len(failed)}")
    print(f"Hashes mudaram         : {len(changed)}")
    for r in changed:
        print(f"  * {r['name']}: {r['hash_antigo']} -> {r['hash_novo']}")
    for r in failed:
        print(f"  ! {r['name']}: {r['outcome']}")
    for r in candidate:
        print(f"  ~ {r['name']}: aguarda ss_leaderboard_id (candidato)")


if __name__ == "__main__":
    asyncio.run(main())
