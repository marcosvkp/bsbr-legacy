"""Reweight com persistência (Plan.md §3.4, fase F4).

- ``collect_suggestions``: roda o algoritmo puro sobre os scores JÁ SINCRONIZADOS
  no banco (o batch semanal sincroniza antes), cria/atualiza sugestões e
  auto-aplica as de confiança alta com |delta| ≤ 1★.
- ``apply_suggestion`` / ``reject_suggestion``: ação de staff; aplicar grava
  RatingHistory (antes→depois) e reescala os sub-stars proporcionalmente.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Difficulty,
    Map,
    MapStatus,
    RatingHistory,
    ReweightSuggestion,
    Score,
    SuggestionStatus,
)
from app.services.reweight import ReweightResult, analyze_difficulty

_SYSTEM_REVIEWER = "system"


def _scale_stars(total_before: float, delta: float, difficulty: Difficulty) -> tuple[float, float, float, float]:
    """Aplica delta no total preservando a proporção dos sub-stars."""
    new_total = max(0.1, total_before + delta)
    factor = new_total / total_before if total_before > 0 else 1.0
    return (
        round(new_total, 2),
        round((difficulty.acc_stars or 0.0) * factor, 2),
        round((difficulty.tech_stars or 0.0) * factor, 2),
        round((difficulty.speed_stars or 0.0) * factor, 2),
    )


async def _difficulty_scores(session: AsyncSession, difficulty_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(Score.acc, Score.score, Score.full_combo, Score.ss_player_pp)
            .where(Score.difficulty_id == difficulty_id)
            .order_by(Score.leaderboard_rank.nulls_last())
        )
    ).all()
    return [
        {
            "acc": acc or 0.0,
            "base_score": score or 0,
            "full_combo": bool(full_combo),
            "player_pp": ss_pp or 0.0,
        }
        for acc, score, full_combo, ss_pp in rows
    ]


async def _upsert_suggestion(
    session: AsyncSession,
    difficulty: Difficulty,
    result: ReweightResult,
) -> ReweightSuggestion:
    existing = (
        await session.scalars(
            select(ReweightSuggestion)
            .where(
                ReweightSuggestion.difficulty_id == difficulty.id,
                ReweightSuggestion.status == SuggestionStatus.PENDING,
            )
            .limit(1)
        )
    ).first()
    if existing is None:
        existing = ReweightSuggestion(difficulty_id=difficulty.id)
        session.add(existing)
    existing.observed_acc = result.median_acc
    existing.expected_acc = result.expected_acc
    existing.sample_size = result.sample_size
    existing.delta_stars = result.delta_stars
    existing.confidence = result.confidence
    existing.suggested_stars = result.suggested_stars
    existing.reason = result.reason[:256]
    return existing


async def _apply_to_difficulty(
    session: AsyncSession,
    difficulty: Difficulty,
    result: ReweightResult,
    *,
    reviewed_by: str,
    batch_id: int | None = None,
) -> RatingHistory:
    before_total = float(difficulty.total_stars or 0.0)
    new_total, new_acc, new_tech, new_speed = _scale_stars(before_total, result.delta_stars, difficulty)
    history = RatingHistory(
        difficulty_id=difficulty.id,
        total_stars_before=before_total,
        total_stars_after=new_total,
        acc_stars_before=difficulty.acc_stars,
        acc_stars_after=new_acc,
        tech_stars_before=difficulty.tech_stars,
        tech_stars_after=new_tech,
        speed_stars_before=difficulty.speed_stars,
        speed_stars_after=new_speed,
        reason=result.reason[:256],
        batch_id=batch_id,
        applied_by=reviewed_by,
    )
    session.add(history)
    difficulty.total_stars = new_total
    difficulty.acc_stars = new_acc
    difficulty.tech_stars = new_tech
    difficulty.speed_stars = new_speed
    return history


async def collect_suggestions(
    session: AsyncSession,
    *,
    batch_id: int | None = None,
    auto_apply: bool = True,
) -> dict[str, int]:
    """Avalia todas as dificuldades rankeadas. Retorna contadores."""
    difficulties = (
        (
            await session.execute(
                select(Difficulty)
                .join(Map, Difficulty.map_id == Map.id)
                .where(Map.status == MapStatus.RANKED)
                .where(Difficulty.total_stars.is_not(None))
            )
        )
        .scalars()
        .all()
    )

    stats = {"evaluated": 0, "pending": 0, "auto_applied": 0}
    for difficulty in difficulties:
        scores = await _difficulty_scores(session, difficulty.id)
        result = analyze_difficulty(scores, float(difficulty.total_stars))
        if result.confidence == "none":
            continue
        stats["evaluated"] += 1
        suggestion = await _upsert_suggestion(session, difficulty, result)
        if auto_apply and result.can_auto_apply:
            await _apply_to_difficulty(
                session, difficulty, result, reviewed_by=_SYSTEM_REVIEWER, batch_id=batch_id
            )
            suggestion.status = SuggestionStatus.APPLIED
            suggestion.reviewed_by = _SYSTEM_REVIEWER
            stats["auto_applied"] += 1
        else:
            stats["pending"] += 1
    await session.commit()
    return stats


async def apply_suggestion(
    session: AsyncSession, suggestion_id: int, *, reviewer: str, batch_id: int | None = None
) -> ReweightSuggestion:
    suggestion = await session.get(ReweightSuggestion, suggestion_id)
    if suggestion is None:
        raise ValueError(f"sugestão {suggestion_id} não encontrada")
    if suggestion.status != SuggestionStatus.PENDING:
        raise ValueError(f"sugestão {suggestion_id} já resolvida ({suggestion.status})")
    difficulty = await session.get(Difficulty, suggestion.difficulty_id)
    if difficulty is None or difficulty.total_stars is None:
        raise ValueError(f"dificuldade da sugestão {suggestion_id} inválida")

    result = ReweightResult(
        sample_size=suggestion.sample_size or 0,
        weighted_acc=None,
        median_acc=suggestion.observed_acc,
        fc_rate=None,
        expected_acc=suggestion.expected_acc,
        delta_stars=suggestion.delta_stars or 0.0,
        suggested_stars=suggestion.suggested_stars or difficulty.total_stars,
        confidence=suggestion.confidence or "low",
        direction="keep",
        reason=suggestion.reason or "aplicação manual",
        can_auto_apply=False,
    )
    await _apply_to_difficulty(session, difficulty, result, reviewed_by=reviewer, batch_id=batch_id)
    suggestion.status = SuggestionStatus.APPLIED
    suggestion.reviewed_by = reviewer
    await session.commit()
    return suggestion


async def reject_suggestion(
    session: AsyncSession, suggestion_id: int, *, reviewer: str
) -> ReweightSuggestion:
    suggestion = await session.get(ReweightSuggestion, suggestion_id)
    if suggestion is None:
        raise ValueError(f"sugestão {suggestion_id} não encontrada")
    if suggestion.status != SuggestionStatus.PENDING:
        raise ValueError(f"sugestão {suggestion_id} já resolvida ({suggestion.status})")
    suggestion.status = SuggestionStatus.REJECTED
    suggestion.reviewed_by = reviewer
    await session.commit()
    return suggestion
