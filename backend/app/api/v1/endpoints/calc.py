"""POST /calc — calculadora de PP/sub-PP e ganho ponderado (+1pp)."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.pp_engine import decompose_pp, raw_pp_for_expected_gain

router = APIRouter()


class CalcRequest(BaseModel):
    stars: float = Field(gt=0, description="totalStars do mapa")
    accuracy: float = Field(gt=0, description="accuracy em % (0-100) ou fração (0-1)")
    share_acc: float = Field(0.34, ge=0)
    share_tech: float = Field(0.33, ge=0)
    share_speed: float = Field(0.33, ge=0)


class GainRequest(BaseModel):
    scores_pps: list[float] = Field(min_length=1)
    expected_pp: float = Field(1.0, gt=0)


@router.post("/calc")
async def calc_pp(req: CalcRequest) -> dict:
    result = decompose_pp(
        req.stars,
        req.accuracy,
        share_acc=req.share_acc,
        share_tech=req.share_tech,
        share_speed=req.share_speed,
    )
    return {k: round(v, 3) for k, v in result.items()}


@router.post("/calc/gain")
async def calc_gain(req: GainRequest) -> dict:
    """PP raw necessário na próxima jogada para ganhar ``expected_pp`` ponderado."""
    needed = raw_pp_for_expected_gain(req.scores_pps, expected_pp=req.expected_pp)
    return {"raw_pp_needed": round(needed, 3), "expected_weighted_gain": req.expected_pp}
