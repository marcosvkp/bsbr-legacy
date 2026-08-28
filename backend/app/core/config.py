from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "BSBR API"
    environment: str = "dev"  # dev | prod
    debug: bool = True

    # Banco de dados — Postgres em produção; SQLite para dev local sem serviços
    database_url: str = "sqlite+aiosqlite:///./storage/bsbr.db"

    # Redis — opcional em dev: sem URL, o cache cai para memória de processo
    redis_url: str | None = None

    # Celery — sem broker configurado usa memory://; CELERY_TASK_ALWAYS_EAGER=1
    # executa tarefas inline no processo da API (dev)
    celery_broker_url: str | None = None
    celery_task_always_eager: bool = False

    # APIs externas
    scoresaber_base_url: str = "https://scoresaber.com/api"
    beatsaver_base_url: str = "https://api.beatsaver.com"
    beatleader_base_url: str = "https://api.beatleader.com"

    # Rate limit ScoreSaber observado no legado: 350 req/min
    scoresaber_max_calls: int = 350
    scoresaber_period_seconds: int = 60

    # Integrações
    discord_webhook_url: str | None = None

    # Scorefeed ao vivo (WebSocket). BeatLeader desligado até o endpoint atual
    # do feed ser descoberto (wss://api.beatleader.xyz/scores/ws retorna 404 hoje)
    live_beatleader_enabled: bool = False

    # Admin: OAuth Discord quando configurado; X-Admin-Token como fallback
    admin_token: str | None = None
    discord_client_id: str | None = None
    discord_client_secret: str | None = None
    # Guild (servidor) cujos membros têm acesso ao painel; None = qualquer login
    discord_guild_id: str | None = None
    # URL pública do painel (usada no redirect_uri do OAuth e no cookie)
    admin_base_url: str = "http://localhost:18000"
    # Segredo para assinar o cookie de sessão do admin (default = admin_token)
    session_secret: str | None = None

    # Front-end
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
