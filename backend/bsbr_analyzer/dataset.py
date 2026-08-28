"""
Builder de dataset de treino ? porte de references/BSStarAnalyzer/main.py download.

Coleta dificuldades rankeadas do ScoreSaber (target: stars oficiais), baixa o
mapa do BeatSaver, analisa com o `bsbr_analyzer` (features fisicas + padrao)
e acumula linhas em `data/dataset.csv` com checkpoint a cada 50 musicas.

Retomavel: entradas ja presentes no CSV sao puladas (use --force para reprocessar).
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .beatsaver import download_map_zip, fetch_map_metadata, map_hash
from .analysis import analyze_map_folder
from .trainer import ALL_FEATURES, DATASET_FILE

SCORESABER_API_URL = "https://scoresaber.com/api"
BEATSAVER_API_URL = "https://api.beatsaver.com"

DATA_DIR = DATASET_FILE.parent
ZIP_DIR = DATA_DIR / "zips"
MAPS_DIR = DATA_DIR / "maps"
RANKED_MAPS_CACHE = DATA_DIR / "ranked_maps.json"

# Mapeamento numero ScoreSaber -> nome de dificuldade (Info.dat)
SS_DIFF_RANK_TO_NAME = {1: "Easy", 3: "Normal", 5: "Hard", 7: "Expert", 9: "ExpertPlus"}

DATASET_FIELDNAMES = (
    ["map_hash", "song_name", "difficulty", "stars", "map_styles"] + ALL_FEATURES
)

_locks_dict_lock = threading.Lock()
_map_locks: Dict[str, threading.Lock] = {}


class RateLimiter:
    """Limita chamadas a no maximo `calls` por janela de `period` segundos (thread-safe)."""

    def __init__(self, calls: int, period: float):
        self.calls, self.period = calls, period
        self.timestamps: List[float] = []
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.time()
            self.timestamps = [t for t in self.timestamps if now - t < self.period]
            if len(self.timestamps) >= self.calls:
                sleep_time = self.period - (now - self.timestamps[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                now = time.time()
                self.timestamps = [t for t in self.timestamps if now - t < self.period]
            self.timestamps.append(time.time())


beatsaver_limiter = RateLimiter(calls=8, period=1.0)


# ---------------------------------------------------------
# ScoreSaber
# ---------------------------------------------------------

def get_ranked_entries(limit: int = 500) -> List[dict]:
    """
    Busca entradas rankeadas do ScoreSaber (50 por pagina) com cache incremental.

    O cache `ranked_maps.json` cresce ? nunca perde dados; ao pedir mais do
    que o cache tem, busca apenas as paginas faltantes.
    """
    cached: List[dict] = []
    cached_ids: set = set()
    if RANKED_MAPS_CACHE.exists():
        try:
            cached = json.loads(RANKED_MAPS_CACHE.read_text(encoding="utf-8"))
            cached_ids = {e.get("id") for e in cached if e.get("id")}
        except Exception:
            cached = []

    if len(cached) >= limit:
        return cached[:limit]

    maps = list(cached)
    page = (len(cached) // 50) + 1
    print(f"  Cache: {len(cached)} entries. Buscando mais {limit - len(cached)} do ScoreSaber...")

    while len(maps) < limit:
        try:
            url = f"{SCORESABER_API_URL}/leaderboards?ranked=true&page={page}&limit=50"
            resp = httpx.get(url, headers={"Accept": "application/json"}, timeout=10)
            resp.raise_for_status()
            entries = resp.json().get("leaderboards", [])
            if not entries:
                print(f"  ScoreSaber retornou pagina vazia na pagina {page} ? fim dos dados.")
                break
            new_entries = [e for e in entries if e.get("id") not in cached_ids]
            maps.extend(new_entries)
            cached_ids.update(e.get("id") for e in new_entries if e.get("id"))
            page += 1
            time.sleep(0.4)
        except Exception as e:
            print(f"  Aviso: erro na pagina {page}: {e}")
            break

    RANKED_MAPS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RANKED_MAPS_CACHE.write_text(json.dumps(maps, indent=2), encoding="utf-8")
    return maps[:limit]


def group_by_hash(entries: List[dict]) -> Dict[str, List[dict]]:
    """Agrupa entries do ScoreSaber por songHash (uma musica pode ter N diffs rankeadas)."""
    groups: Dict[str, List[dict]] = defaultdict(list)
    for entry in entries:
        h = entry.get("songHash")
        if h:
            groups[h].append(entry)
    return dict(groups)


def fetch_ss_leaderboards(song_hash: str, pages: int = 3) -> List[dict]:
    """
    Busca os leaderboards do ScoreSaber para um hash.

    Usa `/api/v2/maps/hash/{hash}` (v2): retorna todos os leaderboards do mapa
    (ranked, qualified E unranked) direto por hash — o search paginado com
    ranked=true nao encontra mapas novos/qualified/unranked.
    Retorna entries normalizadas no formato antigo (id, songHash, difficulty, stars).
    """
    if not song_hash:
        return []
    try:
        url = f"{SCORESABER_API_URL}/v2/maps/hash/{song_hash.upper()}"
        resp = httpx.get(url, headers={"Accept": "application/json"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        # fallback: search paginado (antigo comportamento)
        return _fetch_ss_leaderboards_search(song_hash, pages)

    entries: List[dict] = []
    for lb in data.get("leaderboards") or []:
        realm = lb.get("realm") or {}
        stars = realm.get("stars") or 0
        entries.append(
            {
                "id": lb.get("id"),
                "songHash": data.get("hash") or song_hash.upper(),
                "difficulty": {"difficulty": lb.get("difficulty")},
                "stars": stars if stars else None,
                "ranked": realm.get("leaderboardStatus") == "RANKED",
                "maxScore": lb.get("maxScore"),
            }
        )
    return entries


def _fetch_ss_leaderboards_search(song_hash: str, pages: int) -> List[dict]:
    """Fallback: busca por search paginado (mapas antigos sem v2)."""
    found: List[dict] = []
    seen: set = set()
    for page in range(1, pages + 1):
        try:
            url = f"{SCORESABER_API_URL}/leaderboards?ranked=true&page={page}&limit=50"
            resp = httpx.get(url, headers={"Accept": "application/json"}, timeout=10)
            resp.raise_for_status()
            entries = resp.json().get("leaderboards", [])
            if not entries:
                break
            for e in entries:
                # ScoreSaber usa hash em MAIÚSCULAS; o analyze pode devolver minúsculas
                if (e.get("songHash") or "").upper() == song_hash.upper() and e.get("id") not in seen:
                    seen.add(e.get("id"))
                    found.append(e)
            # paginas rankeadas sao ordenadas por plays; para de buscar quando
            # a pagina nao trouxe mais hits (mapa popular aparece cedo)
            if found and page >= 2:
                break
            time.sleep(0.3)
        except Exception:
            break
    return found


# ---------------------------------------------------------
# Download / extracao (cache local por hash)
# ---------------------------------------------------------

def download_and_extract_map(map_hash_str: str) -> Optional[str]:
    """
    Baixa e extrai o mapa; reusa cache em `data/maps/<hash>/` se ja existir.
    Retorna o caminho da pasta extraida, ou None em falha.
    """
    extract_path = MAPS_DIR / map_hash_str
    with _locks_dict_lock:
        if map_hash_str not in _map_locks:
            _map_locks[map_hash_str] = threading.Lock()
        lock = _map_locks[map_hash_str]
    with lock:
        info_exists = (
            (extract_path / "Info.dat").exists() or (extract_path / "info.dat").exists()
        )
        if extract_path.exists() and info_exists:
            return str(extract_path)

        try:
            metadata = fetch_map_metadata(map_hash_str)
        except Exception as e:
            print(f"  Erro ao buscar metadados de {map_hash_str[:16]}...: {e}")
            return None

        zip_path = ZIP_DIR / f"{map_hash_str}.zip"
        if not zip_path.exists():
            try:
                beatsaver_limiter.wait()
                zip_bytes = download_map_zip(metadata)
                ZIP_DIR.mkdir(parents=True, exist_ok=True)
                zip_path.write_bytes(zip_bytes)
            except Exception as e:
                print(f"  Erro ao baixar {map_hash_str[:16]}...: {e}")
                return None

        try:
            if extract_path.exists():
                shutil.rmtree(extract_path)
            extract_path.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(extract_path)
            return str(extract_path)
        except Exception as e:
            print(f"  Erro ao extrair {map_hash_str[:16]}...: {e}")
            zip_path.unlink(missing_ok=True)
            if extract_path.exists():
                shutil.rmtree(extract_path, ignore_errors=True)
            return None


# ---------------------------------------------------------
# Dataset
# ---------------------------------------------------------

def _processed_keys() -> set:
    """Chaves (map_hash_difficulty) ja presentes no dataset ? evita duplicatas."""
    keys = set()
    if not DATASET_FILE.exists():
        return keys
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            h, d = row.get("map_hash", ""), row.get("difficulty", "")
            if h and d:
                keys.add(f"{h}_{d}")
    return keys


def process_map(map_hash_str: str, ranked_diffs: List[dict]) -> List[dict]:
    """
    Analisa um mapa e gera uma row por dificuldade rankeada:
    features (fisicas + padrao) + target `stars` oficial do ScoreSaber.
    """
    map_path = download_and_extract_map(map_hash_str)
    if not map_path:
        return []

    try:
        analysis = analyze_map_folder(map_path)
    except Exception as e:
        print(f"  Erro ao analisar {map_hash_str[:16]}...: {e}")
        return []
    if not analysis.difficulties:
        return []

    rows = []
    for entry in ranked_diffs:
        stars = entry.get("stars", 0)
        diff_num = (entry.get("difficulty") or {}).get("difficulty")
        diff_name = SS_DIFF_RANK_TO_NAME.get(diff_num)
        if diff_name is None:
            continue

        matched = next((d for d in analysis.difficulties if d.difficulty == diff_name), None)
        if matched is None:
            print(f"  [!] {map_hash_str[:16]}... / {diff_name}: nao encontrado no Info.dat")
            continue

        rows.append(
            {
                "map_hash": map_hash_str,
                "song_name": analysis.name,
                "difficulty": diff_name,
                "stars": stars,
                "map_styles": str(matched.style_tags),
                **matched.features,
            }
        )
    return rows


def update_dataset(new_rows: List[dict], skip_existing: bool = True) -> Tuple[int, int]:
    """Adiciona linhas novas ao dataset.csv (append), pulando duplicatas.

    Se o arquivo existente tiver header com esquema diferente do atual
    (ex.: builder antigo com 'bpm' extra), o arquivo é recriado do zero
    para nao misturar colunas desalinhadas.
    """
    rows = [r for r in new_rows if r]
    if not rows:
        return 0, 0

    existing = _processed_keys() if skip_existing else set()

    if DATASET_FILE.exists():
        with open(DATASET_FILE, "r", newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), None)
        if header != DATASET_FIELDNAMES:
            print("  Aviso: header do dataset.csv diferente do esquema atual — recriando arquivo.")
            DATASET_FILE.unlink()
            existing = set()

    to_write = []
    skipped = 0
    for row in rows:
        key = f"{row.get('map_hash', '')}_{row.get('difficulty', '')}"
        if key in existing:
            skipped += 1
        else:
            to_write.append(row)
            existing.add(key)

    if not to_write:
        return 0, skipped

    file_exists = DATASET_FILE.exists()
    DATASET_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATASET_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DATASET_FIELDNAMES, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(to_write)

    return len(to_write), skipped


# ---------------------------------------------------------
# Comando download
# ---------------------------------------------------------

def cmd_download(limit: int = 500, threads: int = 4, force: bool = False) -> dict:
    """
    Pipeline completa: ScoreSaber -> BeatSaver -> analise -> dataset.csv.
    Checkpoint a cada 50 musicas (progresso parcial salvo mesmo se interromper).
    """
    print(f"Buscando {limit} entradas rankeadas do ScoreSaber...")
    all_entries = get_ranked_entries(limit)
    groups = group_by_hash(all_entries)
    total_songs = len(groups)
    total_diffs = sum(len(v) for v in groups.values())
    print(f"  -> {total_diffs} dificuldades em {total_songs} musicas unicas")

    existing = _processed_keys()
    groups_to_process = {
        h: diffs for h, diffs in groups.items()
        if force or any(
            f"{h}_{SS_DIFF_RANK_TO_NAME.get(d.get('difficulty', {}).get('difficulty'), '?')}"
            not in existing
            for d in diffs
        )
    }
    already = total_songs - len(groups_to_process)
    if already:
        print(f"  -> {already} musicas ja no dataset (puladas)")

    if not groups_to_process:
        print("\nTudo ja esta no dataset. Use --force para reprocessar.")
        return {"added": 0, "skipped": 0, "failed": 0, "processed": 0}

    print(f"  -> {len(groups_to_process)} musicas para processar agora\n")

    all_rows: List[dict] = []
    done = 0
    failed = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(process_map, h, diffs): h
            for h, diffs in groups_to_process.items()
        }
        for future in as_completed(futures):
            h = futures[future]
            rows = future.result()
            done += 1
            if rows:
                all_rows.extend(rows)
                song = rows[0].get("song_name", h[:12])
                diffs_str = ", ".join(f"{r.get('difficulty', '?')} {r.get('stars', '?')}*" for r in rows)
                elapsed = time.time() - start
                eta = (elapsed / done) * (len(groups_to_process) - done) if done > 0 else 0
                print(f"[{done}/{len(groups_to_process)}] {song[:35]:<35} -> {diffs_str}  ETA: {eta / 60:.1f}min")
            else:
                failed += 1
                print(f"[{done}/{len(groups_to_process)}] {h[:16]}... X falhou ({failed} falhas total)")

            # Checkpoint a cada 50 musicas
            if all_rows and done % 50 == 0:
                added, skipped = update_dataset(all_rows, skip_existing=True)
                print(f"  -- Checkpoint: +{added} novas, {skipped} duplicatas --")
                all_rows = []

    added, skipped = update_dataset(all_rows, skip_existing=True)

    elapsed = time.time() - start
    print(f"\n{'-' * 60}")
    print(f"Concluido em {elapsed / 60:.1f} minutos")
    print(f"  Musicas processadas : {done}")
    print(f"  Falhas              : {failed}")
    print(f"  Adicionadas ao CSV  : {added}")
    print(f"  Duplicatas puladas  : {skipped}")

    return {"processed": done, "failed": failed, "added": added, "skipped": skipped}


def dataset_stats() -> dict:
    """Estatisticas resumidas do dataset atual."""
    if not DATASET_FILE.exists():
        return {"rows": 0}
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    unique_hashes = len({r.get("map_hash") for r in rows})
    diff_counts: Dict[str, int] = defaultdict(int)
    for r in rows:
        diff_counts[r.get("difficulty", "?")] += 1
    return {
        "rows": len(rows),
        "unique_maps": unique_hashes,
        "by_difficulty": dict(diff_counts),
    }


__all__ = [
    "DATASET_FILE",
    "cmd_download",
    "dataset_stats",
    "fetch_ss_leaderboards",
    "get_ranked_entries",
    "group_by_hash",
    "process_map",
    "update_dataset",
]
