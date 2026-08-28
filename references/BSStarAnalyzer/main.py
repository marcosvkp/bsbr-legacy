"""
main.py
────────────────────────────────────────────────────────────────────────────
Beat Saber Star Analyzer — CLI principal.

Comandos:
  download          Baixa e indexa mapas rankeados do ScoreSaber
  train             Treina o modelo de predição de stars
  analyze           Analisa um mapa por hash ou BeatSaver ID
  analyze-playlist  Analisa uma playlist .bplist
  performance       Analisa a performance real dos players em um mapa
  adjust-rating     Ajusta o rating de um mapa com base em performance ou manual
  unranked          Estima stars de um mapa não rankeado
  list-adjustments  Lista ajustes de rating salvos
"""

import requests
import os
import sys
import json
import time
import zipfile
import shutil
import argparse
import csv
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

from analyzer import analyze_map_structure
from trainer import (
    train_model,
    predict_stars,
    predict_with_fallback,
    save_adjustment,
    apply_adjustment,
    load_adjustments,
    heuristic_stars,
    BASE_FEATURES,
    PATTERN_FEATURES,
)
from player_performance import (
    ScoreSaberPerformanceAnalyzer,
    performance_with_adjustment,
    format_performance_report,
)

# ─────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────

SCORESABER_API_URL = "https://scoresaber.com/api"
BEATSAVER_API_URL  = "https://api.beatsaver.com"

DOWNLOAD_DIR      = "maps"
EXTRACT_DIR       = "extracted_maps"
RANKED_MAPS_CACHE = "ranked_maps.json"
DATASET_FILE      = "dataset.csv"

# Mapeamento número ScoreSaber → nome de dificuldade
SS_DIFF_RANK_TO_NAME = {1: "Easy", 3: "Normal", 5: "Hard", 7: "Expert", 9: "ExpertPlus"}
DIFF_NAME_TO_RANK    = {"Easy": 1, "Normal": 3, "Hard": 5, "Expert": 7, "ExpertPlus": 9}

# Colunas do dataset — inclui features de padrão
DATASET_FIELDNAMES = (
    ["map_hash", "song_name", "difficulty", "stars", "bpm"]
    + BASE_FEATURES[:-2]   # remove bpm e duration_seconds (já estão acima/abaixo)
    + ["duration_seconds"]
    + PATTERN_FEATURES
    + ["map_styles"]
)
seen = set()
DATASET_FIELDNAMES = [x for x in DATASET_FIELDNAMES if not (x in seen or seen.add(x))]

locks_dict_lock = threading.Lock()
map_locks: dict = {}


# ─────────────────────────────────────────────────────────
# Rate limiter
# ─────────────────────────────────────────────────────────

class RateLimiter:
    def __init__(self, calls: int, period: float):
        self.calls, self.period = calls, period
        self.timestamps: list = []
        self.lock = threading.Lock()

    def wait(self):
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


# ─────────────────────────────────────────────────────────
# Helpers de API
# ─────────────────────────────────────────────────────────

def resolve_beatsaver_id(key: str) -> str | None:
    try:
        beatsaver_limiter.wait()
        resp = requests.get(f"{BEATSAVER_API_URL}/maps/id/{key}", timeout=10)
        if resp.status_code == 200:
            return resp.json()["versions"][0]["hash"]
    except Exception:
        pass
    return None


def get_scoresaber_leaderboard_info(map_hash: str, difficulty_rank: int) -> dict | None:
    try:
        url  = f"{SCORESABER_API_URL}/leaderboard/by-hash/{map_hash}/info?difficulty={difficulty_rank}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_scoresaber_acc(map_hash: str, difficulty_rank: int) -> float | None:
    try:
        info = get_scoresaber_leaderboard_info(map_hash, difficulty_rank)
        if not info:
            return None
        max_score = info.get("maxScore", 0)
        if max_score > 0:
            url  = f"{SCORESABER_API_URL}/leaderboard/by-hash/{map_hash}/scores?difficulty={difficulty_rank}&page=1"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                scores = resp.json().get("scores", [])
                if scores:
                    accs = [s["baseScore"] / max_score for s in scores]
                    return sum(accs) / len(accs)
    except Exception:
        pass
    return None

def get_scoresaber_performance_data(map_hash: str, difficulty_rank: int) -> dict | None:
    """
    Coleta métricas detalhadas de performance do ScoreSaber (percentis, decay, etc).
    """
    try:
        info = get_scoresaber_leaderboard_info(map_hash, difficulty_rank)
        if not info:
            return None
            
        max_score = info.get("maxScore", 0)
        total_plays = info.get("plays", 0)
        
        if total_plays < 100: 
            return None # Poucos dados

        # Busca páginas 1, 2, 4, 6 para ter uma amostra da curva até o top 300
        pages_to_fetch = [1, 2]
        if total_plays > 500: pages_to_fetch.append(4)
        if total_plays > 1000: pages_to_fetch.append(6)

        all_accuracies = []
        full_combos = 0
        total_fetched = 0

        for page in pages_to_fetch:
            url = f"{SCORESABER_API_URL}/leaderboard/by-hash/{map_hash}/scores?difficulty={difficulty_rank}&page={page}"
            resp = requests.get(url, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                scores = data.get("scores", [])
                if not scores: break
                
                for s in scores:
                    if max_score > 0:
                        acc = s["baseScore"] / max_score
                        all_accuracies.append(acc)
                    if s["fullCombo"]:
                        full_combos += 1
                
                total_fetched += len(scores)
            else:
                break
            time.sleep(0.1)

        if not all_accuracies: return None

        # Métricas estatísticas
        all_accuracies.sort(reverse=True)
        n = len(all_accuracies)
        
        def get_percentile(p):
            idx = int(n * p)
            return all_accuracies[min(idx, n - 1)]

        acc_top10  = statistics.mean(all_accuracies[:10]) if n >= 10 else all_accuracies[0]
        acc_q1     = get_percentile(0.25)
        acc_median = get_percentile(0.50)
        acc_q3     = get_percentile(0.75)
        
        elite_decay   = acc_top10 - acc_q1
        general_decay = acc_q1 - acc_median
        acc_std       = statistics.stdev(all_accuracies) if n > 1 else 0

        return {
            "acc_top10": acc_top10,
            "acc_q1": acc_q1,
            "acc_median": acc_median,
            "acc_q3": acc_q3,
            "elite_decay": elite_decay,
            "general_decay": general_decay,
            "acc_std": acc_std,
            "fc_rate": full_combos / total_fetched if total_fetched > 0 else 0,
            "plays": total_plays
        }

    except Exception as e:
        print(f"Erro ao buscar performance detalhada: {e}")
        pass
    return None


def get_ranked_maps_from_scoresaber(limit: int = 500) -> list:
    """
    Busca entradas rankeadas do ScoreSaber com cache incremental.

    Cada entry é uma DIFICULDADE rankeada (não uma música).
    O cache em ranked_maps.json cresce incrementalmente — nunca perde dados.
    Ao pedir mais do que o cache tem, busca apenas as páginas faltantes.
    """
    # Carrega cache existente
    cached: list = []
    cached_ids: set = set()
    if os.path.exists(RANKED_MAPS_CACHE):
        try:
            with open(RANKED_MAPS_CACHE, "r") as f:
                cached = json.load(f)
            cached_ids = {e.get("id") for e in cached if e.get("id")}
        except Exception:
            cached = []

    if len(cached) >= limit:
        return cached[:limit]

    # Precisa buscar mais — continua da última página
    # Estima a página de início baseada no que já temos (50 por página)
    start_page = (len(cached) // 50) + 1
    maps = list(cached)

    print(f"  Cache: {len(cached)} entries. Buscando mais {limit - len(cached)} do ScoreSaber...")

    page = start_page
    while len(maps) < limit:
        try:
            url  = f"{SCORESABER_API_URL}/leaderboards?ranked=true&page={page}&limit=50"
            resp = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
            resp.raise_for_status()
            data    = resp.json()
            entries = data.get("leaderboards", [])
            if not entries:
                print(f"  ScoreSaber retornou página vazia na página {page} — fim dos dados.")
                break
            # Adiciona apenas entries novas (evita duplicatas se páginas mudaram)
            new_entries = [e for e in entries if e.get("id") not in cached_ids]
            maps.extend(new_entries)
            cached_ids.update(e.get("id") for e in new_entries if e.get("id"))
            page += 1
            time.sleep(0.4)
        except Exception as e:
            print(f"  Aviso: erro na página {page}: {e}")
            break

    # Salva cache com TODOS os entries (cresce sempre)
    with open(RANKED_MAPS_CACHE, "w") as f:
        json.dump(maps, f, indent=2)

    return maps[:limit]


def download_and_extract_map(map_hash: str) -> str | None:
    if not map_hash:
        return None
    extract_path = os.path.join(EXTRACT_DIR, map_hash)
    with locks_dict_lock:
        if map_hash not in map_locks:
            map_locks[map_hash] = threading.Lock()
        lock = map_locks[map_hash]
    with lock:
        # Aceita info.dat (case insensitive)
        info_exists = (
            os.path.exists(os.path.join(extract_path, "Info.dat")) or
            os.path.exists(os.path.join(extract_path, "info.dat"))
        )
        if os.path.exists(extract_path) and info_exists:
            return extract_path
        zip_path = os.path.join(DOWNLOAD_DIR, f"{map_hash}.zip")
        if not os.path.exists(zip_path):
            beatsaver_limiter.wait()
            try:
                meta   = requests.get(f"{BEATSAVER_API_URL}/maps/hash/{map_hash}", timeout=10).json()
                dl_url = meta["versions"][0]["downloadURL"]
                beatsaver_limiter.wait()
                with open(zip_path, "wb") as f:
                    f.write(requests.get(dl_url, timeout=30).content)
            except Exception as e:
                print(f"  Erro ao baixar {map_hash}: {e}")
                return None
        try:
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path)
            os.makedirs(extract_path)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_path)
            return extract_path
        except Exception as e:
            print(f"  Erro ao extrair {map_hash}: {e}")
            return None


# ─────────────────────────────────────────────────────────
# Processamento de mapa rankeado
# ─────────────────────────────────────────────────────────

def process_ranked_map(map_hash: str, ranked_diffs: list[dict]) -> list[dict]:
    """
    Processa um mapa, salvando UMA ROW no dataset para CADA dificuldade rankeada.

    Args:
        map_hash: Hash do mapa
        ranked_diffs: Lista de entries do ScoreSaber para esse hash.
                      Cada entry tem { difficulty: {difficulty: 9}, stars: 7.34, ... }

    Returns:
        Lista de rows prontas para o dataset (uma por dificuldade rankeada).
    """
    map_path = download_and_extract_map(map_hash)
    if not map_path:
        return []

    analysis = analyze_map_structure(map_path, include_patterns=True)
    if not analysis:
        return []

    rows = []
    for entry in ranked_diffs:
        stars       = entry.get("stars", 0)
        diff_num    = entry.get("difficulty", {}).get("difficulty")   # número SS: 1,3,5,7,9
        diff_name   = SS_DIFF_RANK_TO_NAME.get(diff_num)              # "ExpertPlus" etc.

        if diff_name is None:
            continue  # dificuldade desconhecida, pula

        # Localiza a dificuldade no resultado da análise
        # Tenta pelo nome primeiro, depois pelo rank numérico
        matched = None
        for d in analysis["difficulties"]:
            if d.get("difficulty") == diff_name:
                matched = d
                break
        if matched is None:
            for d in analysis["difficulties"]:
                if d.get("rank") == diff_num:
                    matched = d
                    break

        if matched is None:
            # Dificuldade rankeada no SS mas não encontrada no arquivo do mapa
            # (pode acontecer com mapas antigos ou V4 com nomes diferentes)
            print(f"  ⚠  {map_hash} / {diff_name}: não encontrado no Info.dat")
            continue

        row = {
            "map_hash":  map_hash,
            "song_name": analysis["song_name"],
            "stars":     stars,
            "bpm":       analysis["bpm"],
            **matched,
        }
        # Serializa map_styles como string para o CSV
        if "map_styles" in row and isinstance(row["map_styles"], list):
            row["map_styles"] = str(row["map_styles"])

        rows.append(row)

    return rows


def group_entries_by_hash(entries: list[dict]) -> dict[str, list[dict]]:
    """
    Agrupa as entries do ScoreSaber por songHash.
    Uma música com 3 dificuldades rankeadas vira um grupo de 3 entries.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        h = entry.get("songHash")
        if h:
            groups[h].append(entry)
    return dict(groups)


def _get_processed_keys() -> set:
    """
    Retorna o conjunto de chaves (map_hash + difficulty) já presentes no dataset.
    Usado para evitar duplicatas ao re-rodar o download.
    """
    keys = set()
    if not os.path.exists(DATASET_FILE):
        return keys
    try:
        import csv as _csv
        with open(DATASET_FILE, "r", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                h = row.get("map_hash", "")
                d = row.get("difficulty", "")
                if h and d:
                    keys.add(f"{h}_{d}")
    except Exception:
        pass
    return keys


def update_dataset(new_data_list: list, skip_existing: bool = True) -> tuple[int, int]:
    """
    Adiciona linhas novas ao dataset, opcionalmente pulando duplicatas.

    Returns:
        (adicionadas, puladas)
    """
    rows = [r for r in new_data_list if r]
    if not rows:
        return 0, 0

    existing_keys = _get_processed_keys() if skip_existing else set()

    to_write = []
    skipped  = 0
    for row in rows:
        key = f"{row.get('map_hash', '')}_{row.get('difficulty', '')}"
        if key in existing_keys:
            skipped += 1
        else:
            to_write.append(row)
            existing_keys.add(key)

    if not to_write:
        return 0, skipped

    file_exists = os.path.exists(DATASET_FILE)
    with open(DATASET_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DATASET_FIELDNAMES, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(to_write)

    return len(to_write), skipped


# ─────────────────────────────────────────────────────────
# Formatação de análise de dificuldade para terminal
# ─────────────────────────────────────────────────────────

DIFF_DISPLAY_ORDER = ["Easy", "Normal", "Hard", "Expert", "ExpertPlus"]


def _display_diff_table(analysis: dict, map_hash: str | None, args) -> None:
    bpm = analysis["bpm"]

    header = (
        f"{'Difficulty':<12} | {'NPS':>5} | {'Peak':>5} | "
        f"{'PkStrain':>8} | {'Volatility':>10} | "
        f"{'Streams':>7} | {'Jumps':>6} | {'Cross%':>6} | "
        f"{'Style':<22} | {'Acc':>7} | {'Pred★':>7} | {'Src':>9}"
    )
    print(header)
    print("─" * len(header))

    diffs_sorted = sorted(
        analysis["difficulties"],
        key=lambda d: DIFF_DISPLAY_ORDER.index(d.get("difficulty", ""))
        if d.get("difficulty") in DIFF_DISPLAY_ORDER else 99,
    )

    for diff in diffs_sorted:
        features = {**diff, "bpm": bpm}

        predicted, src = predict_with_fallback(features)

        if map_hash and diff.get("difficulty"):
            predicted = apply_adjustment(predicted, map_hash, diff["difficulty"])

        if getattr(args, "buff", 0):
            predicted += args.buff
        if getattr(args, "nerf", 0):
            predicted -= args.nerf
        predicted = max(0.0, predicted)

        real_acc_str = "N/A"
        if map_hash and diff.get("rank"):
            acc = get_scoresaber_acc(map_hash, diff["rank"])
            if acc:
                real_acc_str = f"{acc * 100:.1f}%"

        styles = diff.get("map_styles", [])
        if isinstance(styles, str):
            import ast
            try:
                styles = ast.literal_eval(styles)
            except Exception:
                styles = [styles]
        style_str = ", ".join(styles)[:22]

        stream_ratio = diff.get("pat_stream_note_ratio", diff.get("stream_ratio", 0))
        jump_density  = diff.get("pat_jump_density", 0)
        cross_ratio   = diff.get("pat_crossover_ratio", 0)

        print(
            f"{diff['difficulty']:<12} | {diff['nps']:>5.2f} | {diff['peak_nps']:>5} | "
            f"{diff.get('peak_strain', 0):>8.3f} | {diff.get('strain_volatility', 0):>10.3f} | "
            f"{stream_ratio:>7.2f} | {jump_density:>6.2f} | {cross_ratio*100:>6.1f}% | "
            f"{style_str:<22} | {real_acc_str:>7} | {predicted:>7.2f}★ | {src:>9}"
        )


# ─────────────────────────────────────────────────────────
# Comandos CLI
# ─────────────────────────────────────────────────────────

def cmd_download(args) -> None:
    """
    Baixa e indexa mapas rankeados.

    --limit: número de DIFICULDADES rankeadas para buscar do ScoreSaber.
             Uma música com 3 diffs rankeadas gera 3 entradas no dataset.
    """
    print(f"Buscando {args.limit} entradas rankeadas do ScoreSaber...")
    all_entries = get_ranked_maps_from_scoresaber(args.limit)

    # Agrupa por hash — cada música é baixada uma vez
    groups = group_entries_by_hash(all_entries)
    total_songs = len(groups)
    total_diffs = sum(len(v) for v in groups.values())

    print(f"  → {total_diffs} dificuldades em {total_songs} músicas únicas")

    # Descobre quais músicas/dificuldades já estão no dataset (evita re-processar)
    existing_keys = _get_processed_keys()
    already_done  = sum(
        1 for h, diffs in groups.items()
        for d in diffs
        if f"{h}_{SS_DIFF_RANK_TO_NAME.get(d.get('difficulty',{}).get('difficulty'),'?')}" in existing_keys
    )
    if already_done:
        print(f"  → {already_done} dificuldades já no dataset (serão puladas)")

    # Filtra grupos onde TODAS as diffs já estão no dataset
    groups_to_process = {
        h: diffs for h, diffs in groups.items()
        if args.force or any(
            f"{h}_{SS_DIFF_RANK_TO_NAME.get(d.get('difficulty',{}).get('difficulty'),'?')}"
            not in existing_keys
            for d in diffs
        )
    }

    if not groups_to_process:
        print("\nTudo já está no dataset. Use --force para reprocessar.")
        return

    print(f"  → {len(groups_to_process)} músicas para processar agora")
    print()

    all_rows = []
    done     = 0
    failed   = 0
    start    = time.time()

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        future_to_hash = {
            executor.submit(process_ranked_map, h, diffs): h
            for h, diffs in groups_to_process.items()
        }
        for future in as_completed(future_to_hash):
            h    = future_to_hash[future]
            rows = future.result()
            done += 1

            if rows:
                all_rows.extend(rows)
                song_name = rows[0].get("song_name", h[:12])
                diffs_str = ", ".join(
                    f"{r.get('difficulty','?')} {r.get('stars','?')}★" for r in rows
                )
                elapsed = time.time() - start
                eta = (elapsed / done) * (len(groups_to_process) - done) if done > 0 else 0
                print(
                    f"[{done}/{len(groups_to_process)}] {song_name[:35]:<35}"
                    f" → {diffs_str}"
                    f"  ETA: {eta/60:.1f}min"
                )
            else:
                failed += 1
                print(f"[{done}/{len(groups_to_process)}] {h[:16]}... ✗ falhou ({failed} falhas total)")

            # Checkpoint a cada 50 músicas — salva progresso parcial
            if len(all_rows) > 0 and done % 50 == 0:
                added, skipped = update_dataset(all_rows, skip_existing=True)
                print(f"  ── Checkpoint: +{added} novas, {skipped} duplicatas ──")
                all_rows = []

    # Salva o restante
    added, skipped = update_dataset(all_rows, skip_existing=True)

    elapsed = time.time() - start
    print(f"\n{'─'*60}")
    print(f"Concluído em {elapsed/60:.1f} minutos")
    print(f"  Músicas processadas : {done}")
    print(f"  Falhas              : {failed}")
    print(f"  Adicionadas ao CSV  : {added}")
    print(f"  Duplicatas puladas  : {skipped}")

    # Mostra tamanho atual do dataset
    if os.path.exists(DATASET_FILE):
        import csv as _csv
        with open(DATASET_FILE, "r") as f:
            total_rows = sum(1 for _ in _csv.reader(f)) - 1
        print(f"  Dataset total       : {total_rows} linhas")


def cmd_train(args) -> None:
    train_model()


def cmd_analyze(args) -> None:
    target = args.id_or_hash
    if len(target) < 10:
        map_hash = resolve_beatsaver_id(target)
        if not map_hash:
            print("Não foi possível resolver o ID no BeatSaver.")
            return
    else:
        map_hash = target

    map_path = download_and_extract_map(map_hash)
    if not map_path:
        print(f"Falha ao baixar/extrair o mapa {map_hash}.")
        return

    analysis = analyze_map_structure(map_path, include_patterns=True)
    if not analysis:
        print("Falha ao analisar o mapa.")
        return

    print(f"\nMúsica  : {analysis['song_name']}")
    print(f"BPM     : {analysis['bpm']}")
    print(f"Hash    : {map_hash}")
    print()

    _display_diff_table(analysis, map_hash, args)


def cmd_analyze_playlist(args) -> None:
    if not os.path.exists(args.file):
        print(f"Arquivo de playlist não encontrado: {args.file}")
        return

    with open(args.file, "r", encoding="utf-8") as f:
        playlist = json.load(f)

    final_results = {"playlistTitle": playlist.get("playlistTitle"), "songs": []}
    songs_map = {}

    for song in playlist.get("songs", []):
        map_hash = song.get("hash")
        song_name = song.get("songName")
        print(f"\n--- Analisando: {song_name} ---")

        map_path = download_and_extract_map(map_hash)
        if not map_path:
            print(f"  Falha ao baixar/extrair {map_hash}")
            continue

        analysis = analyze_map_structure(map_path, include_patterns=True)
        if not analysis:
            continue

        if map_hash not in songs_map:
            songs_map[map_hash] = {
                "songName": song_name,
                "hash": map_hash,
                "difficulties": []
            }

        for diff_entry in song.get("difficulties", []):
            diff_name = diff_entry.get("name")
            matched = next(
                (d for d in analysis["difficulties"] if d.get("difficulty") == diff_name), None
            )
            if not matched:
                continue

            features = {**matched, "bpm": analysis["bpm"]}
            predicted, src = predict_with_fallback(features)
            adjusted = apply_adjustment(predicted, map_hash, diff_name)

            print(f"  {diff_name:<12} | Predição: {adjusted:.2f}★  [{src}]")

            if args.interactive:
                action = input("  Buff, Nerf ou Pular? (b/n/p): ").lower()
                final_stars = adjusted
                if action in ("b", "n"):
                    try:
                        value = float(input(f"  Valor a {'adicionar' if action == 'b' else 'subtrair'}: "))
                        final_stars = adjusted + (value if action == "b" else -value)
                    except ValueError:
                        print("  Valor inválido, pulando.")
                final_stars = max(0.0, final_stars)
            else:
                final_stars = adjusted

            songs_map[map_hash]["difficulties"].append({
                "name": diff_name,
                "stars": round(final_stars, 2)
            })

    # converter map → lista final
    final_results["songs"] = list(songs_map.values())

    output_file = "playlist_analysis.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=2, ensure_ascii=False)
    print(f"\nAnálise concluída. Resultados em {output_file}")


def cmd_performance(args) -> None:
    target = args.id_or_hash
    if len(target) < 10:
        map_hash = resolve_beatsaver_id(target)
        if not map_hash:
            print("Não foi possível resolver o ID.")
            return
    else:
        map_hash = target

    difficulty_rank = DIFF_NAME_TO_RANK.get(args.difficulty, 9)
    print(f"\nBuscando performance para {map_hash} [{args.difficulty}]...")

    analyzer = ScoreSaberPerformanceAnalyzer()
    result   = analyzer.analyze(
        map_hash=map_hash,
        difficulty_rank=difficulty_rank,
        current_stars=args.stars,
        suggest_adjustment=args.suggest,
    )

    print(format_performance_report(result))

    if args.suggest and args.save and result.get("rating_adjustment"):
        adj = result["rating_adjustment"]
        if adj.get("confidence") in ("medium", "high") and abs(adj.get("suggested_delta", 0)) > 0.1:
            save_adjustment(
                map_hash=map_hash,
                difficulty=args.difficulty,
                base_stars=result.get("stars", 0),
                delta=adj["suggested_delta"],
                reason=adj.get("reason", ""),
                confidence=adj["confidence"],
            )


def cmd_adjust_rating(args) -> None:
    target = args.id_or_hash
    if len(target) < 10:
        map_hash = resolve_beatsaver_id(target)
        if not map_hash:
            print("Não foi possível resolver o ID.")
            return
    else:
        map_hash = target

    if args.delta is not None:
        delta = args.delta
    elif args.set_stars is not None:
        map_path = download_and_extract_map(map_hash)
        if not map_path:
            print("Falha ao baixar mapa para calcular delta.")
            return
        analysis = analyze_map_structure(map_path, include_patterns=True)
        if not analysis:
            return
        matched = next(
            (d for d in analysis["difficulties"] if d.get("difficulty") == args.difficulty), None
        )
        if not matched:
            print(f"Dificuldade {args.difficulty} não encontrada.")
            return
        features = {**matched, "bpm": analysis["bpm"]}
        base_pred, _ = predict_with_fallback(features)
        delta = args.set_stars - base_pred
    else:
        print("Especifique --delta ou --set-stars.")
        return

    ss_info    = get_scoresaber_leaderboard_info(map_hash, DIFF_NAME_TO_RANK.get(args.difficulty, 9))
    base_stars = ss_info.get("stars", 0) if ss_info else 0.0

    save_adjustment(
        map_hash=map_hash,
        difficulty=args.difficulty,
        base_stars=base_stars,
        delta=delta,
        reason=args.reason or "Ajuste manual",
        confidence="manual",
    )


def cmd_unranked(args) -> None:
    target = args.id_or_hash
    if len(target) < 10:
        map_hash = resolve_beatsaver_id(target)
        if not map_hash:
            print("Não foi possível resolver o ID no BeatSaver.")
            return
    else:
        map_hash = target

    map_path = download_and_extract_map(map_hash)
    if not map_path:
        print(f"Falha ao baixar/extrair o mapa {map_hash}.")
        return

    analysis = analyze_map_structure(map_path, include_patterns=True)
    if not analysis:
        print("Falha ao analisar o mapa.")
        return

    print(f"\nMúsica  : {analysis['song_name']}  [NÃO RANKEADO — estimativa]")
    print(f"BPM     : {analysis['bpm']}")
    print(f"Hash    : {map_hash}")
    print()

    class _FakeArgs:
        buff = 0.0
        nerf = 0.0

    _display_diff_table(analysis, None, _FakeArgs())

    print()
    print("Nota: Mapa não rankeado. Predições são estimativas baseadas em padrões físicos do mapa.")

    if args.verbose:
        print("\nDetalhes por dificuldade:")
        for diff in analysis["difficulties"]:
            print(f"\n  [{diff['difficulty']}]")
            styles = diff.get("map_styles", [])
            if isinstance(styles, str):
                import ast
                try:
                    styles = ast.literal_eval(styles)
                except Exception:
                    styles = [styles]
            print(f"    Estilos           : {', '.join(styles)}")
            print(f"    NPS               : {diff.get('nps', 0):.2f}")
            print(f"    Peak NPS          : {diff.get('peak_nps', 0)}")
            print(f"    Streams           : {diff.get('pat_stream_note_ratio', 0)*100:.1f}% das notas")
            print(f"    Stream BPM médio  : {diff.get('pat_stream_bpm_avg', 0):.0f}")
            print(f"    Jumps density     : {diff.get('pat_jump_density', 0):.3f}")
            print(f"    Crossover ratio   : {diff.get('pat_crossover_ratio', 0)*100:.1f}%")
            print(f"    Tech ratio        : {diff.get('pat_tech_ratio', 0)*100:.1f}%")
            print(f"    Parity breaks     : {diff.get('pat_parity_break_ratio', 0)*100:.1f}%")
            print(f"    Reset intensity   : {diff.get('pat_reset_intensity', 0):.1f}°")
            print(f"    Doubles ratio     : {diff.get('pat_double_ratio', 0)*100:.1f}%")
            print(f"    Hand dominance    : {diff.get('pat_hand_dominance', 0)*100:.1f}%")
            print(f"    Bombs             : {diff.get('bomb_count', 0)}")
            print(f"    Obstacles         : {diff.get('obstacle_count', 0)}")


def cmd_dataset_info(args) -> None:
    """Mostra estatísticas do dataset atual."""
    if not os.path.exists(DATASET_FILE):
        print("dataset.csv não encontrado. Rode 'download' primeiro.")
        return

    import csv as _csv
    rows = []
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("Dataset vazio.")
        return

    total = len(rows)
    unique_hashes = len({r.get("map_hash") for r in rows})

    # Contagem por dificuldade
    diff_counts: dict = {}
    for r in rows:
        d = r.get("difficulty", "?")
        diff_counts[d] = diff_counts.get(d, 0) + 1

    # Range de stars
    stars_vals = []
    for r in rows:
        try:
            stars_vals.append(float(r.get("stars", 0)))
        except Exception:
            pass

    print(f"\n{'─'*50}")
    print(f"  Dataset: {DATASET_FILE}")
    print(f"{'─'*50}")
    print(f"  Total de linhas    : {total}")
    print(f"  Músicas únicas     : {unique_hashes}")
    print(f"  Média diffs/música : {total/unique_hashes:.1f}")
    print()
    print("  Por dificuldade:")
    for d in ["Easy", "Normal", "Hard", "Expert", "ExpertPlus"]:
        count = diff_counts.get(d, 0)
        bar = "█" * (count * 30 // max(diff_counts.values(), default=1))
        print(f"    {d:<12} : {count:>5}  {bar}")
    print()
    if stars_vals:
        bins = {"< 3★": 0, "3–5★": 0, "5–7★": 0, "7–9★": 0, "9–11★": 0, "> 11★": 0}
        for s in stars_vals:
            if s < 3:   bins["< 3★"] += 1
            elif s < 5: bins["3–5★"] += 1
            elif s < 7: bins["5–7★"] += 1
            elif s < 9: bins["7–9★"] += 1
            elif s < 11:bins["9–11★"] += 1
            else:       bins["> 11★"] += 1
        print("  Distribuição de stars:")
        for label, count in bins.items():
            bar = "█" * (count * 30 // max(bins.values(), default=1))
            print(f"    {label:<8} : {count:>5}  {bar}")
        print(f"\n  Min: {min(stars_vals):.2f}★  Max: {max(stars_vals):.2f}★"
              f"  Média: {sum(stars_vals)/len(stars_vals):.2f}★")
    print(f"{'─'*50}\n")


def cmd_list_adjustments(args) -> None:
    adjustments = load_adjustments()
    if not adjustments:
        print("Nenhum ajuste salvo.")
        return
    print(f"\n{'Hash/Diff':<45} | {'Base★':>6} | {'Delta':>6} | {'Final★':>7} | {'Conf':>8} | Razão")
    print("─" * 110)
    for key, adj in adjustments.items():
        delta_str = f"+{adj['delta']:.2f}" if adj['delta'] >= 0 else f"{adj['delta']:.2f}"
        reason_short = adj.get("reason", "")[:38]
        print(
            f"{key:<45} | {adj.get('base_stars', 0):>6.2f} | "
            f"{delta_str:>6} | {adj.get('final_stars', 0):>7.2f} | "
            f"{adj.get('confidence', '?'):>8} | {reason_short}"
        )


# ─────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Beat Saber Star Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    p_dl = subparsers.add_parser(
        "download",
        help="Baixa e indexa mapas rankeados",
        description=(
            "Busca entradas rankeadas do ScoreSaber.\n"
            "--limit conta DIFICULDADES rankeadas (não músicas).\n"
            "Uma música com 3 dificuldades rankeadas = 3 entradas no dataset,\n"
            "mas o zip é baixado apenas uma vez.\n"
            "Retomável: entradas já no dataset.csv são puladas automaticamente."
        ),
    )
    p_dl.add_argument("--limit",   type=int, default=500,
                      help="Número de dificuldades rankeadas para buscar (padrão: 500)")
    p_dl.add_argument("--threads", type=int, default=4,
                      help="Threads paralelas para download (padrão: 4)")
    p_dl.add_argument("--force",   action="store_true",
                      help="Reprocessa mesmo entradas já no dataset")
    p_dl.set_defaults(func=cmd_download)

    # train
    p_tr = subparsers.add_parser("train", help="Treina o modelo de predição")
    p_tr.set_defaults(func=cmd_train)

    # analyze
    p_an = subparsers.add_parser("analyze", help="Analisa um mapa por hash ou BeatSaver ID")
    p_an.add_argument("id_or_hash", type=str)
    p_an.add_argument("--buff", type=float, default=0.0)
    p_an.add_argument("--nerf", type=float, default=0.0)
    p_an.set_defaults(func=cmd_analyze)

    # analyze-playlist
    p_pl = subparsers.add_parser("analyze-playlist", help="Analisa uma playlist .bplist")
    p_pl.add_argument("file", type=str)
    p_pl.add_argument("--interactive", action="store_true",
                      help="Permite buff/nerf interativo por dificuldade")
    p_pl.set_defaults(func=cmd_analyze_playlist)

    # performance
    p_pf = subparsers.add_parser("performance",
        help="Analisa a performance real dos players via ScoreSaber")
    p_pf.add_argument("id_or_hash", type=str)
    p_pf.add_argument("--difficulty", "-d", type=str, default="ExpertPlus",
                      choices=["Easy", "Normal", "Hard", "Expert", "ExpertPlus"])
    p_pf.add_argument("--stars", type=float, default=None)
    p_pf.add_argument("--suggest", action="store_true",
                      help="Calcula sugestão de ajuste de rating")
    p_pf.add_argument("--save", action="store_true",
                      help="Salva o ajuste sugerido automaticamente")
    p_pf.set_defaults(func=cmd_performance)

    # adjust-rating
    p_adj = subparsers.add_parser("adjust-rating",
        help="Aplica ajuste manual de rating para um mapa")
    p_adj.add_argument("id_or_hash", type=str)
    p_adj.add_argument("--difficulty", "-d", type=str, default="ExpertPlus",
                       choices=["Easy", "Normal", "Hard", "Expert", "ExpertPlus"])
    p_adj.add_argument("--delta", type=float, default=None,
                       help="Delta a aplicar (ex: 0.5 ou -1.2)")
    p_adj.add_argument("--set-stars", type=float, default=None,
                       help="Define diretamente as stars finais")
    p_adj.add_argument("--reason", type=str, default=None)
    p_adj.set_defaults(func=cmd_adjust_rating)

    # unranked
    p_ur = subparsers.add_parser("unranked",
        help="Estima stars de um mapa não rankeado")
    p_ur.add_argument("id_or_hash", type=str)
    p_ur.add_argument("--verbose", "-v", action="store_true",
                      help="Exibe detalhes de padrões por dificuldade")
    p_ur.set_defaults(func=cmd_unranked)

    # dataset-info
    p_di = subparsers.add_parser("dataset-info",
        help="Mostra estatísticas do dataset atual")
    p_di.set_defaults(func=cmd_dataset_info)

    # list-adjustments
    p_la = subparsers.add_parser("list-adjustments", help="Lista ajustes de rating salvos")
    p_la.set_defaults(func=cmd_list_adjustments)

    args = parser.parse_args()

    for d in [DOWNLOAD_DIR, EXTRACT_DIR]:
        os.makedirs(d, exist_ok=True)

    args.func(args)


if __name__ == "__main__":
    main()
