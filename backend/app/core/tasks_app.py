from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "bsbr",
    broker=settings.celery_broker_url or "memory://",
    backend=settings.redis_url,  # results opcionais; tarefas locais rodam eager
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    timezone="UTC",
    enable_utc=True,
    # Batch semanal: segunda-feira 03:00 UTC (Plan.md §3.4)
    beat_schedule={
        "weekly-reweight-batch": {
            "task": "batch.weekly",
            "schedule": crontab(day_of_week=1, hour=3, minute=0),
        },
        # Complemento do scorefeed ao vivo: re-sync dos leaderboards BR 2x/dia
        # (o feed do WS depende de tráfego mundial; o re-sync garante cobertura BR)
        "sync-br-scores": {
            "task": "sync.br_daily",
            "schedule": crontab(hour=[6, 18], minute=15),
        },
    },
)
