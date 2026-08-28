"""GET /playlists/ranked.bplist — playlist das mapas rankeados."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.playlist import render_bsbr_playlist

router = APIRouter()


@router.get("/playlists/ranked.bplist")
async def get_playlist(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    base_url = str(request.base_url).rstrip("/")
    content = await render_bsbr_playlist(db, sync_url=f"{base_url}/api/v1/playlists/ranked.bplist")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="bsbr_ranked.bplist"'},
    )
