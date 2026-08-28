"""OAuth Discord para o painel admin (fallback: X-Admin-Token).

Fluxo: /admin/oauth/login redireciona para o Discord; o callback troca o
`code` por um token, valida o usuário (e a guild se configurada) e emite um
cookie de sessão HMAC-assinado (`bsbr_admin_session`). Sem credenciais
configuradas, os endpoints de OAuth respondem 400 e o painel continua
funcionando via X-Admin-Token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time

import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import RedirectResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
USER_URL = "https://discord.com/api/users/@me"
GUILD_URL = "https://discord.com/api/users/@me/guilds"
COOKIE_NAME = "bsbr_admin_session"
SESSION_TTL_SECONDS = 12 * 60 * 60  # 12h


def _session_secret() -> bytes:
    settings = get_settings()
    return (settings.session_secret or settings.admin_token or "bsbr-dev-secret").encode()


def _sign(payload: str, expiry: int) -> str:
    mac = hmac.new(_session_secret(), f"{payload}:{expiry}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def _cookie_value(discord_id: str) -> str:
    expiry = int(time.time()) + SESSION_TTL_SECONDS
    return f"{discord_id}.{expiry}.{_sign(discord_id, expiry)}"


def _verify_cookie(value: str) -> str | None:
    try:
        discord_id, expiry, sig = value.split(".")
        if int(expiry) < time.time():
            return None
        if not hmac.compare_digest(sig, _sign(discord_id, int(expiry))):
            return None
        return discord_id
    except (ValueError, TypeError):
        return None


def admin_session_ok(cookie: str | None) -> bool:
    """True se o cookie de sessão do admin é válido (usado pelo require_admin)."""
    if not cookie:
        return False
    return _verify_cookie(cookie) is not None


def _oauth_enabled() -> bool:
    settings = get_settings()
    return bool(settings.discord_client_id and settings.discord_client_secret)


@router.get("/oauth/login")
async def oauth_login() -> RedirectResponse:
    settings = get_settings()
    if not _oauth_enabled():
        raise HTTPException(status_code=400, detail="OAuth Discord não configurado (use X-Admin-Token)")
    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": f"{settings.admin_base_url}/api/v1/admin/oauth/callback",
        "response_type": "code",
        "scope": "identify guilds",
    }
    return RedirectResponse(f"{AUTHORIZE_URL}?{__import__('urllib.parse', fromlist=['urlencode']).urlencode(params)}")


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str | None = Query(None),
) -> RedirectResponse:
    settings = get_settings()
    if not _oauth_enabled():
        raise HTTPException(status_code=400, detail="OAuth Discord não configurado")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(
                TOKEN_URL,
                data={
                    "client_id": settings.discord_client_id,
                    "client_secret": settings.discord_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"{settings.admin_base_url}/api/v1/admin/oauth/callback",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_resp.status_code != 200:
                logger.warning("discord token exchange falhou: %s", token_resp.status_code)
                raise HTTPException(status_code=401, detail="falha na autenticação com o Discord")
            access_token = token_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            user_resp = await client.get(USER_URL, headers=headers)
            user = user_resp.json()
            discord_id = str(user.get("id") or "")

            if settings.discord_guild_id:
                guilds_resp = await client.get(GUILD_URL, headers=headers)
                guilds = guilds_resp.json()
                allowed = any(
                    str(g.get("id")) == settings.discord_guild_id for g in guilds
                )
                if not allowed:
                    raise HTTPException(status_code=403, detail="você não é membro da guild autorizada")
    except httpx.HTTPError as exc:
        logger.exception("erro no fluxo OAuth Discord")
        raise HTTPException(status_code=502, detail=f"erro de rede no OAuth: {exc}")

    response = RedirectResponse(f"{settings.admin_base_url}/admin")
    response.set_cookie(
        COOKIE_NAME,
        _cookie_value(discord_id),
        httponly=True,
        samesite="lax",
        secure=settings.environment == "prod",
        max_age=SESSION_TTL_SECONDS,
    )
    return response


@router.post("/oauth/logout")
async def oauth_logout() -> dict:
    response = Response(content="{}", media_type="application/json")
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}
