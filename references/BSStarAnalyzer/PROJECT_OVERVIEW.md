# BSStarAnalyzer — Visão Geral do Projeto

> Documento de contexto gerado para explicar **como o projeto funciona no geral**.
> Última atualização: 2026-08-08

---

## 1. O que é este projeto?

**BSStarAnalyzer** (Beat Saber Star Analyzer) é uma ferramenta em Python que **analisa mapas de Beat Saber** (arquivos de chart customizados) e **prediz a dificuldade de cada mapa em "stars" (★)** — o mesmo conceito de rating usado pelo ScoreSaber e BeatLeader.

Em resumo, o projeto:

1. **Baixa mapas** do BeatSaver (por hash ou ID);
2. **Interpreta os arquivos do mapa** (formato V2, V3 e V4 — `Info.dat` + arquivos de dificuldade `.dat`);
3. **Extrai dezenas de métricas** de gameplay: NPS, strain, streams, jumps, crossovers, tech, vision blocks, bombas, paredes, etc.;
4. **Treina um modelo de Machine Learning** (`HistGradientBoostingRegressor`) que aprende a prever o rating oficial de estrelas a partir dessas métricas;
5. **Valida/ajusta a predição** usando a performance real dos jogadores no ScoreSaber (accuracy, full combo, distribuição de scores).

O objetivo final é estimar a dificuldade de **mapas não rankeados** e auxiliar na **avaliação de mapas** (buff/nerf de rating) para comunidades/rankings (ex.: BSBR — Brazilian Beat Saber Ranking).

---

## 2. Arquitetura (visão geral)

```
┌──────────────┐    ┌───────────────┐    ┌─────────────────┐    ┌────────────────┐
│  Entradas    │───▶│  Parser       │───▶│  Feature        │───▶│  Modelo ML     │
│  (mapas,     │    │  (parser/)    │    │  Extraction     │    │  (trainer.py)  │
│  playlists,  │    │  V2/V3/V4     │    │  (analyzer.py + │    │  predição ★    │
│  hash/ID)    │    │               │    │   pattern_*)    │    │  + heurística  │
└──────────────┘    └───────────────┘    └─────────────────┘    └────────────────┘
                                                     │
┌─────────────────────────────────────────────────────┴──────────────────────┐
│  Validação/Ajuste por performance real (player_performance.py — API        │
│  ScoreSaber) → sugere delta de rating → rating_adjustments.json            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Fluxo de dados principal:**

```
BeatSaver (download) ─▶ pasta maps/*.zip ─▶ extracted_maps/<hash>/
                                                │
                                                ▼
                                    Info.dat + ExpertStandard.dat ...
                                                │
                                    parser/ (objetos Note, Obstacle)
                                                │
                                    analyzer.py + pattern_analyzer.py
                                                │  (≈ 50+ features por dificuldade)
                                                ▼
                                    dataset.csv  (features + stars reais do SS)
                                                │
                                    trainer.py ─▶ star_rating_model.pkl
                                                │
                                    predict_stars() / heuristic_stars()
                                                ▼
                                    Relatórios: CLI, GUI, playlist_analysis.json
```

---

## 3. Estrutura de arquivos

### Código-fonte (raiz)

| Arquivo | Papel |
|---|---|
| `main.py` | **CLI principal** — todos os comandos (`download`, `train`, `analyze`, `performance`, etc.) e integração com as APIs (ScoreSaber, BeatSaver) |
| `analyzer.py` | **Análise de estrutura do mapa** — lê o `Info.dat`, processa cada dificuldade, calcula métricas físicas (NPS, strain curve, complexity, etc.) e integra o `pattern_analyzer` |
| `pattern_analyzer.py` | **Detecção profunda de padrões** — streams, jumps, crossovers, doubles, stacks, parity breaks, tech ratio, hand dominance, obstacles, bombs, vision blocks, arcs/chains (V3); classifica o estilo do mapa |
| `trainer.py` | **Treinamento e predição do modelo ML** — features, heurística de fallback, avaliação por range/estilo, ajustes de rating persistidos |
| `player_performance.py` | **Análise de performance real** via ScoreSaber API — accuracy ponderada, mediana, distribuição, sugestão de delta de stars |
| `gui.py` | **Interface gráfica** (CustomTkinter) — abas Analyze / History / Train |
| `requirements.txt` | Dependências: `requests`, `pandas`, `scikit-learn`, `joblib`, `customtkinter`, `Pillow`, `packaging` |

### Pacote `parser/` (interpretação de mapas)

| Arquivo | Papel |
|---|---|
| `base.py` | Classe base `BeatmapObject` (tempo em beats `b`) |
| `objects.py` | Objetos tipados: `Note`, `Obstacle`, `Event` — normalizam V2 (`_time`, `_lineIndex`...) e V3 (`b`, `x`, `y`...) |
| `enums.py` | Enums: `NoteColor` (RED/BLUE/BOMB), `NoteCutDirection` (UP, DOWN, ... ANY), linhas/colunas da grid, `EventType` |
| `beatmap.py` | Classe `Beatmap` — detecta a versão (V2/V3) e popula listas de notes, bombs e obstacles |
| `loader.py` | Carregamento de `Info.dat`/`info.dat` e arquivos de dificuldade (legado/auxiliar) |

### Dados gerados / auxiliares

| Arquivo/Pasta | Conteúdo |
|---|---|
| `dataset.csv` | **Dataset de treino** — 1 linha por dificuldade rankeada com todas as features + `stars` reais do ScoreSaber + `map_styles` |
| `ranked_maps.json` | **Cache incremental** das entries rankeadas do ScoreSaber (nunca perde dados, cresce a cada execução) |
| `rating_adjustments.json` | Ajustes manuais/automáticos de rating por mapa+dificuldade |
| `analyzed_history.json` | Histórico salvo pela GUI |
| `playlist_analysis.json` | Resultado do comando `analyze-playlist` |
| `star_rating_model.pkl` | Modelo treinado (joblib) + lista de features (atualmente vazio — precisa `train`) |
| `2.csv` | Dataset antigo/experimental com o mesmo schema (referência) |
| `maps/` | Zips baixados do BeatSaver |
| `extracted_maps/<hash>/` | Mapas extraídos (`Info.dat`, `ExpertStandard.dat`, covers, etc.) |
| `analyze/` | Playlists `.bplist` (ex.: BSBR Ranked, Qualified) |
| `_rules/` | **Referências de APIs**: schemas JSON do BeatLeader, BeatSaver, ScoreSaber e um exemplo de mapa expert |

---

## 4. Módulos em detalhe

### 4.1 `parser/` — Entendendo o mapa

Um mapa de Beat Saber é um **zip** contendo:

- `Info.dat` — metadados: nome da música, BPM, e lista de dificuldades (Easy → ExpertPlus) por "characteristic" (Standard, Lawless, OneSaber...);
- `<Dificuldade>.dat` — o chart em si: notas (posição x/y na grid 4×3, cor, direção de corte, ângulo), bombas, obstáculos (paredes) e eventos de luz.

O parser **normaliza V2 e V3** para objetos unificados:
- `Note(b, x, y, c, d, a)` — `c` = cor (0 vermelho, 1 azul, 3 bomba), `d` = direção de corte, `a` = angle offset (V3);
- `Obstacle(b, x, y, d, w, h)` — parede com posição, duração e tamanho;
- `Event` — eventos de iluminação/rotação (atualmente não usado na análise).

O `analyzer.py` também suporta **V4** (`Info.dat` com `difficultyBeatmaps` / `audio.bpm`), além do V2 clássico.

### 4.2 `analyzer.py` — Métricas físicas

Para cada dificuldade (somente characteristic **Standard**), calcula:

| Métrica | O que mede |
|---|---|
| `nps`, `peak_nps`, `weighted_peak_sum` | Notas por segundo — média e picos (janela deslizante de 1s) |
| `effective_nps`, `peak_ratio` | NPS normalizado pelo BPM e razão pico/média |
| `complexity_score`, `angle_strain`, `tech_density` | Movimento total ponderado, tensão angular, densidade técnica |
| `stream_ratio`, `alternation_ratio`, `vision_block_ratio` | Métricas legadas de fluxo e notas no centro da tela |
| `peak_strain`, `strain_volatility` | **Strain curve** (curva de esforço com decaimento exponencial) — pico médio e variabilidade |
| `bomb_count`, `obstacle_count` | Quantidade de bombas e paredes |
| `map_styles` | Estilo(s) detectado(s) pelo classificador |

### 4.3 `pattern_analyzer.py` — Padrões de gameplay

É o coração da análise qualitativa. Detecta e quantifica:

- **Streams** — sequências rápidas de notas por mão (≥5 notas, intervalo ≤ 0.27 beats);
- **Jumps** — notas simultâneas nas duas mãos com grande distância na grid;
- **Crossovers** — mão esquerda em colunas ≥2 ou direita em colunas ≤1 (cruzar a linha central);
- **Doubles/Bursts** — pares de notas extremamente rápidos por mão (≤ 0.13 beats);
- **Stacks** — notas sobrepostas na mesma posição (difíceis de ler);
- **Parity breaks / Reset intensity** — quebras do fluxo natural de corte (UP→DOWN, etc.) que forçam reset de pulso;
- **Linear vs Tech** — proporção de diagonais/ângulos (tech) vs cortes lineares;
- **Hand dominance** — assimetria de trabalho entre as mãos;
- **Obstacles / Bombs** — densidade de paredes e bombas por segundo;
- **Vision blocks avançado** — notas centrais que bloqueiam a visão de notas seguintes;
- **Arcs / Chains (V3)** — sliders e burst sliders;
- **`pat_pattern_complexity`** — índice agregado que combina todas as métricas acima.

Cada métrica vira uma feature `pat_*` usada no modelo ML. O **classificador de estilo** devolve tags como `stream`, `tech`, `jump`, `crossover`, `speed`, `obstacle`, `balanced`.

### 4.4 `trainer.py` — Machine Learning

- **Features**: 15 base (velocidade, técnica, strain, meta) + 34 de padrão (`pat_*`);
- **Modelo**: `HistGradientBoostingRegressor` (1000 iterações, early stopping, 5-fold CV);
- **Avaliação**: MAE por range de stars (<5★, 5–8★, 8–10★, >10★) e MAE por estilo de mapa; permutation feature importance;
- **Heurística de fallback** (`heuristic_stars`): estimativa empírica para quando não há modelo treinado ou para mapas não rankeados;
- **Ajustes de rating**: sistema de deltas persistidos em `rating_adjustments.json`, aplicados automaticamente nas predições.

### 4.5 `player_performance.py` — Ajuste por performance

Conecta no **ScoreSaber API** e, para um mapa+dificuldade:

1. Busca o leaderboard (info + até 5 páginas de scores, com rate limit);
2. Filtra jogadores com PP ≥ 1000 (evita "casuals");
3. Calcula **accuracy ponderada pelo rank** (decay 0.97), mediana, FC rate e distribuição (90–100%, 80–90%...);
4. Compara a mediana observada com uma **curva empírica esperada** (ex.: 5★ → ~93%, 9★ → ~85%);
5. Sugere um **delta de stars** (sensibilidade 1% acc ≈ 0.25★, limitado a ±2★) com nível de confiança (low/medium/high).

### 4.6 `main.py` — CLI

| Comando | O que faz |
|---|---|
| `download --limit N --threads T` | Baixa mapas rankeados do ScoreSaber/BeatSaver, analisa cada dificuldade e popula `dataset.csv` (retomável, com checkpoint) |
| `train` | Treina o modelo e salva `star_rating_model.pkl` |
| `analyze <hash|id>` | Baixa e analisa o mapa; exibe tabela por dificuldade (NPS, peak, strain, streams, jumps, cross%, estilo, acc real, ★ predita); aceita `--buff`/`--nerf` |
| `analyze-playlist <arquivo.bplist>` | Analisa uma playlist inteira e salva em `playlist_analysis.json`; `--interactive` permite buff/nerf manual |
| `performance <hash> -d <diff> [--suggest] [--save]` | Análise de performance real dos players; sugere e opcionalmente salva ajuste de rating |
| `adjust-rating <hash> -d <diff> [--delta X | --set-stars Y]` | Ajuste manual de rating |
| `unranked <hash|id> [--verbose]` | Estimativa de stars de mapa não rankeado (sem dados do SS) |
| `dataset-info` | Estatísticas do dataset (linhas, músicas únicas, distribuição por dificuldade e stars) |
| `list-adjustments` | Lista os ajustes de rating salvos |

### 4.7 `gui.py` — Interface gráfica

App **CustomTkinter** (tema dark) com 3 abas:

- **Analyze**: entrada de ID/hash → download → análise → tabela de dificuldades com predição editável (+/- 0.1★) → salvar no histórico;
- **History**: lista de análises salvas (`analyzed_history.json`) em Treeview;
- **Train/Settings**: botão para re-treinar o modelo.

---

## 5. Fluxo típico de uso

```bash
# 1. (Opcional) Montar dataset e treinar modelo próprio
python main.py download --limit 500 --threads 8
python main.py train

# 2. Analisar um mapa rankeado (usa modelo/heurística + acc real + ajustes)
python main.py analyze <hash_ou_id>

# 3. Estimar mapa não rankeado
python main.py unranked <hash_ou_id> --verbose

# 4. Validar com performance real e ajustar rating
python main.py performance <hash> -d ExpertPlus --suggest --save
python main.py adjust-rating <hash> -d ExpertPlus --set-stars 9.5 --reason "..."

# 5. Analisar uma playlist
python main.py analyze-playlist analyze/bsbr_ranked.bplist --interactive
```

O rating "vive" em loop: **predição estática → performance real → ajuste → próxima predição já sai ajustada**.

---

## 6. Notas e observações

- O arquivo `star_rating_model.pkl` está **vazio (0 bytes)** no estado atual — é preciso rodar `python main.py train` (com `dataset.csv` populado) para ativar a predição por modelo; sem ele, o sistema usa a heurística (`predict_with_fallback`).
- O `dataset.csv` atual contém mapas rankeados com stars oficiais do ScoreSaber (ex.: KICK BACK, Fractured Angel, AμreoLe, etc.), servindo como base de treino.
- `2.csv` parece ser um dump antigo/experimental do mesmo formato — candidato a consolidação com `dataset.csv`.
- As pastas `_rules/` contêm apenas **documentação de schema das APIs** (BeatLeader, BeatSaver, ScoreSaber) usada como referência de desenvolvimento.
- O parser ignora eventos de iluminação e características não-Standard (Lawless, OneSaber...) — foco total na dificuldade "Standard" que é a usada em rankings oficiais.
- Há suporte a **V3 (arcs/chains)** no `pattern_analyzer` e a **V4** no `analyzer.py`.

---

## 7. Dependências

```
requests        # APIs ScoreSaber / BeatSaver
pandas          # dataset / dataframe
scikit-learn    # HistGradientBoostingRegressor, CV, métricas
joblib          # persistência do modelo (.pkl)
customtkinter   # GUI
Pillow          # imagens (GUI)
packaging       # utilitário (dependência)
```
