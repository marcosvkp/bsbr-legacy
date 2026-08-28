"""
Cliente da API do BeatSaver: resolve mapa por id ou hash e baixa o zip.

Endpoints:
    https://api.beatsaver.com/maps/id/{id}
    https://api.beatsaver.com/maps/hash/{hash}
"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

BASE_URL = "https://api.beatsaver.com"
TIMEOUT = 30.0
USER_AGENT = "bsbr_analyzer/2.0 (BSBR rating pipeline)"


class BeatSaverError(RuntimeError):
    pass


def _is_hex_hash(source: str) -> bool:
    return len(source) == 40 and all(c in "0123456789abcdefABCDEF" for c in source)


def fetch_map_metadata(source: str) -> Dict[str, Any]:
    """
    Busca os metadados do mapa no BeatSaver.
    `source` pode ser o id numérico ou o hash (40 hex) do mapa.
    """
    if _is_hex_hash(source):
        url = f"{BASE_URL}/maps/hash/{source}"
    else:
        url = f"{BASE_URL}/maps/id/{source}"

    try:
        resp = httpx.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise BeatSaverError(f"Falha ao consultar BeatSaver ({url}): {exc}") from exc
    return resp.json()


def download_map_zip(metadata: Dict[str, Any]) -> bytes:
    """Baixa o conteúdo do zip via downloadURL dos metadados."""
    versions = metadata.get("versions") or []
    download_url = None
    for version in reversed(versions):
        download_url = version.get("downloadURL")
        if download_url:
            break
    if not download_url:
        # fallback para formato legado
        download_url = metadata.get("downloadURL")
    if not download_url:
        raise BeatSaverError("Metadados sem downloadURL.")

    try:
        resp = httpx.get(download_url, timeout=120.0, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise BeatSaverError(f"Falha ao baixar mapa ({download_url}): {exc}") from exc
    return resp.content


def extract_to_tempdir(zip_bytes: bytes) -> str:
    """Extrai o zip do mapa em um tempdir e retorna o caminho."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise BeatSaverError("Download não é um zip válido.") from exc
    tmpdir = tempfile.mkdtemp(prefix="bsbr_map_")
    archive.extractall(tmpdir)
    return tmpdir


def map_hash(metadata: Dict[str, Any]) -> str:
    """Hash da versão atual do mapa (versions[0].hash, fallback latestVersion)."""
    versions = metadata.get("versions") or []
    if versions and versions[0].get("hash"):
        return str(versions[0]["hash"]).lower()
    latest = metadata.get("latestVersion") or {}
    return str(latest.get("hash") or "").lower()


def map_name_mapper(metadata: Dict[str, Any]) -> tuple[str, str]:
    """Extrai (name, mapper) dos metadados."""
    name = metadata.get("name") or "Unknown"
    uploader = metadata.get("uploader") or {}
    mapper = metadata.get("metadata", {}).get("levelAuthorName") or uploader.get("name") or "Unknown"
    return name, mapper


def find_info_dat(map_dir: str) -> str:
    """Localiza Info.dat/info.dat na pasta extraída."""
    import os

    for candidate in ("Info.dat", "info.dat"):
        path = os.path.join(map_dir, candidate)
        if os.path.exists(path):
            return path
    # Busca recursiva simples (zips com subpasta)
    for root, _dirs, files in os.walk(map_dir):
        for fname in files:
            if fname.lower() == "info.dat":
                return os.path.join(root, fname)
    raise BeatSaverError("Info.dat não encontrado no zip do mapa.")


def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)
