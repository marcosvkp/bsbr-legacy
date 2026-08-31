"""OAuth Steam (OpenID 2.0) para login de usuários do site.

O steamID64 do Steam é o ``ss_id`` do ScoreSaber no nosso banco
(``Player.ss_id``) — o login cria/atualiza o Player e emite o cookie
``bsbr_user_session`` (HMAC-assinado, ver ``app.core.user_session``).

Fluxo:
  GET /auth/steam/login  → redireciona para o OpenID do Steam (com state em
                           cookie e return_to/realm do nosso backend).
  GET /auth/steam/callback → valida state + OpenID (check_authentication),
                           extrai o steamID64, upsert do Player e seta sessão.
"""

from __future__ import annotations

import re
import secrets
import urllib.parse

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_user
from app.core.cache import cache
from app.core.config import get_settings
from app.core.db import get_db
from app.core.user_session import (
    COOKIE_NAME as USER_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    cookie_value,
    verify_cookie,
)
from app.models import Player

router = APIRouter()

OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
OPENID_NS = "http://specs.openid.net/auth/2.0"
OPENID_IDENTIFIER_SELECT = "http://specs.openid.net/auth/2.0/identifier_select"
STEAM_ID_RE = re.compile(r"^https://steamcommunity\.com/openid/id/(\d{17})$")
STEAM_PROFILE_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"

STATE_COOKIE = "bsbr_steam_state"


def _fail_redirect(settings, reason: str) -> RedirectResponse:
    redirect = RedirectResponse(f"{settings.frontend_base_url}?auth_error={urllib.parse.quote(reason)}")
    redirect.delete_cookie(STATE_COOKIE)
    return redirect


@router.get("/auth/steam/login")
async def steam_login() -> RedirectResponse:
    settings = get_settings()
    if not settings.steam_return_to:
        raise HTTPException(status_code=500, detail="steam_return_to não configurado")

    state = secrets.token_hex(16)
    return_to = f"{settings.steam_return_to}?state={state}"
    realm = urllib.parse.urlparse(settings.steam_return_to)
    realm_origin = f"{realm.scheme}://{realm.netloc}"

    params = {
        "openid.ns": OPENID_NS,
        "openid.mode": "checkid_setup",
        "openid.identity": OPENID_IDENTIFIER_SELECT,
        "openid.claimed_id": OPENID_IDENTIFIER_SELECT,
        "openid.return_to": return_to,
        "openid.realm": realm_origin,
    }
    redirect = RedirectResponse(f"{OPENID_ENDPOINT}?{urllib.parse.urlencode(params)}")
    redirect.set_cookie(
        STATE_COOKIE,
        state,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "prod",
        max_age=300,
    )
    return redirect


@router.get("/auth/steam/callback")
async def steam_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    query = request.query_params
    state_cookie = request.cookies.get(STATE_COOKIE)

    if not settings.steam_return_to:
        return _fail_redirect(settings, "steam_return_to não configurado")

    # CSRF: o state da query precisa bater com o cookie setado no login.
    if not state_cookie or query.get("state") != state_cookie:
        return _fail_redirect(settings, "state inválido")

    if query.get("openid.mode") != "id_res":
        return _fail_redirect(settings, "modo openid inválido")

    # Anti open-redirect: o return_to precisa ser exatamente o configurado
    # (com o state que emitimos).
    if query.get("openid.return_to") != f"{settings.steam_return_to}?state={state_cookie}":
        return _fail_redirect(settings, "return_to divergente")

    claimed = query.get("openid.claimed_id") or ""
    match = STEAM_ID_RE.match(claimed)
    if not match:
        return _fail_redirect(settings, "claimed_id inválido")
    steam_id = match.group(1)

    # Validação de autenticidade (OpenID check_authentication).
    openid_params = {k: v for k, v in query.items() if k.startswith("openid.")}
    openid_params["openid.mode"] = "check_authentication"
    is_valid = False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(OPENID_ENDPOINT, data=openid_params)
            is_valid = "is_valid:true" in resp.text.lower()
    except httpx.HTTPError:
        is_valid = False
    if not is_valid:
        return _fail_redirect(settings, "validação OpenID falhou")

    # Perfil Steam (nome/avatar/país) — opcional; falha não impede o login.
    profile: dict = {}
    if settings.steam_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                pr = await client.get(
                    STEAM_PROFILE_URL,
                    params={"key": settings.steam_api_key, "steamids": steam_id},
                )
                players = (pr.json().get("response") or {}).get("players") or []
                if players:
                    profile = players[0]
        except (httpx.HTTPError, ValueError):
            profile = {}

    # Upsert do Player (ss_id == steamID64 == identidade ScoreSaber).
    player = (await db.scalars(select(Player).where(Player.ss_id == steam_id))).first()
    if player is None:
        player = Player(
            ss_id=steam_id,
            bl_id=steam_id,
            name=(profile.get("personaname") or "Steam user")[:128],
            avatar_url=profile.get("avatarfull"),
            country=profile.get("loccountrycode"),
        )
        db.add(player)
    else:
        if profile.get("personaname"):
            player.name = profile["personaname"][:128]
        if profile.get("avatarfull"):
            player.avatar_url = profile["avatarfull"]
        if profile.get("loccountrycode"):
            player.country = profile["loccountrycode"]
        if not player.bl_id:
            player.bl_id = steam_id
    await db.commit()
    await cache.invalidate_prefix("player:")
    await cache.invalidate_prefix("rankings:")

    redirect = RedirectResponse(settings.frontend_base_url)
    redirect.delete_cookie(STATE_COOKIE)
    redirect.set_cookie(
        USER_COOKIE_NAME,
        cookie_value(steam_id),
        httponly=True,
        samesite="lax",
        secure=settings.environment == "prod",
        max_age=SESSION_TTL_SECONDS,
    )
    return redirect


@router.get("/auth/me")
async def me(
    ss_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    player = (await db.scalars(select(Player).where(Player.ss_id == ss_id))).first()
    if player is None:
        raise HTTPException(status_code=401, detail="jogador não encontrado")
    return {
        "ss_id": player.ss_id,
        "name": player.name,
        "avatar_url": player.avatar_url,
        "country": player.country,
        "rank": player.rank,
    }


@router.post("/auth/logout")
async def logout() -> Response:
    response = Response(content="{}", media_type="application/json")
    response.delete_cookie(USER_COOKIE_NAME)
    return response
