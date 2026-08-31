"""Dependencies de autenticação de usuário do site (jogadores).

A identidade vem do cookie ``bsbr_user_session`` (HMAC-assinado, ver
``app.core.user_session``); o payload é o ``ss_id`` do ``Player``.
"""

from __future__ import annotations

from fastapi import Cookie, HTTPException

from app.core.user_session import verify_cookie


def require_user(bsbr_user_session: str | None = Cookie(default=None)) -> str:
    """Exige sessão válida; devolve o ss_id do jogador logado (401 se não)."""
    ss_id = verify_cookie(bsbr_user_session)
    if ss_id is None:
        raise HTTPException(status_code=401, detail="não autenticado")
    return ss_id


def optional_user(bsbr_user_session: str | None = Cookie(default=None)) -> str | None:
    """Devolve o ss_id se houver sessão válida; None caso contrário."""
    return verify_cookie(bsbr_user_session)
