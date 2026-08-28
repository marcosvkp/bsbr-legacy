# Beat Saber Star Analyzer

Ferramenta de análise e predição de dificuldade (stars) para mapas de Beat Saber, com integração ao ScoreSaber.

---

## Estrutura de Arquivos

```
app/
├── main.py               # CLI principal
├── analyzer.py           # Análise de estrutura do mapa (integra parser + padrões)
├── pattern_analyzer.py   # Detecção profunda de padrões (NOVO)
├── player_performance.py # Análise de performance real via ScoreSaber API (NOVO)
├── trainer.py            # Treinamento e predição do modelo ML
├── parser/
│   ├── beatmap.py        # Classe Beatmap (parse V2 e V3)
│   ├── objects.py        # Note, Obstacle, Event
│   ├── enums.py          # NoteColor, NoteCutDirection, etc.
│   ├── loader.py         # Carregamento de arquivos .dat
│   └── base.py           # BeatmapObject base
└── README.md
```

---

## Instalação

```bash
pip install scikit-learn pandas numpy joblib requests
```

---

## Comandos

### `download` — Baixar mapas rankeados para treino

```bash
python main.py download --limit 500 --threads 8
```

Baixa mapas rankeados do ScoreSaber, analisa cada um e salva no `dataset.csv`.

---

### `train` — Treinar o modelo

```bash
python main.py train
```

Treina o modelo `HistGradientBoostingRegressor` com **49 features** (15 base + 34 de padrão).  
Exibe MAE por range de stars, MAE por estilo de mapa e feature importance.

---

### `analyze` — Analisar um mapa rankeado

```bash
python main.py analyze <hash_ou_id_beatsaver>
python main.py analyze abc123 --buff 0.5
python main.py analyze abc123 --nerf 1.0
```

Exibe tabela com todas as dificuldades incluindo:
- NPS, Peak NPS, Peak Strain, Volatility
- Stream ratio, Jump density, Crossover %
- Estilo detectado (stream / tech / jump / crossover / speed / obstacle / balanced)
- Accuracy real do ScoreSaber
- Stars preditas (modelo ou heurística)

---

### `unranked` — Estimar stars de mapa não rankeado

```bash
python main.py unranked <hash_ou_id_beatsaver>
python main.py unranked abc123 --verbose
```

Mesmo que `analyze`, mas sem buscar accuracy do ScoreSaber (mapa não está rankeado).  
`--verbose` exibe breakdown detalhado de padrões por dificuldade.

---

### `performance` — Analisar performance real dos players

```bash
# Análise simples
python main.py performance <hash> -d ExpertPlus

# Com sugestão de ajuste de rating
python main.py performance <hash> -d ExpertPlus --suggest

# Com sugestão E salva automaticamente se confiança for medium/high
python main.py performance <hash> -d ExpertPlus --suggest --save
```

Coleta até 5 páginas de scores do leaderboard e calcula:
- Accuracy ponderada pelo rank (top players têm mais peso)
- Mediana de accuracy
- Taxa de Full Combo
- Distribuição de accuracy (90-100%, 80-90%, etc.)
- Sugestão de delta de rating baseado em curvas empíricas

---

### `adjust-rating` — Ajuste manual de rating

```bash
# Adiciona/subtrai delta fixo
python main.py adjust-rating <hash> -d ExpertPlus --delta 0.8 --reason "Map é mais fácil que parece"

# Define as stars finais diretamente
python main.py adjust-rating <hash> -d ExpertPlus --set-stars 9.5
```

Salva o ajuste em `rating_adjustments.json`. O ajuste é aplicado automaticamente em `analyze` e `analyze-playlist`.

---

### `list-adjustments` — Ver ajustes salvos

```bash
python main.py list-adjustments
```

---

### `analyze-playlist` — Analisar playlist inteira

```bash
python main.py analyze-playlist minha_playlist.bplist
python main.py analyze-playlist minha_playlist.bplist --interactive
```

`--interactive` permite aplicar buff/nerf manualmente em cada dificuldade.

---

## Padrões Detectados

O `pattern_analyzer.py` detecta e quantifica:

| Feature | Descrição |
|---|---|
| `pat_stream_*` | Streams (notas rápidas consecutivas por mão) |
| `pat_jump_*` | Jumps (ambas as mãos simultâneas com distância) |
| `pat_crossover_*` | Crossovers (mão cruzando a linha central) |
| `pat_double_*` | Doubles/Bursts (notas extremamente rápidas duplas) |
| `pat_stack_count` | Stacks (notas sobrepostas na grid) |
| `pat_parity_break_*` | Quebras de parity / resets de pulso |
| `pat_reset_intensity` | Ângulo médio dos resets |
| `pat_tech_ratio` | Proporção de notas diagonais (tech) |
| `pat_hand_dominance` | Assimetria de trabalho entre mãos |
| `pat_obstacle_density` | Paredes por segundo |
| `pat_bomb_density` | Bombas por segundo |
| `pat_vision_block_severity` | Severidade de vision blocks |
| `pat_arc_*` / `pat_chain_*` | Arcs e Chains (V3) |
| `pat_pattern_complexity` | Índice agregado de complexidade |

---

## Estilos de Mapa

O classificador detecta automaticamente:

- **stream** — Notas rápidas consecutivas (>35% das notas em stream, ou BPM efetivo >160)
- **tech** — Muitas diagonais e breaks de parity (>25% tech, >20% parity breaks)
- **jump** — Movimentos grandes entre mãos (density >15%, distância >2.0)
- **crossover** — Muitos cruzamentos de linha central (>12%)
- **speed** — Doubles/bursts frequentes (>8%)
- **obstacle** — Paredes densas (>0.5/s)
- **balanced** — Nenhum estilo dominante

---

## Fluxo de Rating com Ajuste por Performance

```
1. analyze/unranked → predição inicial (modelo ML ou heurística)
2. performance --suggest → calcula delta baseado em accuracy real dos players
3. adjust-rating --delta / --save → persiste o delta em rating_adjustments.json
4. analyze (próxima vez) → aplica delta automaticamente ao resultado
```

O rating muda de acordo com como os jogadores realmente jogam o mapa.

---

## Lógica de Ajuste de Rating

Curva empírica usada:
- **1★** → accuracy mediana esperada: ~98%
- **5★** → ~91%
- **9★** → ~85%
- **13★+** → ~78%

Se a mediana observada estiver muito acima do esperado → mapa está fácil demais → aumentar stars.  
Se estiver muito abaixo → mapa está difícil demais → diminuir stars.

Sensibilidade: **1% de diferença de accuracy ≈ 0.25 stars**.  
Limite máximo de ajuste automático: **±2 stars** (mudanças maiores requerem `adjust-rating` manual).

