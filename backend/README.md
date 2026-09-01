# BSBR Backend

API e motor do ranking brasileiro de Beat Saber: **FastAPI + SQLAlchemy 2 async +
PostgreSQL + Redis + Celery**, com um módulo de **ML para análise de mapas**
(`bsbr_analyzer`) e **scores ao vivo** via WebSocket.

## Visão geral

O backend é o cérebro do BSBR. Ele:

1. **Analisa mapas** com ML (`bsbr_analyzer`): baixa do BeatSaver, parse V2/V3/V4,
   extrai ~50 features e prediz `totalStars` decomposto em **acc/tech/speed**.
2. **Calcula PP** com a curva exata do legado (`stars × 42.117208413 × curva(acc)`),
   golden-tested 1:1 contra `references/scorecalc.py`, e decompõe em sub-PPs.
3. **Roda o batch semanal** (Celery beat): sync ScoreSaber → reweight → ranking +
   snapshot → playlist → webhook Discord.
4. **Ingere scores ao vivo** (ScoreSaber + BeatLeader WebSocket) e expõe em `/live/recent`.
5. **Sustenta a comunidade**: OAuth Steam, sugestões de mapas com rate-limit,
   revisão no admin (abas).

## Estrutura

```
app/
├── main.py              # Cria a aplicação FastAPI e registra os routers
├── api/v1/
│   ├── router.py        # Monta todos os routers sob /api/v1
│   └── endpoints/       # health, rankings, players, maps, calc, playlist,
│                        # stars_bands, live, auth, suggestions, admin, oauth, og
├── core/
│   ├── config.py        # Settings (pydantic-settings) + get_settings()
│   ├── db.py            # engine/session async, task_session_factory (loop-isolado)
│   ├── cache.py         # Redis por event loop; memória de processo sem REDIS_URL
│   ├── ratelimit.py     # SlidingWindowLimiter (Redis ZSET ou deque em memória)
│   ├── user_session.py  # Cookie HMAC de sessão do usuário (bsbr_user_session)
│   └── tasks_app.py     # App Celery + beat_schedule
├── models/              # SQLAlchemy: Player, Map, Difficulty, Score, RankSnapshot,
│                        # RatingHistory, Batch, ReweightSuggestion, MapSuggestion,
│                        # StaffUser, WebhookConfig
├── schemas/             # Pydantic de request/response
├── services/
│   ├── pp_engine/       # Curva de PP + decomposição (golden-testado)
│   ├── ranking.py       # Pontuação e posições (usa PP interno do BSBR)
│   ├── qualification.py # Pipeline de qualificação de mapas
│   ├── reweight/        # Coleta, preview e aplicação de reweight
│   ├── suggestions.py   # Sugestões de mapas (metadata leve, sem ML)
│   ├── sync/            # Sync ScoreSaber (jogadores e scores)
│   ├── live/            # Scorefeed WebSocket + persistência + recents
│   ├── playlist.py      # Geração .bplist
│   └── og_image.py      # PNGs de share (OpenGraph)
├── integrations/        # Client HTTPs: scoresaber, beatleader, discord
└── workers/tasks.py     # Tasks Celery: batch.weekly, sync.br_daily, ping
bsbr_analyzer/           # ML de estrelas: parser, features, trainer, models
alembic/                 # Migrações (8 versões; alembic upgrade head)
tests/                   # 1429 testes (pytest + pytest-asyncio)
```

## Tasks do Celery (`app/workers/tasks.py`)

| Task | Schedule | O que faz |
|---|---|---|
| `batch.weekly` | Segunda 03:00 (`crontab(day_of_week=1, hour=3, minute=0)`) | Sync ScoreSaber → reweight → auto-aplica confiança alta / fila staff → ranking + snapshot → playlist → webhook Discord |
| `sync.br_daily` | 06:15 e 18:15 | Sync dos scores dos jogadores brasileiros |
| `ping` | — | Healthcheck do worker |

Sem broker configurado (dev) o Celery usa `memory://`; com
`CELERY_TASK_ALWAYS_EAGER=1` as tasks rodam inline no processo da API.

## Batch semanal — fluxo

1. **Sync** dos scores do ScoreSaber (paginação por `metadata.totalItems`).
2. **Reweight**: para cada dificuldade rankeada, compara a **mediana de acc observada**
   com a expected (`max(0.78, 0.98 − 0.015·stars)`), delta clamp ±2★.
   Confiança alta (|Δ| ≤ 1★) auto-aplica; o resto vai para a fila staff.
3. **Ranking + snapshot**: recalcula posições com o PP interno e congela em `rank_snapshot`.
4. **Playlist** `.bplist` dos rankeados + **webhook Discord** (multi-webhook configurável
   no admin) com o resumo da semana.
5. Auditoria completa: toda mudança de estrelas fica em `rating_history`.

## Scores ao vivo (`app/services/live/`)

- `runner.py` — consumidor WebSocket: **ScoreSaber** e **BeatLeader**
  (`wss://sockets.api.beatleader.com/scores`).
- `persist.py` — upsert por `(jogador, dificuldade)`, maior PP vence; resolve
  `bl_id → ss_id` (Steam ID direto) via `app/services/beatleader_resolve.py`.
- `bus.py` — publica no Redis (`bsbr:live`), mantém os `recents` de 2h e notifica
  o endpoint `/live/recent`; sem Redis o bus fica inerte sem quebrar.

## API — endpoints (`/api/v1`)

### Público

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Status da API |
| GET | `/rankings` | Ranking BR (componente + paginação + país) |
| GET | `/players/{ss_id}` | Perfil do jogador (medalhas, evolução) |
| GET | `/players/{ss_id}/scores` | Scores do jogador |
| GET | `/maps` | Catálogo (sort por stars/recent/name) |
| GET | `/maps/{hash}` | Detalhe do mapa + histórico de rating |
| GET | `/leaderboard/{hash}` | Placar do mapa (usado pelo plugin in-game) |
| GET | `/maps/qualification` | Fila de qualificação |
| GET | `/stars-bands` | Distribuição por faixa de estrelas |
| GET | `/live/recent` | Scores ao vivo recentes |
| POST | `/calc` | PP decomposto `{stars, accuracy, shares?}` |
| POST | `/calc/gain` | PP raw necessário para +1pp ponderado |
| GET | `/playlists/ranked.bplist` / `latest.bplist` | Playlists |
| GET | `/og/players/{ss_id}.png` / `/og/maps/{hash}.png` | Imagens OG |

### Comunidade (cookie `bsbr_user_session`)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/auth/steam/login` | Inicia OAuth Steam (OpenID 2.0) |
| GET | `/auth/steam/callback` | Retorno do Steam → upsert `Player` + sessão |
| GET | `/auth/me` | Usuário logado (401 sem sessão) |
| POST | `/auth/logout` | Encerra a sessão |
| POST | `/suggestions` | Sugere mapa (BeatSaver, **sem ML**; máx. 3 ativas) |
| GET | `/suggestions/me` | Sugestões do usuário logado |
| GET | `/suggestions` | Fila pública de sugestões |

### Admin (`X-Admin-Token` ou OAuth Discord)

| Método | Rota | Descrição |
|---|---|---|
| POST | `/admin/maps/qualify` | Analisa mapa com ML e cria candidato |
| POST | `/admin/maps/{id}/approve` · `/reject` | Decide candidato |
| POST | `/admin/maps/{id}/difficulties/{id}/rank` | Rankeia/desranqueia dificuldade (`is_ranked`) |
| POST | `/admin/reweight/collect` · `/preview` | Coleta/preview das sugestões de reweight |
| POST | `/admin/reweight/{id}/apply` · `/reject` | Aplica/recusa sugestão |
| POST | `/admin/batch/run` | Executa o batch manualmente |
| GET | `/admin/batches` | Histórico de batches |
| GET | `/admin/suggestions` | Revisão das sugestões da comunidade |
| POST | `/admin/suggestions/{id}/approve` · `/reject` | Aprova (cria `Map` candidate) / recusa |
| GET/POST/PATCH/DELETE | `/admin/webhooks` | CRUD de webhooks Discord |

## Configuração (env vars)

Veja [`config.py`](app/core/config.py) e `.env.example` na raiz. Principais:

| Var | Default | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./storage/bsbr.db` | Postgres em prod, SQLite em dev |
| `REDIS_URL` | (vazio) | Sem ele: cache/rate-limit/scorefeed em memória |
| `CELERY_BROKER_URL` / `CELERY_TASK_ALWAYS_EAGER` | — | Broker Celery; `1` roda inline |
| `ADMIN_TOKEN` | — | Header `X-Admin-Token` do painel |
| `SESSION_SECRET` | — | Assina cookies (admin + usuários); forte em prod |
| `DISCORD_WEBHOOK_URL` | — | Webhook padrão do batch |
| `STEAM_API_KEY` | — | Nome/avatar do login Steam (tolerante a falha) |
| `FRONTEND_BASE_URL` / `STEAM_RETURN_TO` | `http://localhost:3000` / — | Redirect pós-login e callback OpenID |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Origens do CORS (com credentials) |

## Desenvolvimento local

```bash
# API (SQLite + cache em memória — zero serviços)
cd backend
../.venv/Scripts/pip install -r requirements.txt
../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000   # docs em /docs

# Worker + beat (se for usar Redis como broker)
../.venv/Scripts/python -m celery -A app.core.tasks_app.celery_app worker --loglevel=info
../.venv/Scripts/python -m celery -A app.core.tasks_app.celery_app beat --loglevel=info

# Scorefeed ao vivo
../.venv/Scripts/python -m app.services.live.runner
```

## Testes

```bash
cd backend && ../.venv/Scripts/python -m pytest -q          # 1429 testes
../.venv/Scripts/python -m pytest tests/pp_engine/ -q      # golden do motor de PP
```

Pontos-chave dos testes:

- **Golden PP**: paridade total com o módulo legado (`references/scorecalc.py`), ~840 casos ±1e-9.
- **CI usa Redis real**: `REDIS_URL` aponta para o serviço do GitHub Actions — cobre o
  cache por loop, o rate-limit por IP (ZSET) e o scorefeed.
- **Loop-isolamento**: `get_db()`/`task_session_factory()`/`cache._ensure_redis()` criam
  recursos async dentro do loop do request/task — o `TestClient` do Starlette roda cada
  request num loop próprio, então um engine/cliente criado na importação quebra com
  "attached to a different loop" no Linux/CI.

## Migrações (Alembic)

```bash
cd backend && alembic upgrade head       # aplica
alembic revision -m "descricao"          # nova migração (autogenerate c/ cuidado)
```

## Docker

O backend tem `Dockerfile` próprio e é o mesmo build usado por `api`, `worker`, `beat`
e `live` no `docker-compose.yml` da raiz. O único serviço sem `--reload` (dev) é a `api`;
mudanças no código exigem restart do container.
