# BSBR v2 — Arquitetura

> Ranking brasileiro de Beat Saber com **PP multi-componente** (acc / tech / speed),
> **batch semanal de ranqueamento com reweight**, **placares ao vivo** e
> **plugin in-game** — em [bsbr.pro](https://bsbr.pro).
>
> Este documento descreve o que o sistema faz, como cada peça funciona, e os
> invariantes que não podem ser quebrados. Fonte da verdade do design:
> [`Plan.md`](../Plan.md).

---

## 1. Visão geral

**Stack:**

| Camada | Tech |
|---|---|
| Backend | FastAPI · SQLAlchemy 2 async · Alembic · Celery |
| Dados | PostgreSQL 16 (dev local: SQLite) · Redis 7 (cache / rate-limit / scorefeed) |
| ML | `bsbr_analyzer` (parser V2/V3/V4 + ~50 features + `HistGradientBoostingRegressor`) |
| Front-end | Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 |
| Plugin | C# · BSIPA · LeaderboardCore · BSML · SiraUtil |

**Estrutura do repositório:**

```
.
├── backend/    # FastAPI + SQLAlchemy 2 async + Alembic + Celery + bsbr_analyzer (ML)
├── frontend/   # Next.js 16 (App Router) · TypeScript · Tailwind
├── plugin/     # Plugin in-game BSIPA (C# / .NET Framework 4.8) — leaderboard do BSBR
├── references/ # Legado (bsbr, BSStarAnalyzer) e materiais de estudo
├── Plan.md     # Plano de recriação completo (design, dados, roadmap)
└── .github/    # CI: pytest (backend) + build (frontend)
```

**O que o BSBR faz:**

| | |
|---|---|
| **Ranking BR** | Ranqueia jogadores brasileiros com PP próprio (acc/tech/speed), curva herdada do legado e golden-tested 1:1 |
| **Análise de mapas com ML** | `bsbr_analyzer` baixa o mapa do BeatSaver, faz parse V2/V3/V4 e prediz estrelas decompostas em acc/tech/speed |
| **Batch semanal** | Celery beat: sync ScoreSaber → reweight (mediana de acc observada vs. expected) → auto-aplica ou fila staff → ranking + snapshot → playlist → webhook Discord |
| **Scores ao vivo** | Scorefeed via WebSocket (ScoreSaber + BeatLeader) persistido e exposto em `/ao-vivo` |
| **Comunidade** | Login com **OAuth Steam** (steamID64 = identidade ScoreSaber) + **sugestões de mapas** (máx. 3 ativas) |
| **Plugin in-game** | Leaderboard do BSBR dentro do Beat Saber (BSIPA), top 10 por mapa com logo e células customizadas |

---

## 2. O coração do domínio: PP multi-componente

O BSBR não é um wrapper do ScoreSaber — ele tem **rating próprio** decomposto em 3 eixos. Tudo gira em torno disso.

### 2.1 Sub-stars (decomposição do total)

`backend/bsbr_analyzer/substars.py:127` — `totalStars = accStars + techStars + speedStars` (invariante: a soma sempre fecha).

Cada eixo é um score bruto das features do analyzer, normalizado em **shares** (`share_acc + share_tech + share_speed = 1`), então `subStars_x = totalStars × share_x`. Knobs de calibração em `substars.py:46-75`:

- **tech** ← `pat_tech_ratio`, parity breaks, crossovers, `pat_pattern_complexity`
- **speed** ← `peak_nps`, `nps`, `effective_nps`, `stream_ratio`, bursts/doubles
- **acc** ← `vision_block_ratio`, stacks, bombas/s, paredes/s, `peak_strain`

Features de magnitude larga passam por `log1p` (`_LOG_SCALED`) para nenhum eixo dominar só por escala. `AXIS_WEIGHTS["tech"] = 1.5` compensa features discriminativas de magnitude menor.

### 2.2 Curva de PP (porte exato do legado)

`backend/app/services/pp_engine/curve.py:29` — 36 pontos piecewise-linear. `STAR_MULTIPLIER = 42.117208413`. Em `acc = 0.95` o multiplicador é exatamente `1.0` (ponto de calibração); cresce explosivo perto de 1.00 (até `5.3674`). **Golden tests** travam isso contra o legado (~840 casos, ±1e-9).

### 2.3 PP do score + decomposição

`backend/app/services/pp_engine/pp.py:43` — `decompose_pp`:

```
totalPP = totalStars × 42.117208413 × curveBSBR(acc)   # IDÊNTICO ao legado
g_acc(acc)   = curveBSBR(acc) / curveBSBR(0.95)        # herda comportamento BSBR
g_tech(acc)  = exp(1.9 × (acc − 0.95))                 # tech explode com acc alta
g_speed(acc) = exp(1.2 × (acc − 0.95))                 # speed menos sensível
subPP_x = totalPP × share_x × g_x(acc) / Σ(w)          # normalização → Σ subPP = totalPP
```

Propriedades:
- Em `acc = 0.95` (ponto de calibração) os sub-PPs saem exatamente proporcionais aos sub-stars.
- Acc altíssima num mapa tech desloca PP para `techPP`.
- O ranking **geral** usa `totalPP` (curva legado intacta); os rankings **por componente** usam os sub-PPs.

### 2.4 Agregação do jogador

`backend/app/services/pp_engine/aggregate.py:15` — `weighted_pp(pps) = Σ ppᵢ × 0.965ⁱ` (scores ordenados desc). Componentes agregam na **mesma ordem** (por `pp_total` desc), então `pp_acc + pp_tech + pp_speed == pp_total`.

`backend/app/services/ranking.py:33` — `recompute_all_rankings` recalcula PP agregado e rank de todos os players; `recompute_player` (linha 58) faz só um jogador (score ao vivo). Rank = posição por `pp_total` desc.

### 2.5 Calculadora "+1pp"

`backend/app/services/pp_engine/calculator.py:33` — busca binária pela fronteira de inserção: quanto PP cru um novo score precisa para adicionar `expected_pp` ao PP ponderado, dado os PPs atuais. Porte 1:1 do legado. Exposto em `POST /calc/gain`.

---

## 3. Pipeline semanal (o coração operacional)

`backend/app/core/tasks_app.py:21` — Celery beat com 2 schedules:

- **`batch.weekly`** — segunda 03:00 UTC
- **`sync.br_daily`** — 06:15 e 18:15 UTC (complemento do scorefeed)

`backend/app/workers/tasks.py:19` — `run_weekly_batch` orquestra:

1. **Sync** (`services/sync/__init__.py:409`) — para cada dificuldade rankeada, busca scores do ScoreSaber (por `ss_leaderboard_id`) e BeatLeader (por `bl_leaderboard_id`), faz upsert de players e scores, calculando PP na ingestão via `decompose_pp`. **1 score por (player, difficulty)** — o mais recente substitui o anterior (dedup no sync, não na constraint do banco; ver `sync/__init__.py:247`). Conflito SS × BL: fica o de maior PP do BSBR.
2. **Reweight** (`services/reweight/service.py:201`) — `collect_suggestions` avalia cada dificuldade rankeada:
   - `algorithm.py:56` — acc mediana observada vs `expected(stars) = max(0.78, 0.98 − 0.015·stars)`; `delta = clamp(±2★, −(mediana − esperada) × 100 × 0.25)`.
   - `service.py:61` — `analyze_difficulty_with_ml`: **delta = ½ ML + ½ performance** (desde 5988383). ML re-prediz stars do beatmap; performance mede acc observada vs esperada.
   - Confiança: `n≥100` high, `n≥40` medium, senão low; `n<6` sem sugestão (limiares BR reescalados).
   - **Auto-aplicar** apenas `confidence=high` e `|delta| ≤ 1★`; resto vai para fila staff.
3. **Ranking** — `recompute_all_rankings` + `write_weekly_snapshot` (idempotente por semana).
4. **Playlist** `.bplist` + **webhook Discord** (`integrations/discord.py`) — relatório "Monthly Reweight" com antes→depois de cada mapa.

Tudo vira linha em `rating_history` (auditoria completa, nunca mutação silenciosa). Em caso de erro, o batch é marcado `failed` com `finished_at` (`tasks.py:101`).

---

## 4. Scorefeed ao vivo (WebSocket)

Duas fontes WebSocket consumidas em paralelo:

- ScoreSaber: `wss://scoresaber.com/ws`
- BeatLeader: `wss://sockets.api.beatleader.com/scores` (habilitado desde 2026-08-29)

**Fluxo:** `services/live/listener.py:28` (loop com reconexão backoff 1s→60s) → `messages.py:232` (parser normaliza ambos formatos em `LiveScore`) → `bus.py:38` (`publish`) → `persist.py:44` (upsert) → `ranking.recompute_player` (recalc na hora) → Redis (ZSET `bsbr:live:recents` 2h + pub/sub `bsbr:live`).

**Filtro:** só jogadas de players BR em dificuldades rankeadas (`persist.py:51`). Players do BeatLeader passam pelo resolver (`beatleader_resolve.py:77`): `bl_id → ss_id` (Steam ID direto na maioria; fallback via API/socials/busca por nome).

**Endpoint:** `api/v1/endpoints/live.py:23` — WS `/api/v1/ws/live` (envia últimos 20 + pub/sub) e `GET /live/recent`. Frontend `frontend/src/app/ao-vivo/live-feed.tsx:26` conecta com reconexão exponencial.

---

## 5. ML — `bsbr_analyzer`

Motor de análise de mapas (porte de `references/BSStarAnalyzer`).

### 5.1 Pipeline de análise

`analysis.py:241` — `analyze_map(source)` baixa zip do BeatSaver → extrai → lê `Info.dat` (V2/V3/V4/V4.0.1) → para cada dificuldade Standard: features físicas + padrões + heurística/modelo + sub-stars + estilo.

### 5.2 Parser

`parser/beatmap.py:28` — detecta versão, parse V2 (`_notes`), V3 (`colorNotes`), V4.1 (`colorNotes`/`colorNotesData` com deltas parciais em arrays paralelos — formato Beat Saber 1.40+).

### 5.3 Features físicas

`features.py:95` — NPS, peak NPS (janela deslizante 1s), strain curve (decay exponencial 2.0/s), complexity, angle_strain, vision_block_ratio, alternation, etc. — ~19 features. Preserva EXATAMENTE as janelas e decaimentos da referência.

### 5.4 Features de padrão (`pat_*`)

`patterns.py` — ~35 features com limiares idênticos à referência:

- **Streams** (`beat_diff ≤ 0.27`, min length 5), **jumps**, **crossovers**, **doubles** (`beat_diff ≤ 0.13`), **stacks**, **parity breaks** (via `NATURAL_FLOW`), **resets**, **arcs/chains** (V3), **hand dominance**.
- **Vision blocks** avançado, **obstacle/bomb density**, **pattern_complexity** agregada.
- `classify_map_style` → tags `stream/tech/jump/crossover/speed/obstacle/balanced`.

### 5.5 Modelo

`trainer.py:99` — `HistGradientBoostingRegressor` (1000 iter, early stopping, 5-fold CV) sobre ~49 features. Salvo em `models/star_rating_model.pkl`. `predict_with_fallback` (`trainer.py:231`) usa modelo se disponível, senão `heuristic_stars` (`stars_heuristic.py`). Dataset real: 500 amostras/256 músicas, MAE CV 0.54★, R² 0.91.

### 5.6 Builder de dataset

`dataset.py` — coleta dificuldades rankeadas do ScoreSaber (target = stars oficiais) com cache incremental, baixa mapa do BeatSaver, analisa, acumula em `data/dataset.csv` com checkpoint a cada 50 músicas. Retomável. CLI: `python -m bsbr_analyzer download | train | dataset-info`.

---

## 6. Backend — API e infra

### 6.1 Models (`backend/app/models/`)

| Model | Chave | Observação |
|---|---|---|
| `Player` | `ss_id` (Steam ID), `bl_id` | `pp_total/acc/tech/speed`, `rank`, `country` |
| `Score` | `(player_id, difficulty_id, time_set)` único | `pp`, `pp_acc/tech/speed`, `ss_player_pp`, `leaderboard_rank` |
| `Map` | `hash`, `beatsaver_id` | `status` (candidate/qualified/ranked/removed) |
| `Difficulty` | `(map_id, characteristic, name)` único | `total_stars/acc/tech/speed`, `ss_leaderboard_id`, `bl_leaderboard_id`, `is_ranked` |
| `RatingHistory` | auditoria antes→depois de cada reweight | `batch_id`, `applied_by`, `reason` |
| `Batch` | `kind` (weekly/manual), `started_at/finished_at`, `stats` JSON | |
| `RankSnapshot` | `(week, player_id)` único | snapshot semanal idempotente |
| `ReweightSuggestion` | fila de reweight pendente | `delta_stars`, `confidence`, `suggested_stars` |
| `MapSuggestion` | sugestão de mapa por jogador | máx 3 pending por jogador |
| `WebhookConfig` | webhooks Discord configuráveis pelo admin | |
| `StaffUser` | staff Discord | id, name, avatar, guild |

Enums (`enums.py:48`): `native_enum=False` → VARCHAR + CHECK portável (SQLite e PG idênticos).

### 6.2 DB / Cache / Rate-limit

- `core/db.py:47` — `task_session_factory`: **engine isolado por event loop** nas tasks Celery (resolve "attached to a different loop" com asyncpg/Postgres). `get_db` (linha 82) cria sessionmaker no loop do request para testes.
- `core/cache.py:18` — Redis quando `REDIS_URL` definido, senão memória de processo (dev). `_ensure_redis` recria cliente se o loop mudou.
- `core/ratelimit.py:15` — `SlidingWindowLimiter`: Redis ZSET de timestamps (limite vale para API + workers + beat juntos) ou `deque` em memória. `acquire` bloqueia até vaga abrir (sleep); sem o sleep, excesso vira busy-loop e pendura o request. ScoreSaber: 350 req/min (legado).

### 6.3 Sessões (cookie HMAC)

- `core/user_session.py` — cookie `bsbr_user_session`, TTL 30 dias, payload `ss_id.expiry.sig` onde `sig = HMAC-SHA256(session_secret, "ss_id:expiry")`. `verify_cookie` usa `hmac.compare_digest` (constante-temporal).
- `api/v1/endpoints/oauth.py` — cookie admin `bsbr_admin_session`, TTL 12h, mesma técnica. `admin_session_ok` é a primeira via de `require_admin` (antes do `X-Admin-Token`).
- **Dois cookies independentes** — fluxos admin (Discord) e jogador (Steam) separados.

### 6.4 Integrações externas

`integrations/scoresaber.py` — `ScoreSaberClient` (httpx async + rate limit + retry em `{429, 500, 502, 503}`). Endpoints: `/players?countries=BR`, `/player/{id}/full`, `/player/{id}/scores`, `/leaderboard/by-id/{id}/scores`, `/leaderboard/by-id/{id}/info` (maxScore/stars).

`integrations/beatleader.py` — `BeatLeaderClient` (mesmo padrão). Endpoints: `/player/{id}` (socials, linkedIds), `/players?search=`, `/leaderboards/hash/{hash}`, `/leaderboard/scores/{id}`. `extract_ss_id_from_socials` — fallback do resolver (fonte primária é Steam ID direto).

`integrations/discord.py` — webhook reweight. Múltiplos URLs via `webhook_configs` (tabela) ou `DISCORD_WEBHOOK_URL` (env, vírgula-separado). Embed "Monthly Reweight" com antes→depois.

### 6.5 Endpoints (`/api/v1`)

```
# Público
GET  /health
GET  /rankings?component=total|acc|tech|speed&page=&country=
GET  /players/{ss_id}              · perfil, medalhas, evolução semanal
GET  /players/{ss_id}/scores
GET  /players/{ss_id}/pp-history   · progressão de PP por timestamp dos scores
GET  /maps?sort=stars|recent|name&q=&min_stars=
GET  /maps/{hash}                  · detalhe + leaderboard + histórico de rating
GET  /leaderboard/{hash}           · placar do mapa (usado pelo plugin in-game)
GET  /stars-bands                  · distribuição por faixa de estrelas
GET  /live/recent                  · scores recentes ao vivo
WS   /ws/live                      · stream em tempo real
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

---

## 7. Frontend (Next.js 16)

SSR (RSC) consumindo a API real. `lib/api.ts:7` — `API_INTERNAL_URL` (server, dentro do compose `http://api:8000/api/v1`) vs `NEXT_PUBLIC_API_URL` (browser, embutida no bundle). `credentials: "include"` para cookies de sessão.

**Páginas:**

- `/` — home com status da API, top 5 jogadores, mapas recentes
- `/ranking` — tabs Geral/Acc/Tech/Speed, medalhas top 3, busca por nome
- `/jogadores/[ss_id]` — header com avatar + 4 stat blocks, radar (componentes vs líderes), evolução semanal, **progressão de PP** por timestamp dos scores, tabela de scores com covers e ponderação, calculadora +1pp
- `/mapas` — catálogo com busca + slider de estrelas, cards com capa/overlay
- `/mapas/[hash]` — detalhe com seletor de dificuldade (mais alta primeiro), leaderboard, histórico de rating
- `/ao-vivo` — feed WS em tempo real
- `/stars-ranking` — ranking por faixa de estrelas
- `/sobre` — wiki + curva + Discord oficial
- `/admin` — abas: Qualificação, Sugestões de mapas, Reweight, Batch, Webhooks

UI "Saber Arcade": fontes Tektur/IBM Plex Sans, glow dos sabres, grade de ritmo, entrada em cascata. Validação: `next build` é o gate (dev tolera erros TS).

---

## 8. Plugin in-game (C#)

`plugin/` — BSIPA net48, leaderboard do BSBR dentro do Beat Saber. Multi-versão 1.29.1–1.40.8 (define `V129` para `IPlatformUserModel.GetUserInfo()` sem CancellationToken).

- `Plugin.cs:20` — Zenjector instala `AppInstaller` (App) + `MainInstaller` (Menu).
- `LeaderboardFeatureInstaller.cs:10` — binda `BSBRLeaderboardService`, `BSBRLeaderboardViewController`, `BSBRListAdder` (tag BSML customizado `bsbr-list`), `BSBRCustomLeaderboard` (adapter para `CustomLeaderboardManager`). `BindInterfacesAndSelfTo` + `NonLazy` são obrigatórios para `IInitializable` disparar.
- `BSBRLeaderboardService.cs:82` — `GET /leaderboard/{hash}?difficulty=...&characteristic=...&limit=10&offset=...&player_id=...` (top 10 paginado, destaca o próprio jogador). Usa `IGPlatformUserModel` para pegar o Steam ID local.
- `BSBRCustomLeaderboard.cs` — registra a tab "BSBR" no `LeaderboardCore`. `#if V129` para assinaturas 1.29.1 (Mono) vs 1.34+ (fork NSGolova). Painel acima do HIGHSCORES com logo BSBR, células customizadas (`bsbr-list`, port do AccSaber).
- `BSBRConfig.cs` — `UserData/BSBRLeaderboard.json` com `enabled` e `apiBaseUrl` (default `https://bsbr.pro/api/v1`).

---

## 9. Auth / comunidade

- **OAuth Steam** (`auth.py:55`) — OpenID 2.0. `steamID64` = `Player.ss_id` (identidade unificada). Cookie `bsbr_user_session` HMAC-assinado.
- **Sugestões de mapas** (`services/suggestions.py`) — jogadores logados sugerem (máx 3 pending, sem ML — só metadata BeatSaver). Rate-limit 10/hora por IP. Aprovação cria `Map` candidate.
- **Admin** — OAuth Discord (cookie `bsbr_admin_session`, guild check) ou `X-Admin-Token` fallback.

---

## 10. Deploy / ops

- **Local Docker:** `docker compose up --build` — 6 serviços (postgres, redis, api, worker, beat, live, web). Host local usa `API_PORT=18000`, `POSTGRES_PORT=15432`, `REDIS_PORT=16379` (SliceWeb ocupa as padrão).
- **Produção:** VPS `bsbr.pro` (187.45.188.156, user `deploy`, sem sudo). **Sem git** — deploy por sync de arquivos (tar+SFTP). SliceWeb na 8080; nginx 80/443 com certbot container. 502 pós-recreate → restart `bsbr_pro_nginx`.
- **CI:** GitHub Actions — pytest contra Postgres-independente + Redis real de serviço; `next build` (gate do Next 16).
- **Migrações:** Alembic (`backend/alembic/versions/`). Dev SQLite e prod Postgres.

---

## 11. Mapa de dependências (como tudo se conecta)

```
BeatSaver ──download──> bsbr_analyzer ──features──> substars ──shares──> pp_engine.decompose_pp
                                                                    │
ScoreSaber ──sync──> Score (pp, pp_acc/tech/speed) ─────────────────┤
BeatLeader ──resolve──> Player (ss_id) ──upsert──> Score ───────────┤
                                                                     ▼
WS live ──publish──> Redis bus ──persist──> Score ──> ranking.recompute_player
                                                                     │
Celery beat ──batch.weekly──> sync ──> reweight (ML + perf) ──> RatingHistory
                              ──> ranking.recompute_all ──> RankSnapshot ──> playlist ──> Discord webhook
                                                                     │
FastAPI ──/rankings, /players, /maps, /leaderboard ──> Next.js SSR ──> browser
       ──/ws/live ──> WebSocket ──> LiveFeed (React)
       ──/auth/steam ──> cookie bsbr_user_session ──> /suggestions
       ──/admin (OAuth Discord) ──> qualify/approve/reweight/batch

Plugin (C# in-game) ──GET /leaderboard/{hash}──> BSBRLeaderboardService ──> BSML cells
```

---

## 12. Invariantes do sistema (o que NÃO pode quebrar)

1. **Σ sub-stars == total_stars** — `substars.compute_substars` normaliza shares (soma 1.0).
2. **Σ sub-PP == total-PP** — `pp.decompose_pp` normaliza pesos; `aggregate.aggregate_components` usa a mesma ordem.
3. **Curva de PP == legado** — golden tests ~840 casos ±1e-9 contra `references/bsbr/app/scorecalc`.
4. **1 score por (player, difficulty)** — dedup no sync/live (upsert + delete dos anteriores), não na constraint do banco (testes de reweight precisam de múltiplos).
5. **Auditoria completa** — todo reweight vira `RatingHistory` (antes→depois); nunca mutação silenciosa.
6. **Loop-isolamento** — engine DB e Redis criados por event loop nas tasks Celery (`task_session_factory`, `cache._ensure_redis`); senão "attached to a different loop" na 2ª execução.
7. **Idempotência do snapshot** — `write_weekly_snapshot` deleta e reescreve a semana; `(week, player_id)` único.
8. **Reweight: delta = ½ ML + ½ perf** desde 5988383 (antes era só performance).
9. **Auto-aplicar só high + |delta| ≤ 1★** — resto vai para fila staff.
10. **PP interno do BSBR** — colocação no leaderboard do mapa é por `Score.pp`, nunca rank global do ScoreSaber.

---

## 13. Pontos críticos / gotchas

1. **Loop-isolamento async** — o problema mais sutil. Redis e engine do banco são criados por event loop nas tasks Celery, senão "Event loop is closed" / "attached to a different loop" na 2ª execução. Repro só com asyncpg/Postgres (não aparece no Windows/SQLite).
2. **1 score por (player, difficulty)** — dedup no sync/live (upsert), **não** na constraint do banco. Testes de ranking/reweight dependem de múltiplos scores na mesma difficulty.
3. **PP interno do BSBR** — colocação no leaderboard do mapa é por `Score.pp` (local #1), nunca o rank global do ScoreSaber. Reweight usa `Player.pp_total` (payload do ScoreSaber não traz pp do player).
4. **max_score NULL zerava PP** — difficulty sem `max_score` → acc=None → pp=0. Sync auto-preenche via `/leaderboard/by-id/{id}/info`.
5. **`beatsaver_id` String(64)** — hash SHA1 de 40 chars estourava varchar(32).
6. **`/api/v2/maps/hash/{hash}`** do ScoreSaber — retorna leaderboards de qualquer status (search paginado com `ranked=true` não cobre mapas novos).
7. **BeatLeader resolver** — `bl_id == ss_id` para jogadores Steam (17 dígitos); fallback via `linkedIds.steamId` / socials / busca por nome+país.
8. **Validação frontend** — `next build` é o gate; dev tolera erros TS. Datas por fuso quebram hidratação em prod (`suppressHydrationWarning`).
9. **CLI backend** — ASCII puro (cp1252); console Windows crasha em `→ ★ ±`.
10. **Containers sem hot reload** — api sem `--reload` (restart), web é imagem build (`up --build`).
11. **Cache-Control OG dinâmico** — max-age 120s (cache de 1h segurava V1 após deploy da V2).
12. **Rate-limit ZSET persiste entre testes** — `SlidingWindowLimiter.reset` apaga ZSET para isolamento no CI com Redis real.

---

## 14. O que o projeto NÃO é

- Não é+ é um port do legado (`references/bsbr/`) — é rework total com arquitetura de verdade (API + workers + cache + banco relacional + frontend desacoplado). O legado era monólito Flet com cache em memória.
- Não usa PP do ScoreSaber/BeatLeader — recalcula tudo com a curva própria + sub-stars.
- Não tem speedRating explícito do BeatLeader — speed é heurística própria sobre features (peak_nps, stream_ratio, etc.).
- Não rankeia por país no banco — `country` é atributo do Player; ranking filtra por `?country=BR` na query.
- Não tem deploy via git na VPS — deploy por sync de arquivos (tar+SFTP), `bsbr.pro` não tem git.

---

## 15. Cobertura por camada

| Camada | Responsabilidade | Entrypoint |
|---|---|---|
| **bsbr_analyzer** | Parser V2/V3/V4 + features + padrões + ML + substars | `analyze_map(source)` |
| **pp_engine** | Curva legado + decomposição + agregação + calc +1pp | `decompose_pp`, `weighted_pp` |
| **sync** | ScoreSaber/BeatLeader → upsert Score (1 por player+diff) | `sync_all_ranked_difficulties` |
| **reweight** | ML + performance → delta → RatingHistory (auto/fila) | `collect_suggestions`, `apply_suggestion` |
| **ranking** | Recalc PP agregado + rank + snapshot semanal + medalhas | `recompute_all_rankings`, `recompute_player` |
| **live** | WS ScoreSaber+BeatLeader → persist → recompute → Redis pub/sub | `listener.run`, `bus.publish` |
| **qualification** | BeatSaver → analyze → candidato → approve → RANKED | `qualify_source`, `approve_map` |
| **beatleader_resolve** | bl_id → ss_id (Steam direto / socials / busca) | `resolve_bl_player` |
| **suggestions** | Jogadores sugerem mapas (máx 3, sem ML, rate-limit IP) | `create_map_from_suggestion` |
| **pp_history** | Série (ts, pp) com estimativas em gaps | `build_pp_history` |
| **playlist** | `.bplist` dos rankeados | `generate_bsbr_playlist` |
| **og_image** | OG 1200×630 para share social | `render(payload)` |
| **workers/tasks** | Celery beat: batch semanal + sync BR 2x/dia | `batch.weekly`, `sync.br_daily` |
| **integrations** | ScoreSaber/BeatLeader/Discord (httpx + rate limit + retry) | `ScoreSaberClient`, `BeatLeaderClient` |
| **plugin** | Leaderboard in-game (tab BSBR, top 10 paginado, células custom) | `BSBRCustomLeaderboard` |

---

## 16. Desenvolvimento local

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

### Docker (stack completa)

```bash
cp .env.example .env
docker compose up --build
# api :8000 · web :3000 · postgres :5432 · redis :6379
# (portas configuráveis via .env — o host local usa API_PORT=18000,
#  POSTGRES_PORT=15432 e REDIS_PORT=16379 quando as padrão estão ocupadas)
```

### Migrações

```bash
cd backend && alembic upgrade head   # dev SQLite e prod Postgres
```
