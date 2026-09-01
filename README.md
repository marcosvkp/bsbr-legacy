# BSBR — Beat Saber Brasil Ranking

Ranking brasileiro de Beat Saber com **PP multi-componente** (acc / tech / speed),
**batch semanal de ranqueamento com reweight**, **placares ao vivo** e um
**plugin in-game** — em [bsbr.pro](https://bsbr.pro).

Backend **FastAPI + PostgreSQL + Redis + Celery** e front-end **Next.js 16**.

## O que o BSBR faz

| | |
|---|---|
| **Ranking BR** | Ranqueia jogadores brasileiros com PP próprio (acc/tech/speed), curva herdada do legado e golden-tested 1:1 |
| **Análise de mapas com ML** | `bsbr_analyzer` baixa o mapa do BeatSaver, faz parse V2/V3/V4 e prediz estrelas decompostas em acc/tech/speed |
| **Batch semanal** | Celery beat: sync ScoreSaber → reweight (mediana de acc observada vs. expected) → auto-aplica ou fila staff → ranking + snapshot → playlist → webhook Discord |
| **Scores ao vivo** | Scorefeed via WebSocket (ScoreSaber + BeatLeader) persistido e exposto em `/ao-vivo` |
| **Comunidade** | Login com **OAuth Steam** (steamID64 = identidade ScoreSaber) + **sugestões de mapas** (máx. 3 ativas) |
| **Plugin in-game** | Leaderboard do BSBR dentro do Beat Saber (BSIPA), top 10 por mapa com logo e células customizadas |

## Estrutura do repositório

```
.
├── backend/    # FastAPI + SQLAlchemy 2 async + Alembic + Celery + bsbr_analyzer (ML)
├── frontend/   # Next.js 16 (App Router) · TypeScript · Tailwind
├── plugin/     # Plugin in-game BSIPA (C# / .NET Framework 4.8) — leaderboard do BSBR
├── references/ # Legado (bsbr, BSStarAnalyzer) e materiais de estudo
├── Plan.md     # Plano de recriação completo (design, dados, roadmap)
└── .github/    # CI: pytest (backend) + build (frontend)
```

Cada subprojeto tem seu próprio README: [`backend/README.md`](./backend/README.md),
[`frontend/README.md`](./frontend/README.md), [`plugin/README.md`](./plugin/README.md).

## Stack

| Camada | Tech |
|---|---|
| Backend | FastAPI · SQLAlchemy 2 async · Alembic · Celery |
| Dados | PostgreSQL 16 (dev local: SQLite) · Redis 7 (cache / rate-limit / scorefeed) |
| ML | `bsbr_analyzer` (parser V2/V3/V4 + ~50 features + sub-stars heurísticos) |
| Front-end | Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 |
| Plugin | C# · BSIPA · LeaderboardCore · BSML · SiraUtil |

## API (`/api/v1`, OpenAPI em `/docs`)

```
# Público
GET  /health
GET  /rankings?component=total|acc|tech|speed&page=&country=
GET  /players/{ss_id}              · perfil, medalhas, evolução semanal
GET  /players/{ss_id}/scores
GET  /maps?sort=stars|recent|name  · catálogo ranqueado + qualificação
GET  /maps/{hash}                  · detalhe do mapa + histórico de rating
GET  /leaderboard/{hash}           · placar do mapa (usado pelo plugin in-game)
GET  /stars-bands                  · distribuição por faixa de estrelas
GET  /live/recent                  · scores recentes ao vivo
POST /calc                         · {stars, accuracy, shares?} → PP decomposto
POST /calc/gain                    · quanto falta para +1pp ponderado
GET  /playlists/ranked.bplist      · playlist de todos os rankeados
GET  /og/{players|maps}/...png     · imagens OG (share social)

# Login / comunidade
GET  /auth/steam/login             · OAuth Steam (OpenID 2.0)
GET  /auth/steam/callback          · retorno do Steam → cria/atualiza Player
GET  /auth/me                      · sessão do usuário logado
POST /auth/logout
POST /suggestions                  · sugerir mapa (metadata do BeatSaver, sem ML)
GET  /suggestions/me               · "minhas sugestões" (máx. 3 ativas)
GET  /suggestions                  · fila pública de sugestões

# Admin (header X-Admin-Token ou OAuth Discord)
POST /admin/maps/qualify           · analisar mapa com ML
POST /admin/maps/{id}/approve|reject
POST /admin/maps/{id}/difficulties/{id}/rank
POST /admin/reweight/collect|preview
POST /admin/reweight/{id}/apply|reject
POST /admin/batch/run              · executar o batch semanal manualmente
GET  /admin/batches                · histórico de batches
GET  /admin/suggestions            · revisar sugestões da comunidade
POST /admin/suggestions/{id}/approve|reject
GET/POST/PATCH/DELETE /admin/webhooks · webhooks Discord
```

## Desenvolvimento local

### Sem Docker (API + SQLite, zero serviços externos)

```bash
# Backend
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# Analisar um mapa real do BeatSaver
cd backend && ../.venv/Scripts/python -m bsbr_analyzer <map_id_ou_hash>

# Testes (1400+)
cd backend && ../.venv/Scripts/python -m pytest -q

# Front-end
cd frontend && npm install && npm run dev   # http://localhost:3000
```

### Docker (stack completa: postgres + redis + api + worker + beat + live + web)

```bash
cp .env.example .env
docker compose up --build
# api :8000 · web :3000 · postgres :5432 · redis :6379
# (portas configuráveis via .env — o host local usa API_PORT=18000,
#  POSTGRES_PORT=15432 e REDIS_PORT=16379 quando as padrão estão ocupadas)
```

## Migrações

```bash
cd backend && alembic upgrade head   # dev SQLite e prod Postgres
```

## CI (GitHub Actions)

No push para `master`/PR o CI roda dois jobs:

- **Backend**: `pytest` completo contra **Postgres-independente** (SQLite em arquivo por teste) com **Redis real** de serviço (`REDIS_URL`) — cobre o cache, o rate-limit e o scorefeed sem falso verde de memória.
- **Frontend**: `npm ci` + `next build` (gate do Next 16; lint com 9 erros pré-existentes documentados no workflow).

## Garantias de correção

- **Golden tests** travam a curva de PP contra o módulo legado original (~840 casos, ±1e-9) — `backend/tests/pp_engine/`.
- Σ sub-PP == PP total em qualquer accuracy; Σ sub-stars == total stars (testado).
- Reweight com auditoria completa (`rating_history` antes→depois, nunca mutação silenciosa).
- Loop-isolamento de recursos async: Redis e engine do banco são criados por event loop nas tasks Celery (`task_session_factory`), evitando "Event loop is closed" em produção e no CI.

## Documentação

- [`Plan.md`](./Plan.md) — plano de recriação: design do rating, modelo de dados, roadmap por fases.
- [`backend/README.md`](./backend/README.md) — arquitetura, endpoints, env vars, tasks do Celery.
- [`frontend/README.md`](./frontend/README.md) — páginas, estrutura, dev.
- [`plugin/README.md`](./plugin/README.md) — plugin in-game: instalação, build, config.
