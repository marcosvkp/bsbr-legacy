# BSBR Frontend

Interface web do ranking brasileiro de Beat Saber: **Next.js 16 (App Router) +
React 19 + TypeScript + Tailwind CSS 4**. Roda em [bsbr.pro](https://bsbr.pro) e
consome a API do [`backend/`](../backend/).

## Páginas

| Rota | Página | Descrição |
|---|---|---|
| `/` | Home | Visão geral do site, CTA para o ranking |
| `/ranking` | Ranking | Classificação BR por componente (total/acc/tech/speed), paginada e por país |
| `/jogadores` · `/jogadores/[ss_id]` | Jogadores | Lista + perfil (medalhas, evolução semanal, scores) |
| `/mapas` · `/mapas/[hash]` | Mapas | Catálogo com busca, slider de estrelas e aba comunidade; detalhe com histórico de rating |
| `/stars-ranking` | Estrelas | Distribuição/ranking por faixa de estrelas |
| `/ao-vivo` | Ao vivo | Scorefeed de scores recém-jogados (ScoreSaber + BeatLeader) |
| `/sobre` | Sobre | Wiki do BSBR: como funciona, curva de PP, critérios, Discord |
| `/admin` | Admin | Painel da staff em abas (ver abaixo) |

### Admin (abas)

- **Qualificação** — analisar mapa com ML, revisar predições, aprovar/recusar, rankear dificuldades.
- **Sugestões** — cards paginados das sugestões da comunidade (cover, mapper, BPM, quem sugeriu), Aprovar/Recusar.
- **Reweight** — coletar sugestões, prévia (simulação), aplicar/recusar.
- **Batch** — executar o batch semanal e ver o histórico.
- **Webhooks** — gerenciar URLs de webhook do Discord.

O acesso usa o header `X-Admin-Token` (guardado em `sessionStorage`) ou OAuth Discord.

## Estrutura

```
src/
├── app/                 # App Router
│   ├── layout.tsx       # Header global (SiteNav + UserMenu)
│   ├── page.tsx         # Home
│   ├── admin/page.tsx   # Painel (abas via ?tab=)
│   ├── ao-vivo/ · ranking/ · sobre/ · stars-ranking/
│   ├── jogadores/       # lista + [ss_id]
│   └── mapas/           # lista + [hash]
├── components/
│   ├── site-nav.tsx     # Navegação do site
│   ├── user-menu.tsx    # Login/logout Steam + menu do usuário
│   ├── suggest-map.tsx  # Modal "Sugerir mapa" (máx. 3 ativas)
│   ├── player-avatar.tsx
│   ├── pagination.tsx   # Paginação reutilizável
│   ├── smart-img.tsx    # Imagem com fallback/erro
│   ├── playlist-download.tsx · pp-meta.ts · sub-stats.tsx · empty-state.tsx
│   └── ui/              # Badge, Card, etc.
└── lib/
    ├── api.ts           # getJson/postJson/patchJson/deleteJson (AbortController 10s)
    ├── types.ts         # Tipos compartilhados com a API
    └── format.ts        # Datas, números, PP
```

## Como a API é chamada

`lib/api.ts` resolve a base da API por contexto:

- **Server (RSC)** → `API_INTERNAL_URL` em runtime (no compose: `http://api:8000/api/v1`).
  Vars sem `NEXT_PUBLIC_` **não** são embutidas no bundle.
- **Browser** → `NEXT_PUBLIC_API_URL` embutida no build (ex.: `http://localhost:8000/api/v1`).

O fetch envia `credentials: "include"` (cookies `bsbr_user_session` / sessão do admin)
e tem timeout de 10s via `AbortController` (o POST de sugestão aceita timeout maior,
pois o BeatSaver pode demorar).

## Desenvolvimento

```bash
npm install
npm run dev        # http://localhost:3000
npm run build      # gate do CI (Next 16 + Turbopack)
npm run start      # serve o build
npm run lint       # eslint (CI desliga o lint: 9 erros pré-existentes documentados no workflow)
```

### Env vars

| Var | Contexto | Descrição |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Build/browser | Base pública da API (default `http://localhost:8000/api/v1`) |
| `API_INTERNAL_URL` | Runtime/server | Base interna (default `http://api:8000/api/v1` — rede do compose) |

> ⚠️ O frontend é uma **imagem de build** no compose: mudar `NEXT_PUBLIC_API_URL`
> exige `docker compose up --build` (sem hot reload no container).

## Deploy

O CI (`.github/workflows/ci.yml`) roda `npm ci` + `npm run build` como gate em todo
push para `master`. Na VPS, o frontend roda como container `web` do compose atrás do
nginx (HTTPS via Let's Encrypt), com `API_INTERNAL_URL=http://api:8000/api/v1`.
