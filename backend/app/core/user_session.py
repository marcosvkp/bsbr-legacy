"""Sessão de usuário do site (jogadores), cookie HMAC-assinado.

Espelha a técnica do painel admin (``app/api/v1/endpoints/oauth.py``) com um
cookie separado (``bsbr_user_session``) cujo payload é o ``ss_id`` do Player
(Steam ID). Não toca no cookie do admin — fluxos independentes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.core.config import get_settings

COOKIE_NAME = "bsbr_user_session"
SESSION_TTL_SECONDS = 30 * 24 * 3600  # 30 dias


def _session_secret() -> bytes:
    settings = get_settings()
    return (settings.session_secret or settings.admin_token or "bsbr-dev-secret").encode()


def _sign(payload: str, expiry: int) -> str:
    mac = hmac.new(_session_secret(), f"{payload}:{expiry}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def cookie_value(ss_id: str) -> str:
    expiry = int(time.time()) + SESSION_TTL_SECONDS
    return f"{ss_id}.{expiry}.{_sign(ss_id, expiry)}"


def verify_cookie(value: str | None) -> str | None:
    """Valida o cookie e devolve o ss_id; None se inválido/expirado."""
    if not value:
        return None
    try:
        ss_id, expiry, sig = value.split(".")
        if int(expiry) < time.time():
            return None
        if not hmac.compare_digest(sig, _sign(ss_id, int(expiry))):
            return None
        return ss_id
    except (ValueError, TypeError):
        return None


def user_session_ok(cookie: str | None) -> bool:
    return verify_cookie(cookie) is not None
