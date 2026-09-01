# BSBR Leaderboard — plugin in-game

Plugin **BSIPA** (C#, .NET Framework 4.8) que adiciona o **leaderboard do BSBR
dentro do Beat Saber**: um painel acima do HIGHSCORES com o **top 10 do ranking
brasileiro** por mapa, logo e células customizadas.

Site: [bsbr.pro](https://bsbr.pro) · Backend: [`../backend/`](../backend/) · CI não
cobre o plugin (build via BSMT local).

## Funcionalidades

- **Leaderboard do BSBR in-game** — substitui o placar padrão do mapa (via
  `LeaderboardCore`) com o ranking brasileiro do mapa tocado.
- **Top 10 paginado** — busca `limit=10` + `offset` (páginas "Anterior/Próxima").
- **Jogador local destacado** — o plugin envia o Steam ID (`ss_id`) de quem joga e
  a sua linha é destacada no placar.
- **Células customizadas** (`bsbr-list`) — células com o logo do BSBR e dados do
  mapa (estrelas total/acc/tech/speed quando disponíveis).
- **View de info do mapa** — detalhes extras na tela do mapa.
- **Config por jogador** — ligar/desligar e trocar a URL da API sem recompilar.

## Compatibilidade

| Versão | Notas |
|---|---|
| Beat Saber | **1.29.1 – 1.40.8** (multi-build; instância legada 1.29.1 = "V129" Mono) |
| BSIPA | ^4.2.2 |
| BeatSaberMarkupLanguage | ^1.6.10 |
| SiraUtil | ^3.1.2 |
| LeaderboardCore | ^1.3.3 |

`loadAfter: ["ScoreSaber", "BeatLeader"]` — funciona ao lado dos outros
leaderboards sem conflito de painel.

## Como funciona

O plugin intercepta o leaderboard do mapa atual e chama a API pública do BSBR:

```
GET {apiBaseUrl}/leaderboard/{songHash}
    ?difficulty={difficulty}
    &characteristic={characteristic}
    &limit=10&offset={pagina}
    &player_id={steamID64}     # opcional — destaca o jogador local
```

Resposta: posição, nome, país, acc/PP e a posição do próprio jogador (`has_more`
habilita a paginação). O `player_id` é o Steam ID obtido do `IPlatformUserModel`
(no V129 a chamada é sem `CancellationToken` — diferença tratada por compilação
condicional `#if V129`).

## Estrutura

```
src/
├── Plugin.cs              # Ponto de entrada BSIPA (Zenject installers)
├── Core/
│   ├── AppInstaller.cs    # Bindings de App (HTTP, config)
│   ├── MainInstaller.cs   # Bindings de Menu (leaderboard)
│   └── BSBRConfig.cs      # Config em UserData/BSBRLeaderboard.json
├── Features/Leaderboards/
│   ├── Domain/BSBRBeatmapKey.cs
│   ├── Services/BSBRLeaderboardService.cs   # HTTP + parse do placar
│   ├── Adapters/          # ViewControllers + BSML (placar, célula, info)
│   └── Addons/            # Células e tags customizadas (bsbr-list)
└── Resources/BSBRLogo.png # Logo embutido (recurso de assembly)
```

## Config

`UserData/BSBRLeaderboard.json`:

```json
{
  "enabled": true,
  "apiBaseUrl": "https://bsbr.pro/api/v1"
}
```

`apiBaseUrl` aponta para a API do BSBR — em produção o default já é
`https://bsbr.pro/api/v1`.

## Build

Requisitos: .NET SDK com suporte a `net48`, instância do Beat Saber com o jogo
instalado (para os assemblies `Managed/`), e as dependências no jogo
(BSIPA, BSML, SiraUtil, LeaderboardCore).

```bash
# Compila com a instância default (Directory.Build.props → 1.39.1)
dotnet build plugin/BSBRLeaderboard.csproj -c Release

# Ou aponte para outra instância / a 1.29.1 (V129)
dotnet build plugin/BSBRLeaderboard.csproj -c Release -p:BeatSaberDir="C:\caminho\Beat Saber"

# Build da 1.29.1 (Mono) exige o símbolo V129
dotnet build plugin/BSBRLeaderboard.csproj -c Release -p:BeatSaberDir="...\29.1 Multi" -p:DefineConstants=V129
```

Override de `BeatSaberDir` local (sem versionar): `Directory.Build.local.props`.
O `csproj` usa `BepInEx.AssemblyPublicizer.MSBuild` para publicizar `Main.dll`
e `BeatSaberModdingTools.Tasks` para instalar o build no jogo.

## Instalação do build

Depois de buildar com `BeatSaberDir` apontado para a instância, o BSMT copia o
plugin e o ícone para `Plugins/`. Se você só tem o `.dll`, coloque em
`Beat Saber/Plugins/BSBRLeaderboard.dll` com a pasta `Resources` correspondente
(o logo é carregado por recurso de assembly — não remova a `BSBRLogo.png`).
