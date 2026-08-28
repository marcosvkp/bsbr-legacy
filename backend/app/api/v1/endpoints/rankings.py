"""GET /rankings — ranking geral e por componente, com cache curto."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.db import get_db
from app.models import Player

router = APIRouter()

_COMPONENT_COLUMNS = {
    "total": Player.pp_total,
    "acc": Player.pp_acc,
    "tech": Player.pp_tech,
    "speed": Player.pp_speed,
}


@router.get("/rankings")
async def get_rankings(
    component: str = Query("total", pattern="^(total|acc|tech|speed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    country: str | None = Query(None, min_length=2, max_length=2),
    db: AsyncSession = Depends(get_db),
) -> dict:
    column = _COMPONENT_COLUMNS[component]
    cache_key = f"rankings:{component}:{page}:{page_size}:{(country or 'all').upper()}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    base = select(Player).where(Player.rank.is_not(None))
    if country:
        base = base.where(func.upper(Player.country) == country.upper())
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(column.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    payload = {
        "component": component,
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "rank": p.rank,
                "ss_id": p.ss_id,
                "name": p.name,
                "country": p.country,
                "avatar_url": p.avatar_url,
                "pp_total": round(p.pp_total, 2),
                "pp_acc": round(p.pp_acc, 2),
                "pp_tech": round(p.pp_tech, 2),
                "pp_speed": round(p.pp_speed, 2),
            }
            for p in rows
        ],
    }
    await cache.set_json(cache_key, payload, ttl=60)
    return payload
