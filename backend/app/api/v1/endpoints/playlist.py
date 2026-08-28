"""Playlists .bplist (JSON renomeado) com syncURL para atualização automática.

- GET /playlists/ranked.bplist — todos os mapas rankeados (arquivo playlist.bplist);
- GET /playlists/latest.bplist — mapas da "batch atual" (novos, últimos 30 dias).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.playlist import render_bsbr_playlist

router = APIRouter()

NEW_MAPS_DAYS = 30


def _public_base(request: Request) -> str:
    """URL pública do host (funciona atrás do proxy nginx com TLS)."""
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip() or "https"
    host = request.headers.get("host") or request.url.hostname or ""
    return f"{proto}://{host}"


def _bplist_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/playlists/ranked.bplist")
async def get_playlist(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    base = _public_base(request)
    sync_url = f"{base}/api/v1/playlists/ranked.bplist"
    content = await render_bsbr_playlist(db, sync_url=sync_url)
    return _bplist_response(content, "playlist.bplist")


@router.get("/playlists/latest.bplist")
async def get_latest_playlist(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    base = _public_base(request)
    sync_url = f"{base}/api/v1/playlists/latest.bplist"
    content = await render_bsbr_playlist(db, sync_url=sync_url, days=NEW_MAPS_DAYS)
    return _bplist_response(content, "playlist-novos.bplist")
