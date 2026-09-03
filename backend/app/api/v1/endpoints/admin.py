"""Endpoints administrativos (protegidos por X-Admin-Token até o OAuth Discord).

- Qualificação: analisar mapa do BeatSaver (candidato) e aprovar como rankeado.
- Fila de reweight: listar / aplicar / rejeitar sugestões.
- Rodar batch semanal manualmente.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.cache import cache
from app.core.config import get_settings
from app.core.db import get_db
from app.core.user_session import verify_cookie
from app.models import (
    Batch,
    Difficulty,
    Map,
    MapStatus,
    MapSuggestion,
    MapSuggestionStatus,
    Player,
    ReweightSuggestion,
    StaffUser,
    SuggestionStatus,
    WebhookConfig,
)
from app.services.qualification import approve_map, qualify_source
from app.services.reweight.service import (
    apply_suggestion,
    analyze_source,
    collect_suggestions,
    enqueue_manual,
    preview_difficulty,
    preview_suggestions,
    reject_suggestion,
    remove_manual_queue,
    apply_delta,
)
from app.services.suggestions import create_map_from_suggestion

def _escape_like(value: str) -> str:
    """Escapa curingas do LIKE para busca literal (%, _, \\)."""
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


router = APIRouter(prefix="/admin")


async def _staff_by_steam(db: AsyncSession, bsbr_user_session: str | None) -> StaffUser | None:
    """Resolve o staff pelo cookie de sessão Steam (ss_id na tabela staff_users)."""
    ss_id = verify_cookie(bsbr_user_session) if bsbr_user_session else None
    if ss_id is None:
        return None
    return await db.scalar(select(StaffUser).where(StaffUser.ss_id == ss_id).limit(1))


async def current_staff(
    x_admin_token: str | None = Header(default=None),
    bsbr_user_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> StaffUser:
    """Identidade do admin: sessão Steam (staff) ou X-Admin-Token de emergência.

    Distingue 401 (sem sessão válida) de 403 (logado mas não é staff) para o
    gate do frontend saber entre "Entrar com Steam" e "acesso restrito".
    Sem OAuth Discord por enquanto.
    """
    # 1. Sessão Steam validada contra staff_users (fonte primária de identidade,
    #    preserva role owner/staff real da tabela)
    ss_id = verify_cookie(bsbr_user_session) if bsbr_user_session else None
    if ss_id is not None:
        staff = await db.scalar(select(StaffUser).where(StaffUser.ss_id == ss_id).limit(1))
        if staff is not None:
            return staff

    # 2. X-Admin-Token de emergência (igual ao admin_token configurado) — vence a
    #    sessão Steam de um jogador que não é staff (ex.: admin com token aberto
    #    enquanto logado no site)
    expected = get_settings().admin_token
    if expected and x_admin_token == expected:
        return StaffUser(ss_id="token-admin", role="owner", name="Admin")

    # 3. Sessão Steam válida mas o jogador não faz parte da equipe
    if ss_id is not None:
        raise HTTPException(status_code=403, detail="acesso restrito à equipe do BSBR")

    # Token informado porém errado → tentativa de acesso negada (403).
    if x_admin_token:
        raise HTTPException(status_code=403, detail="acesso restrito à equipe do BSBR")

    # Sem nenhuma credencial válida
    raise HTTPException(status_code=401, detail="não autenticado")


async def require_admin(
    staff: StaffUser = Depends(current_staff),
) -> None:
    """Exige identidade de admin válida (StaffUser logado / token / Discord)."""
    return None


async def require_owner(staff: StaffUser = Depends(current_staff)) -> StaffUser:
    """Exige role owner (gestão de staff)."""
    if staff.role != "owner":
        raise HTTPException(status_code=403, detail="somente owner pode gerenciar a equipe")
    return staff


# ── Qualificação de mapas ──────────────────────────────────────────────────


class QualifyRequest(BaseModel):
    source: str = ""  # id do BeatSaver ou hash de 40 hex (obrigatório no /maps/qualify)
    # Ajuste manual de estrelas por dificuldade (ex.: {"ExpertPlus": 8.5})
    stars_override: dict[str, float] | None = None
    # Dificuldades inviáveis: não entram no pool rankeado (is_ranked=False)
    excluded_difficulties: list[str] = []


class ApproveRequest(BaseModel):
    ss_leaderboard_ids: dict[str, str]  # difficulty name -> leaderboard id ScoreSaber
    reviewer: str = "staff"
    excluded_difficulties: list[str] = []


class DifficultyRankRequest(BaseModel):
    ranked: bool = True


class AnalyzeRequest(BaseModel):
    source: str = ""
    map_id: int | None = None


class ApplyDeltaRequest(BaseModel):
    difficulty_id: int
    delta_stars: float
    reason: str | None = None


class ApplySuggestionRequest(BaseModel):
    reviewer: str = "staff"
    delta_override: float | None = None


class EnqueueRequest(BaseModel):
    difficulty_id: int
    method: str = "mix"  # ml | perf | mix


class DifficultyPreviewRequest(BaseModel):
    difficulty_id: int
    method: str = "mix"  # ml | perf | mix
    seed: int | None = None
    noise_sigma: float = 0.47


@router.post("/maps/qualify")
async def qualify(
    req: QualifyRequest,
    reviewer: str = "staff",
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Analisa o mapa no BeatSaver e persiste como candidato com predições."""
    if not req.source.strip():
        raise HTTPException(status_code=422, detail="source obrigatório (id ou hash do BeatSaver)")
    try:
        return await qualify_source(
            db, req.source, submitted_by=reviewer, stars_override=req.stars_override
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"análise falhou: {exc}") from exc


@router.get("/maps/candidates")
async def list_candidates(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fila de qualificação: candidatos (analisados) e enfileirados (aguardando aprovação)."""
    rows = (
        (
            await db.execute(
                select(Map)
                .where(Map.status.in_([MapStatus.CANDIDATE, MapStatus.QUALIFIED]))
                .options(joinedload(Map.difficulties))
                .order_by(Map.id.desc())
                .limit(50)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return {
        "items": [
            {
                "id": m.id,
                "hash": m.hash,
                "name": m.name,
                "mapper": m.mapper,
                "bpm": m.bpm,
                "status": m.status.value,
                "cover_url": m.cover_url,
                "submitted_by": m.submitted_by,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "difficulties": [
                    {
                        "id": d.id,
                        "name": d.name,
                        "total_stars": d.total_stars,
                        "ss_leaderboard_id": d.ss_leaderboard_id,
                        "is_ranked": d.is_ranked,
                    }
                    for d in m.difficulties
                ],
            }
            for m in rows
        ],
    }


@router.get("/maps/ranked")
async def list_ranked_maps(
    q: str | None = Query(None, max_length=80, description="Busca por nome do mapa ou mapper"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mapas rankeados com dificuldades — gerenciar quais continuam no pool."""
    filters = [Map.status == MapStatus.RANKED]
    if q:
        pattern = f"%{_escape_like(q)}%"
        filters.append(
            or_(
                Map.name.ilike(pattern, escape="\\"),
                Map.mapper.ilike(pattern, escape="\\"),
            )
        )
    total = (await db.execute(select(func.count()).select_from(Map).where(*filters))).scalar_one()
    rows = (
        (
            await db.execute(
                select(Map)
                .where(*filters)
                .options(joinedload(Map.difficulties))
                .order_by(Map.created_at.desc().nulls_last(), Map.id.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return {
        "items": [
            {
                "id": m.id,
                "hash": m.hash,
                "name": m.name,
                "mapper": m.mapper,
                "bpm": m.bpm,
                "cover_url": m.cover_url,
                "difficulties": [
                    {
                        "id": d.id,
                        "name": d.name,
                        "total_stars": d.total_stars,
                        "is_ranked": d.is_ranked,
                    }
                    for d in m.difficulties
                    if d.characteristic == "Standard"
                ],
            }
            for m in rows
        ],
        "total": total,
    }


@router.post("/maps/{map_id}/qualify")
async def qualify_map(
    map_id: int,
    req: QualifyRequest | None = None,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Move o candidato para a fila de qualificação (QUALIFIED).

    Aceita `stars_override` (mesmo formato do /maps/qualify) para ajustar as
    estrelas das dificuldades sem re-analisar o mapa.
    """
    m = await db.get(Map, map_id)
    if m is None:
        raise HTTPException(status_code=404, detail="mapa não encontrado")
    if m.status == MapStatus.QUALIFIED:
        # Idempotente: re-análise de mapa já enfileirado não precisa re-encaminhar.
        await cache.invalidate_prefix("maps:")
        return {"id": m.id, "hash": m.hash, "status": m.status.value}
    if m.status != MapStatus.CANDIDATE:
        raise HTTPException(status_code=422, detail=f"status atual: {m.status.value}")

    req = req or QualifyRequest(source="")
    override = req.stars_override or {}
    excluded = set(req.excluded_difficulties)
    difficulties = (await db.scalars(select(Difficulty).where(Difficulty.map_id == map_id))).all()
    for d in difficulties:
        if d.name in excluded:
            d.is_ranked = False
            continue
        d.is_ranked = True
        if d.name not in override:
            continue
        nova = float(override[d.name])
        if nova <= 0:
            continue
        old = float(d.total_stars or 0.0)
        if old > 0 and nova != old:
            ratio = nova / old
            d.acc_stars = round((d.acc_stars or 0.0) * ratio, 2)
            d.tech_stars = round((d.tech_stars or 0.0) * ratio, 2)
            d.speed_stars = round((d.speed_stars or 0.0) * ratio, 2)
        d.total_stars = round(nova, 2)

    m.status = MapStatus.QUALIFIED
    await db.commit()
    await cache.invalidate_prefix("maps:")
    return {"id": m.id, "hash": m.hash, "status": m.status.value}


@router.post("/maps/{map_id}/reject")
async def reject_map(
    map_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recusa o candidato/enfileirado (não vai para o pool rankeado)."""
    m = await db.get(Map, map_id)
    if m is None:
        raise HTTPException(status_code=404, detail="mapa não encontrado")
    if m.status == MapStatus.RANKED:
        raise HTTPException(status_code=422, detail="mapa rankeado não pode ser recusado")
    m.status = MapStatus.REMOVED
    await db.commit()
    await cache.invalidate_prefix("maps:")
    return {"id": m.id, "hash": m.hash, "status": m.status.value}


@router.post("/maps/{map_id}/approve")
async def approve(
    map_id: int,
    req: ApproveRequest,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        m = await approve_map(
            db,
            map_id,
            ss_leaderboard_ids=req.ss_leaderboard_ids,
            reviewer=req.reviewer,
            excluded_difficulties=req.excluded_difficulties,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await cache.invalidate_prefix("maps:")
    return {"id": m.id, "hash": m.hash, "status": m.status.value}


@router.post("/maps/{map_id}/difficulties/{difficulty_id}/rank")
async def set_difficulty_rank(
    map_id: int,
    difficulty_id: int,
    req: DifficultyRankRequest,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ativa/desativa uma dificuldade no pool rankeado (is_ranked).

    Dificuldades desativadas deixam de contar para ranking, reweight,
    playlists e leaderboards; o mapa permanece com o status atual.
    """
    d = (
        await db.scalars(
            select(Difficulty).where(Difficulty.id == difficulty_id, Difficulty.map_id == map_id)
        )
    ).first()
    if d is None:
        raise HTTPException(status_code=404, detail="dificuldade não encontrada")
    d.is_ranked = req.ranked
    if not req.ranked:
        d.ss_leaderboard_id = None
        d.ranked_at = None
    await db.commit()
    await cache.invalidate_prefix("maps:")
    await cache.invalidate_prefix("map:")
    return {
        "map_id": map_id,
        "difficulty_id": difficulty_id,
        "name": d.name,
        "is_ranked": d.is_ranked,
    }


# ── Reweight ───────────────────────────────────────────────────────────────


@router.get("/reweight/suggestions")
async def list_suggestions(
    status: SuggestionStatus = SuggestionStatus.PENDING,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        (
            await db.execute(
                select(ReweightSuggestion, Difficulty)
                .join(Difficulty, ReweightSuggestion.difficulty_id == Difficulty.id)
                .options(joinedload(Difficulty.map))
                .where(ReweightSuggestion.status == status)
                .order_by(ReweightSuggestion.created_at.desc())
                .limit(200)
            )
        )
        .all()
    )
    return {
        "status": status.value,
        "items": [
            {
                "id": s.id,
                "difficulty_id": s.difficulty_id,
                "map_name": d.map.name if d.map else None,
                "difficulty": d.name,
                "current_stars": d.total_stars,
                "observed_acc": s.observed_acc,
                "expected_acc": s.expected_acc,
                "sample_size": s.sample_size,
                "delta_stars": s.delta_stars,
                "suggested_stars": s.suggested_stars,
                "confidence": s.confidence,
                "reason": s.reason,
            }
            for s, d in rows
        ],
    }


class CollectRequest(BaseModel):
    auto_apply: bool = False


@router.post("/reweight/collect")
async def run_collect(
    req: CollectRequest,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stats = await collect_suggestions(db, auto_apply=req.auto_apply)
    await cache.invalidate_prefix("rankings:")
    await cache.invalidate_prefix("map:")
    await cache.invalidate_prefix("player:")
    return stats


@router.post("/reweight/preview")
async def run_preview(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Simulação em memória do reweight (impacto no ranking) — não persiste."""
    return await preview_suggestions(db)


@router.post("/reweight/{suggestion_id}/apply")
async def apply(
    suggestion_id: int,
    req: ApplySuggestionRequest | None = None,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aplica a sugestão; delta_override opcional ajusta o valor antes de aplicar."""
    suggestion = await apply_suggestion(
        db,
        suggestion_id,
        reviewer=(req.reviewer if req else "staff"),
        delta_override=(req.delta_override if req else None),
    )
    await cache.invalidate_prefix("rankings:")
    await cache.invalidate_prefix("map:")
    await cache.invalidate_prefix("player:")
    return {"id": suggestion.id, "status": suggestion.status.value}


@router.post("/reweight/analyze")
async def analyze(
    req: AnalyzeRequest,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Análise de reweight de UM mapa (por map_id ou source BeatSaver) — não persiste."""
    try:
        return await analyze_source(db, req.source or None, map_id=req.map_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/reweight/enqueue")
async def enqueue(
    req: EnqueueRequest,
    staff: StaffUser = Depends(current_staff),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enfileira reweight manual de uma dificuldade (aplicado no próximo batch).

    Reason honesto ML/perf conforme o método escolhido. NÃO muda as stars agora.
    """
    try:
        suggestion = await enqueue_manual(
            db, difficulty_id=req.difficulty_id, method=req.method, reviewer=staff.ss_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "id": suggestion.id,
        "difficulty_id": suggestion.difficulty_id,
        "delta_stars": suggestion.delta_stars,
        "suggested_stars": suggestion.suggested_stars,
        "status": suggestion.status,
        "reason": suggestion.reason,
    }


@router.delete("/reweight/enqueue/{difficulty_id}")
async def dequeue(
    difficulty_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a dificuldade da fila manual de reweight (não aplica)."""
    removed = await remove_manual_queue(db, difficulty_id)
    if not removed:
        raise HTTPException(status_code=404, detail="dificuldade não está na fila manual")
    return {"ok": True}


@router.post("/reweight/preview-difficulty")
async def preview_one(
    req: DifficultyPreviewRequest,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Preview de UMA dificuldade: delta pelo método + percentis com ruído seedado."""
    try:
        return await preview_difficulty(
            db,
            req.difficulty_id,
            method=req.method,
            seed=req.seed,
            noise_sigma=req.noise_sigma,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/reweight/apply-delta")
async def apply_delta_endpoint(
    req: ApplyDeltaRequest,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aplica delta manual de stars em uma dificuldade com recálculo imediato."""
    try:
        result = await apply_delta(db, req.difficulty_id, req.delta_stars, reviewer="staff")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await cache.invalidate_prefix("rankings:")
    await cache.invalidate_prefix("map:")
    await cache.invalidate_prefix("player:")
    return result


@router.post("/reweight/{suggestion_id}/reject")
async def reject(
    suggestion_id: int,
    reviewer: str = "staff",
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    suggestion = await reject_suggestion(db, suggestion_id, reviewer=reviewer)
    return {"id": suggestion.id, "status": suggestion.status.value}


# ── Batch ──────────────────────────────────────────────────────────────────


@router.post("/batch/run")
async def run_batch(_: None = Depends(require_admin)) -> dict:
    """Pipeline completa do batch (sync → reweight → ranking → snapshot) inline."""
    from app.workers.tasks import run_weekly_batch

    stats = await run_weekly_batch()
    await cache.invalidate_prefix("rankings:")
    await cache.invalidate_prefix("maps:")
    await cache.invalidate_prefix("map:")
    await cache.invalidate_prefix("player:")
    return stats


@router.get("/batches")
async def list_batches(
    limit: int = Query(50, ge=1, le=200),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Auditoria: execuções de batch (manuais e semanais) com status e stats."""
    rows = (
        (await db.execute(select(Batch).order_by(Batch.started_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": b.id,
                "kind": b.kind.value,
                "started_at": b.started_at.isoformat() if b.started_at else None,
                "finished_at": b.finished_at.isoformat() if b.finished_at else None,
                "running": b.finished_at is None,
                "stats": b.stats,
            }
            for b in rows
        ],
    }


# ── Sugestões de mapas (jogadores logados) ───────────────────────────────


def _suggestion_item(s: MapSuggestion, player: Player | None) -> dict:
    return {
        "id": s.id,
        "ss_id": s.ss_id,
        "hash": s.hash,
        "beatsaver_id": s.beatsaver_id,
        "name": s.name,
        "mapper": s.mapper,
        "bpm": s.bpm,
        "cover_url": s.cover_url,
        "note": s.note,
        "status": s.status.value,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
        "player_name": player.name if player else None,
        "player_avatar": player.avatar_url if player else None,
        "player_country": player.country if player else None,
    }


@router.get("/suggestions")
async def list_map_suggestions(
    status: str | None = Query(None, description="pending | approved | rejected"),
    limit: int = Query(12, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sugestões de mapas com o jogador que sugeriu — revisão paginada."""
    filters = []
    if status:
        try:
            filters.append(MapSuggestion.status == MapSuggestionStatus(status))
        except ValueError:
            raise HTTPException(status_code=422, detail="status inválido")
    total = (
        await db.scalar(select(func.count()).select_from(MapSuggestion).where(*filters))
    ) or 0
    rows = (
        await db.execute(
            select(MapSuggestion, Player)
            .join(Player, Player.ss_id == MapSuggestion.ss_id, isouter=True)
            .where(*filters)
            .order_by(MapSuggestion.created_at.desc(), MapSuggestion.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [_suggestion_item(s, p) for s, p in rows],
        "total": total,
        "page": offset // limit,
        "page_size": limit,
    }


@router.post("/suggestions/{suggestion_id}/approve")
async def approve_map_suggestion(
    suggestion_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aprova a sugestão: cria um Map candidate SEM ML (metadata já salva).

    Se o mapa já existe (mesmo hash — ex.: candidato, na fila ou rankeado),
    vincula a sugestão ao mapa existente em vez de duplicar (`linked: true`).
    """
    suggestion = await db.get(MapSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="sugestão não encontrada")
    if suggestion.status != MapSuggestionStatus.PENDING:
        raise HTTPException(status_code=422, detail="sugestão já revisada")

    existing = await db.scalar(select(Map).where(Map.hash == suggestion.hash).limit(1))
    if existing is not None:
        suggestion.status = MapSuggestionStatus.APPROVED
        suggestion.reviewed_at = datetime.now(timezone.utc)
        suggestion.reviewed_by = "admin"
        await db.commit()
        await cache.invalidate_prefix("maps:")
        return {"id": suggestion.id, "status": "approved", "map_id": existing.id, "linked": True}

    created = await create_map_from_suggestion(db, suggestion)
    suggestion.status = MapSuggestionStatus.APPROVED
    suggestion.reviewed_at = datetime.now(timezone.utc)
    suggestion.reviewed_by = "admin"
    await db.commit()
    await cache.invalidate_prefix("maps:")
    return {"id": suggestion.id, "status": "approved", "map_id": created.id}


@router.post("/suggestions/{suggestion_id}/reject")
async def reject_map_suggestion(
    suggestion_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    suggestion = await db.get(MapSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="sugestão não encontrada")
    if suggestion.status != MapSuggestionStatus.PENDING:
        raise HTTPException(status_code=422, detail="sugestão já revisada")
    suggestion.status = MapSuggestionStatus.REJECTED
    suggestion.reviewed_at = datetime.now(timezone.utc)
    suggestion.reviewed_by = "admin"
    await db.commit()
    return {"id": suggestion.id, "status": "rejected"}


# ── Webhooks do Discord (reweight) ───────────────────────────────────────


def _webhook_item(w: WebhookConfig) -> dict:
    return {
        "id": w.id,
        "url": w.url,
        "label": w.label,
        "enabled": w.enabled,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


class WebhookRequest(BaseModel):
    url: str
    label: str | None = None


class WebhookPatch(BaseModel):
    enabled: bool


@router.get("/webhooks")
async def list_webhooks(
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (await db.scalars(select(WebhookConfig).order_by(WebhookConfig.id))).all()
    return {"items": [_webhook_item(w) for w in rows]}


@router.post("/webhooks", status_code=201)
async def create_webhook(
    body: WebhookRequest,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    url = body.url.strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=422, detail="URL inválida")
    exists = await db.scalar(select(WebhookConfig.id).where(WebhookConfig.url == url).limit(1))
    if exists is not None:
        raise HTTPException(status_code=409, detail="webhook já cadastrado")
    webhook = WebhookConfig(url=url, label=(body.label or "").strip() or None)
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)
    return _webhook_item(webhook)


@router.patch("/webhooks/{webhook_id}")
async def patch_webhook(
    webhook_id: int,
    body: WebhookPatch,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    webhook = await db.get(WebhookConfig, webhook_id)
    if webhook is None:
        raise HTTPException(status_code=404, detail="webhook não encontrado")
    webhook.enabled = body.enabled
    await db.commit()
    await db.refresh(webhook)
    return _webhook_item(webhook)


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    webhook = await db.get(WebhookConfig, webhook_id)
    if webhook is None:
        raise HTTPException(status_code=404, detail="webhook não encontrado")
    await db.delete(webhook)
    await db.commit()


# ---------------------------------------------------------------------------
# Staff (equipe do admin) — autenticada por Steam session contra staff_users
# ---------------------------------------------------------------------------


class AddStaffRequest(BaseModel):
    ss_id: str
    role: str = "staff"


@router.get("/me")
async def admin_me(staff: StaffUser = Depends(current_staff)) -> dict:
    """Identidade do admin logado (gate do frontend)."""
    return {"ss_id": staff.ss_id, "name": staff.name, "role": staff.role}


@router.get("/staff")
async def list_staff(_: None = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(select(StaffUser).order_by(StaffUser.role, StaffUser.ss_id))).all()
    return {"items": [_staff_item(s) for s in rows]}


@router.post("/staff")
async def add_staff(
    body: AddStaffRequest,
    _: StaffUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Adiciona um membro da equipe pelo Steam ID (ss_id)."""
    ss_id = body.ss_id.strip()
    if not (ss_id.isdigit() and len(ss_id) == 17):
        raise HTTPException(status_code=422, detail="ss_id inválido (deve ser o Steam ID de 17 dígitos)")
    if await db.scalar(select(StaffUser).where(StaffUser.ss_id == ss_id).limit(1)):
        raise HTTPException(status_code=409, detail="esse ss_id já é da equipe")

    player = await db.scalar(select(Player).where(Player.ss_id == ss_id).limit(1))
    role = body.role if body.role in ("owner", "staff") else "staff"
    member = StaffUser(ss_id=ss_id, role=role, name=player.name if player else None, created_by="admin")
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return _staff_item(member)


@router.delete("/staff/{member_id}")
async def remove_staff(
    member_id: int,
    me: StaffUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove um membro; não permite remover o último owner."""
    member = await db.get(StaffUser, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="membro não encontrado")

    owners = (
        await db.scalars(select(StaffUser).where(StaffUser.role == "owner").order_by(StaffUser.id))
    ).all()
    if member.role == "owner" and len(owners) <= 1:
        raise HTTPException(status_code=422, detail="não é possível remover o último owner")
    if member.ss_id == me.ss_id:
        raise HTTPException(status_code=422, detail="você não pode se remover (use outro owner)")

    await db.delete(member)
    await db.commit()
    return {"ok": True}


def _staff_item(m: StaffUser) -> dict:
    return {"id": m.id, "ss_id": m.ss_id, "name": m.name, "role": m.role}
