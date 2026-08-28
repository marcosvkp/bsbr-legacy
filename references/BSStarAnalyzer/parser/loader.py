import json
import os
from typing import List, Tuple, Optional
from .beatmap import Beatmap

def _get_info_data(map_folder: str) -> Optional[dict]:
    """Carrega o arquivo Info.dat ou info.dat."""
    info_path = os.path.join(map_folder, "Info.dat")
    if not os.path.exists(info_path):
        info_path = os.path.join(map_folder, "info.dat")
    if not os.path.exists(info_path):
        return None
    try:
        with open(info_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def get_all_valid_difficulties(map_folder: str) -> List[Tuple[str, str, float]]:
    """
    Encontra todas as dificuldades em uma pasta que possuem um arquivo .dat
    e uma entrada correspondente com estrelas no scoresaber.json.

    Retorna:
        Uma lista de tuplas: (difficulty_name, difficulty_filename, stars)
    """
    info_data = _get_info_data(map_folder)
    if not info_data:
        return []

    scoresaber_path = os.path.join(map_folder, 'scoresaber.json')
    if not os.path.exists(scoresaber_path):
        return []
    try:
        with open(scoresaber_path, 'r') as f:
            scoresaber_data = json.load(f)
    except:
        return []

    valid_difficulties = []
    is_v2 = '_beatsPerMinute' in info_data
    beatmap_sets = info_data.get('_difficultyBeatmapSets', []) if is_v2 else info_data.get('difficultyBeatmapSets', [])

    for s in beatmap_sets:
        characteristic = s.get('_beatmapCharacteristicName') if is_v2 else s.get('beatmapCharacteristicName')
        if characteristic == 'Standard':
            diffs = s.get('_difficultyBeatmaps') if is_v2 else s.get('difficultyBeatmaps')
            for d in diffs:
                diff_name = d.get('_difficulty') if is_v2 else d.get('difficulty')
                # Verifica se a dificuldade tem estrelas e se o arquivo existe
                if diff_name in scoresaber_data and scoresaber_data[diff_name].get('stars'):
                    filename = d.get('_beatmapFilename') if is_v2 else d.get('beatmapFilename')
                    if filename and os.path.exists(os.path.join(map_folder, filename)):
                        stars = scoresaber_data[diff_name]['stars']
                        valid_difficulties.append((diff_name, filename, stars))
    
    return valid_difficulties

def load_specific_difficulty(map_folder: str, difficulty_filename: str) -> Optional[Tuple[Beatmap, float, str]]:
    """
    Carrega um arquivo de dificuldade específico e os metadados do mapa.

    Retorna:
        Uma tupla (beatmap, bpm, audio_path) ou None se falhar.
    """
    info_data = _get_info_data(map_folder)
    if not info_data:
        return None

    is_v2 = '_beatsPerMinute' in info_data
    bpm = info_data.get('_beatsPerMinute') if is_v2 else info_data.get('beatsPerMinute')
    song_filename = info_data.get('_songFilename') if is_v2 else info_data.get('songFilename')

    if not bpm or not song_filename:
        return None

    audio_path = os.path.join(map_folder, song_filename)
    diff_path = os.path.join(map_folder, difficulty_filename)

    if not os.path.exists(audio_path) or not os.path.exists(diff_path):
        return None

    try:
        with open(diff_path, 'r', encoding='utf-8') as f:
            map_json_data = json.load(f)
        
        beatmap = Beatmap()
        beatmap.parse_json(map_json_data)
        
        return beatmap, float(bpm), audio_path
    except Exception as e:
        print(f"Erro ao carregar/parsear {diff_path}: {e}")
        return None
