"""Endpoints administrativos (protegidos por X-Admin-Token até o OAuth Discord).

- Qualificação: analisar mapa do BeatSaver (candidato) e aprovar como rankeado.
- Fila de reweight: listar / aplicar / rejeitar sugestões.
- Rodar batch semanal manualmente.
"""

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Batch, Difficulty, Map, MapStatus, ReweightSuggestion, SuggestionStatus
from app.services.qualification import approve_map, qualify_source
from app.services.reweight.service import apply_suggestion, collect_suggestions, reject_suggestion

from .oauth import admin_session_ok

router = APIRouter(prefix="/admin")


async def require_admin(
    x_admin_token: str | None = Header(default=None),
    bsbr_admin_session: str | None = Cookie(default=None),
) -> None:
    """Aceita sessão OAuth Discord (cookie) ou o X-Admin-Token de fallback."""
    if admin_session_ok(bsbr_admin_session):
        return
    expected = get_settings().admin_token
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="token de admin inválido")


# ── Qualificação de mapas ──────────────────────────────────────────────────


class QualifyRequest(BaseModel):
    source: str = ""  # id do BeatSaver ou hash de 40 hex (obrigatório no /maps/qualify)
    # Ajuste manual de estrelas por dificuldade (ex.: {"ExpertPlus": 8.5})
    stars_override: dict[str, float] | None = None


class ApproveRequest(BaseModel):
    ss_leaderboard_ids: dict[str, str]  # difficulty name -> leaderboard id ScoreSaber
    reviewer: str = "staff"


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
                .order_by(Map.id.desc())
                .limit(50)
            )
        )
        .scalars()
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
            }
            for m in rows
        ],
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
    if m.status != MapStatus.CANDIDATE:
        raise HTTPException(status_code=422, detail=f"status atual: {m.status.value}")

    override = (req or QualifyRequest(source="")).stars_override or {}
    if override:
        difficulties = (
            (await db.scalars(select(Difficulty).where(Difficulty.map_id == map_id))).all()
        )
        for d in difficulties:
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
            db, map_id, ss_leaderboard_ids=req.ss_leaderboard_ids, reviewer=req.reviewer
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await cache.invalidate_prefix("maps:")
    return {"id": m.id, "hash": m.hash, "status": m.status.value}


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


@router.post("/reweight/{suggestion_id}/apply")
async def apply(
    suggestion_id: int,
    reviewer: str = "staff",
    _: None = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    suggestion = await apply_suggestion(db, suggestion_id, reviewer=reviewer)
    await cache.invalidate_prefix("rankings:")
    await cache.invalidate_prefix("map:")
    return {"id": suggestion.id, "status": suggestion.status.value}


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
