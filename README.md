# BSBR v2 — Beat Saber Brasil Ranking

Ranking brasileiro de Beat Saber com **PP multi-componente** (acc / tech / speed),
**batch semanal de ranqueamento com reweight**, FastAPI + Redis + Postgres e front-end Next.js.

Plano completo: [`Plan.md`](./Plan.md). Referências legadas: `references/bsbr/`, `references/BSStarAnalyzer/`.

## Como funciona

1. **Análise de mapas** (`backend/bsbr_analyzer`): baixa o mapa do BeatSaver, faz parse V2/V3/V4,
   extrai ~50 features e prediz `totalStars` decomposto em **acc/tech/speed** (sempre somando o total).
2. **PP por score**: curva exata do legado (`stars × 42.117208413 × curva(acc)`, golden-tested 1:1)
   decomposta em sub-PPs — mapa tech recompensa quem domina tech em accuracy alta.
3. **Batch semanal** (Celery beat): sync ScoreSaber → reweight (mediana de acc observada vs
   `max(0.78, 0.98 − 0.015·stars)`, delta clamp ±2★) → auto-aplica confiança alta |Δ|≤1★,
   resto vai pra fila staff → ranking + snapshot → playlist → webhook Discord.
4. **Qualificação**: staff analisa mapa novo (`POST /admin/maps/qualify`), revisa predições,
   aprova com os leaderboard ids → entra no pool rankeado com auditoria em `rating_history`.

## Stack

| Camada | Tech |
|---|---|
| Backend | FastAPI · SQLAlchemy 2 async · Alembic · Celery |
| Dados | PostgreSQL 16 (dev local: SQLite) · Redis 7 (cache/fila/rate-limit) |
| Analyzer | `bsbr_analyzer` (parser V2/V3/V4 + features + sub-stars heurísticos) |
| Front-end | Next.js (App Router) · TypeScript · Tailwind |

## API (`http://localhost:8000/api/v1`, OpenAPI em `/docs`)

```
GET  /health
GET  /rankings?component=total|acc|tech|speed&page=&country=
GET  /players/{ss_id}              · perfil, medalhas, evolução semanal
GET  /players/{ss_id}/scores
GET  /maps?sort=stars|recent|name  · GET /maps/{hash} (leaderboard + histórico de rating)
POST /calc                         · {stars, accuracy, shares?} → PP decomposto
POST /calc/gain                    · quanto de PP raw falta para +1pp ponderado
GET  /playlists/ranked.bplist
# Admin (header X-Admin-Token; OAuth Discord planejado):
POST /admin/maps/qualify           · POST /admin/maps/{id}/approve
GET  /admin/reweight/suggestions   · POST /admin/reweight/{id}/apply|reject
POST /admin/reweight/collect       · POST /admin/batch/run
```

## Desenvolvimento local (sem Docker)

```bash
.venv/Scripts/pip install -r backend/requirements.txt

# API (SQLite + cache em memória — zero serviços externos)
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# Analisar um mapa real do BeatSaver
cd backend && ../.venv/Scripts/python -m bsbr_analyzer <map_id_ou_hash>

# Testes (1319+)
cd backend && ../.venv/Scripts/python -m pytest -q

# Front-end
cd frontend && npm install && npm run dev   # http://localhost:3000
```

## Docker (stack completa)

```bash
cp .env.example .env
docker compose up --build
# api :8000 · web :3000 · postgres :5432 · redis :6379 (api/worker/beat)
```

## Migrações

```bash
cd backend && alembic upgrade head
```

## Garantias de correção

- **Golden tests** travam a curva de PP contra o módulo legado original (~840 casos, ±1e-9).
- Σ sub-PP == PP total em qualquer accuracy; Σ sub-stars == total stars (testado).
- Reweight com auditoria completa (`rating_history` antes→depois, nunca mutação silenciosa).
