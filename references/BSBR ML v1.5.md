# BSBR ML v1.5 — Plano de implementação

> Portar features do `beatleader-analyzer` (C#) para o `bsbr_analyzer` (Python)
> como inputs do ML existente, deixando o modelo mais capaz de entender
> dificuldade técnica real do mapa (swing, paridade, walls, NJS, multi-note).
>
> Fonte: `references/beatleader-analyzer/` (clone de
> `github.com/BeatLeader/beatleader-analyzer` + parser em
> `github.com/BeatLeader/beatleader-parser` @ `aa9a24d`).
>
> Data: 2026-09-01 · Status: **planejamento**

---

## 0. Goal e não-goals

**Goal:** reduzir o MAE CV do modelo de stars (hoje 0.54★) para ~0.35-0.40★
adicionando features swing-based portadas do BL, sem quebrar golden tests do
PP engine nem o invariante `Σ sub-stars == total_stars`.

**Não-goals (v1.5):**
- Não reescrever o `pp_engine` (curva legado, decomposição, agregação intactas).
- Não mudar o significado dos sub-stars (isso é v2.0, fase opcional 4).
- Não substituir o parser V2/V3/V4 do BSBR (só adicionar tipos que faltam).
- Não mudar a pipeline de sync/reweight/ranking.

**Princípio:** o BL é **determinístico** (algoritmo → PassRating/TechRating/MultiRating).
O BSBR usa **ML** sobre features. O valor do BL para o BSBR está nas **features
ricas** que captam dificuldade que nota-a-nota não vê — portar como inputs do ML,
não como substituto.

---

## 1. O que o BL tem que o BSBR não (resumo)

| Conceito | BL | BSBR atual |
|---|---|---|
| Unidade de análise | **Swing** (grupo de notas, slider/multi-note) | Nota |
| Paridade (forehand/backhand) | **DP (Viterbi)** minimizando angle strain | Heurística `NATURAL_FLOW` |
| Direção de dot notes | Flow anterior + **bomb avoidance** (player position tracking) | `DIR_TO_ANGLE` fixo |
| Multi-note | Stack, Tower, Window, Slanted Window, Slider, Curved Slider (discriminado) | `pat_stack_count` genérico |
| Walls | **Dodge vs Crouch** (buffs 1.1/1.2, cooldown, merge) | `obstacle_count` |
| Bombs | **Bomb avoidance** (parity flip, player move) | `bomb_count` |
| NJS | **NJS buff** (`njs>24 → 1+0.01*(njs-24)`) | Armazenado, não usado |
| BPM/NJS events | Parseia **BpmEvent/NjsEvent** (BPM variable) | Assume BPM fixo |
| Arcs/Chains | First-class | Chains parseado, arcs não |
| Pass diff | **5 janelas** {8,16,32,64,128} | 1 janela 1s |
| Peak sustained | **EBPM** (janela 4 swings) | peak_nps instantâneo |
| Stress model | `stress = angle*0.05 + repositioning*0.3 + rotation*0.2` com saturação | — |
| One-saber nerf | `handsRatio` (desequilíbrio entre mãos) | — |
| Low-note nerf | `0.6 + (clamp(20,200,n)-20)/450` | — |
| Linear swing | Detecta (direção + movimento match) | — |

---

## 2. Fases

### Fase 1 — Parser (pré-requisito, ~0.5 dia)

Portar tipos do `beatleader-parser` que o BSBR não lê. Sem isso, features
swing-based ficam erradas em mapas com BPM/NJS variable.

**Arquivos do BL (referência):**
- `Map/Difficulty/V3/Event/BpmEvent.cs` — `{b: beats, m: bpm}`
- `Map/Difficulty/V3/Event/NjsEvent.cs` — `{b: beats, d: delta, p: usePrevious, e: easing}`
- `Map/Difficulty/V3/Grid/Chain.cs` — `{b, x, y, c, d, tb: tailInBeats, tx, ty, sc: sliceCount, s: squish}`
- `Map/Difficulty/V3/Grid/Arc.cs` — chain + `{mu: multiplier, tmu: tailMultiplier, m: anchorMode}`

**Arquivos do BSBR (editar/criar):**
- `backend/bsbr_analyzer/parser/objects.py` — adicionar `Chain`, `Arc`, `BpmEvent`, `NjsEvent` dataclasses
- `backend/bsbr_analyzer/parser/beatmap.py:28` — parsear `chains`, `arcs`, `bpmEvents`, `njsEvents` em `_parse_v3` e `_parse_v41`
- `backend/bsbr_analyzer/parser/base.py` — adicionar `seconds` (tempo real respeitando BPM events) se necessário

**Decisão:** V2 não tem esses tipos — só V3/V4. Arcs/Chains em V4.1 usam o mesmo
padrão delta de `colorNotesData` (já implementado para notes).

**Validação:** adicionar teste `tests/bsbr_analyzer/test_parser.py::test_v3_with_bpm_events` com um mapa real que tenha BPM variable (ex.: camaleontic maps). Confirmar que `beatmap.chains` e `beatmap.bpm_events` são populados.

---

### Fase 2 — Swing features (núcleo, ~2-3 dias)

Portar o núcleo do BL analyzer para Python como gerador de features. Roda em
paralelo a `features.py` + `patterns.py` atuais; o output é mergeado no dict
de features final.

**Arquivo novo:** `backend/bsbr_analyzer/swing_features.py`

**Ports (1:1 do C#, Python puro, sem deps):**

| Módulo BL | Linha chave | O que faz |
|---|---|---|
| `PreprocessNotes.cs` | `Detect` (24), `CreateNoteGroups` (39), `ValidateSliders` (145), `AnalyzeBombInfluence` (510) | Agrupa notas em swings, detecta sliders, calcula direção de dots, simula bomb avoidance |
| `ParityPredictor.cs` | `Predict` (15) | DP para paridade forehand/backhand ótima, detecta parity errors |
| `SwingCreation.cs` | `Process` (19), `CalcEntryExit`, `VerifyMultiNotes` (184) | Cria SwingData com entry/exit, swing frequency, hit distance, angle strain, linear detection |
| `SwingMovement.cs` | `Calc` (16) | Repositioning distance (perpendicular + 2-swing avg), rotation amount |
| `AngleStrain.cs` | `SwingAngleStrainCalc` (14), `ParityAngleStrainCalc` (52) | Strain angular vs neutro forehand/backhand, falloff temporal |
| `MultiNoteClassifier.cs` | `CountMultiNoteHits` (23), `IsStack/Tower/Window/CurvedSlider` | Classifica Stack/Tower/Window/SlantedWindow/Slider/CurvedSlider |
| `WallClassifier.cs` | `ClassifyWalls` (14) | Dodge vs Crouch, cooldown 1s, merge walls sobrepostas |
| `NjsBuff.cs` | `CalculateNjsBuff` (7) | `njs>24 → 1+0.01*(njs-24)` |
| `AnalyzeMap.cs` | `UseAlgorithm` (24) | Orquestra tudo, calcula PassRating/TechRating/MultiRating/PeakSustainedEBPM/LowNoteNerf/OneSaberRatio |

**Estrutura Python proposta:**

```python
# backend/bsbr_analyzer/swing_features.py
@dataclass
class SwingData:
    cubes: list[Note]
    bpm_time: float
    direction: float
    entry_position: tuple[float, float]
    exit_position: tuple[float, float]
    forehand: bool
    parity_error: bool
    bomb_avoidance: bool
    is_linear: bool
    angle_strain: float
    repositioning_distance: float
    rotation_amount: float
    swing_frequency: float
    hit_distance: float
    swing_diff: float
    swing_tech: float
    pattern_type: str  # Single/Stack/Tower/Window/SlantedWindow/Slider/CurvedSlider

@dataclass
class SwingAnalysis:
    swings: list[SwingData]
    pass_rating: float
    tech_rating: float
    multi_rating: float
    peak_sustained_ebpm: float
    low_note_nerf: float
    one_saber_ratio: float
    linear_percentage: float
    statistics: dict  # stacks, towers, sliders, curved_sliders, windows, slanted_windows,
                      # dodge_walls, crouch_walls, parity_errors, bomb_avoidances, linear_swings

def analyze_swings(beatmap: Beatmap, bpm: float, njs: float, speed_mult: float = 1, njs_mult: float = 1) -> SwingAnalysis:
    """Porte de AnalyzeMap.UseAlgorithm."""
    ...

def compute_swing_features(beatmap: Beatmap, bpm: float, njs: float) -> dict[str, float]:
    """Retorna dict de features para o ML (chaves pat_swing_*)."""
    analysis = analyze_swings(beatmap, bpm, njs)
    return {
        "pat_swing_count": len(analysis.swings),
        "pat_swing_frequency_avg": ...,
        "pat_swing_frequency_peak": ...,
        "pat_hit_distance_avg": ...,
        "pat_repositioning_distance_avg": ...,
        "pat_rotation_amount_avg": ...,
        "pat_angle_strain_avg": ...,
        "pat_angle_strain_peak": ...,
        "pat_linear_swing_ratio": analysis.linear_percentage,
        "pat_parity_error_count_dp": analysis.statistics["parity_errors"],
        "pat_parity_error_ratio_dp": ...,
        "pat_bomb_avoidance_count": analysis.statistics["bomb_avoidances"],
        "pat_stack_count": analysis.statistics["stacks"],
        "pat_tower_count": analysis.statistics["towers"],
        "pat_slider_count": analysis.statistics["sliders"],
        "pat_curved_slider_count": analysis.statistics["curved_sliders"],
        "pat_window_count": analysis.statistics["windows"],
        "pat_slanted_window_count": analysis.statistics["slanted_windows"],
        "pat_dodge_wall_count": analysis.statistics["dodge_walls"],
        "pat_crouch_wall_count": analysis.statistics["crouch_walls"],
        "pat_njs_buff_avg": ...,
        "pat_njs_max": ...,
        "pat_peak_sustained_ebpm": analysis.peak_sustained_ebpm,
        "pat_multi_rating_bl": analysis.multi_rating,
        "pat_low_note_nerf": analysis.low_note_nerf,
        "pat_one_saber_ratio": analysis.one_saber_ratio,
        # Opcionais (compostos do BL):
        "pat_pass_rating_bl": analysis.pass_rating,
        "pat_tech_rating_bl": analysis.tech_rating,
    }
```

**Integração em `analysis.py`:**

```python
# analysis.py, em analyze_map_folder, depois de compute_physical_features + analyze_patterns:
from .swing_features import compute_swing_features
swing_feats = compute_swing_features(beatmap, bpm=info_bpm, njs=diff_njs)
features.update(swing_feats)
```

**Constantes críticas (porte exato):**
- `PASS_CALIBRATION_FACTOR = 0.825`
- `ONE_SABER_NERF = 0.5`
- `BALANCED_TECH_SCALER = 14.0`
- `STRESS_FALLOFF = 2.0`, `DISTANCE_FALLOFF = 2.668`, `SPEED_FALLOFF_BASE = 1.4`
- `PARITY_ERROR_MULTIPLIER = 2.0`, `STREAM_BONUS = 1.05`
- `DODGE_WALL_BUFF = 1.1`, `CROUCH_WALL_BUFF = 1.2`, `WALL_EXTRA_DURATION = 0.5`
- Neutros: `LEFT_FOREHAND=292.5`, `RIGHT_FOREHAND=247.5`, `LEFT_BACKHAND=112.5`, `RIGHT_BACKHAND=67.5`
- Window sizes: `{8, 16, 32, 64, 128}`
- Multi-note values: `STACK=1.05, TOWER=1.1, SLIDER=1.05, CURVED_SLIDER=1.5, WINDOW=1.1`
- `SIMULTANEOUS_THRESHOLD_SEC = 0.020`, `STREAM_BEAT_THRESHOLD = 0.27`, `DOUBLE_BEAT_THRESHOLD = 0.13`, `STREAM_MIN_LENGTH = 5`

**Validação:** teste `tests/bsbr_analyzer/test_swing_features.py` com um mapa real (ex.: um tech map conhecido) — confirmar que `parity_error_count_dp > 0`, `curved_slider_count > 0` etc. não são todos zero (sanity). Comparar com output do BL Benchmark para o mesmo mapa (tolerância 1e-6).

---

### Fase 3 — Treinamento e validação (~0.5 dia)

**`trainer.py`:** adicionar `SWING_FEATURES` em `ALL_FEATURES`:

```python
SWING_FEATURES = [
    "pat_swing_count", "pat_swing_frequency_avg", "pat_swing_frequency_peak",
    "pat_hit_distance_avg", "pat_repositioning_distance_avg", "pat_rotation_amount_avg",
    "pat_angle_strain_avg", "pat_angle_strain_peak", "pat_linear_swing_ratio",
    "pat_parity_error_count_dp", "pat_parity_error_ratio_dp", "pat_bomb_avoidance_count",
    "pat_stack_count", "pat_tower_count", "pat_slider_count", "pat_curved_slider_count",
    "pat_window_count", "pat_slanted_window_count",
    "pat_dodge_wall_count", "pat_crouch_wall_count",
    "pat_njs_buff_avg", "pat_njs_max", "pat_peak_sustained_ebpm",
    "pat_multi_rating_bl", "pat_low_note_nerf", "pat_one_saber_ratio",
    "pat_pass_rating_bl", "pat_tech_rating_bl",
]
ALL_FEATURES = BASE_FEATURES + PATTERN_FEATURES + SWING_FEATURES
```

**`dataset.py`:** reprocessar dataset com `--force` para popular as novas colunas. O `DATASET_FIELDNAMES` já usa `ALL_FEATURES`, então automático.

**Treinar e comparar:**

```bash
cd backend
python -m bsbr_analyzer download --force   # reprocessa dataset
python -m bsbr_analyzer train              # treina com features novas
python -m bsbr_analyzer dataset-info       # valida esquema
```

**Métricas de sucesso:**
- MAE CV antes: 0.54★ (baseline)
- MAE CV depois: target ≤ 0.40★
- R² CV depois: target ≥ 0.93
- `permutation_importance` — confirmar que as features swing estão entre as top 20; se alguma for inútil, remover.

**Rollback:** se MAE não melhorar ou piorar, reverter para o modelo anterior (`models/star_rating_model.pkl` versionado). O código das features pode ficar (não atrapalha), só o modelo volta.

---

### Fase 4 (opcional, v2.0) — Sub-stars baseadas em ratings do BL

**NÃO fazer em v1.5.** Documentar aqui para referência futura.

Hoje as shares acc/tech/speed vêm de heurísticas sobre features (`substars.py:46-75`).
O BL calcula PassRating, TechRating, MultiRating determinísticos. Usar como base:

```python
# substars.py, alternativa futura:
pass_r = swing_analysis.pass_rating
tech_r = swing_analysis.tech_rating
multi_r = swing_analysis.multi_rating
total = pass_r + tech_r + multi_r
shares = {"acc": pass_r/total, "tech": tech_r/total, "speed": multi_r/total}
```

**Risco:** muda o significado dos sub-stars e os rankings por componente. Precisa:
- Validar `Σ sub-stars == total_stars` (invariante mantido pela normalização).
- Comunicação aos jogadores (rankings por componente vão mudar).
- Nova bateria de golden tests.

---

## 3. Validação e invariantes

### Invariantes que NÃO podem quebrar (v1.5)
1. `Σ sub-stars == total_stars` — `substars.compute_substars` intacto.
2. `Σ sub-PP == total-PP` — `pp.decompose_pp` intacto.
3. Curva de PP == legado — golden tests intactos.
4. 1 score por (player, difficulty) — sync intacto.
5. PP interno do BSBR — ranking intacto.

v1.5 só toca `bsbr_analyzer` (features + modelo). O `pp_engine`, `sync`,
`ranking`, `reweight` não são alterados. O pior caso é o modelo predizer stars
pior — rollback do `.pkl` resolve.

### Testes a adicionar
- `tests/bsbr_analyzer/test_parser.py::test_v3_bpm_events`
- `tests/bsbr_analyzer/test_parser.py::test_v3_chains_arcs`
- `tests/bsbr_analyzer/test_swing_features.py::test_tech_map_has_parity_errors`
- `tests/bsbr_analyzer/test_swing_features.py::test_wall_classification_dodge_crouch`
- `tests/bsbr_analyzer/test_swing_features.py::test_bl parity_dp_matches_heuristic_on_simple_map`
- `tests/bsbr_analyzer/test_swing_features.py::test_features_finite_and_non_negative`
- `tests/bsbr_analyzer/test_trainer.py::test_model_with_swing_features_mae_below_threshold`

### Testes existentes que devem continuar verdes
- `tests/bsbr_analyzer/test_parser.py` (V2/V3/V4 existentes)
- `tests/bsbr_analyzer/test_features.py`
- `tests/bsbr_analyzer/test_patterns.py`
- `tests/bsbr_analyzer/test_stars.py` (golden vs legado)
- `tests/bsbr_analyzer/test_trainer.py` (MAE/R²)

---

## 4. Riscos e mitigações

| Risco | Prob | Mitigação |
|---|---|---|
| Port Python diverge do C# (bug silencioso) | Médio | Teste de paridade com BL Benchmark em N mapas (ex.: 10), tolerância 1e-6 |
| Features novas não melhoram MAE | Médio | `permutation_importance` sinaliza; rollback do `.pkl` |
| Performance: swing analysis lenta | Baixo | Profilar; se >2x features.py, otimizar (numpy/vectorizar) ou rodar em thread |
| BPM variable quebra features existentes | Baixo | Features existentes usam BPM fixo; só as novas respeitam BpmEvent |
| Mapas V2 sem chains/arcs | Baixo | `_parse_v2` não toca; swings vazios → features swing = 0 |
| Dataset reprocess demora | Médio | ~500 amostras, ~15 min com rate-limit; rodar em background |

---

## 5. File map

**Criar:**
- `backend/bsbr_analyzer/swing_features.py` — núcleo da port (~600 linhas)
- `backend/tests/bsbr_analyzer/test_swing_features.py` — testes

**Editar:**
- `backend/bsbr_analyzer/parser/objects.py` — adicionar `Chain`, `Arc`, `BpmEvent`, `NjsEvent`
- `backend/bsbr_analyzer/parser/beatmap.py` — parsear novos tipos em `_parse_v3`/`_parse_v41`
- `backend/bsbr_analyzer/analysis.py` — chamar `compute_swing_features` e mergear
- `backend/bsbr_analyzer/trainer.py` — adicionar `SWING_FEATURES` em `ALL_FEATURES`
- `backend/tests/bsbr_analyzer/test_parser.py` — testes dos novos tipos

**Não tocar:**
- `backend/app/services/pp_engine/*` (curva, decomposição, agregação)
- `backend/app/services/sync/*`
- `backend/app/services/ranking.py`
- `backend/app/services/reweight/*`
- `backend/bsbr_analyzer/substars.py` (só na Fase 4 opcional)
- `backend/bsbr_analyzer/features.py` (features nota-a-nota mantidas)
- `backend/bsbr_analyzer/patterns.py` (features pat_* mantidas)

---

## 6. Ordem de execução (commits por etapa)

1. **Commit A (parser):** Fase 1 — `Chain`/`Arc`/`BpmEvent`/`NjsEvent` + testes. Roda `pytest tests/bsbr_analyzer/test_parser.py`.
2. **Commit B (swing core):** Fase 2 — `swing_features.py` com `PreprocessNotes` + `ParityPredictor` + `SwingCreation` + `SwingMovement`. Teste sanity (não crasha, features finitas).
3. **Commit C (swing classifiers):** Fase 2 — `MultiNoteClassifier` + `WallClassifier` + `NjsBuff` + `AnalyzeMap` (ratings). Teste de paridade vs BL Benchmark em 3 mapas.
4. **Commit D (integração ML):** Fase 3 — `SWING_FEATURES` em `trainer.py`, `compute_swing_features` em `analysis.py`. Rodar `download --force` + `train`.
5. **Commit E (validação):** Comparar MAE antes/depois. Se melhor, commit do novo `.pkl`. Se pior, rollback do `.pkl` e documentar no commit.

Cada commit deve deixar o sistema verde (`pytest -q` + `next build`). Rollback
a qualquer etapa é limpo (reverter o commit).

---

## 7. Referências

- BL analyzer: `references/beatleader-analyzer/beatleader-analyzer/BeatmapScanner/`
- BL parser: `references/beatleader-analyzer/Parser/beatleader-parser/beatleader-parser/Map/`
- BSBR analyzer: `backend/bsbr_analyzer/`
- BSBR trainer: `backend/bsbr_analyzer/trainer.py`
- BSBR dataset: `backend/bsbr_analyzer/data/dataset.csv` (500 amostras, 256 músicas)
- BSBR modelo: `backend/bsbr_analyzer/models/star_rating_model.pkl`
- Plan.md original: `Plan.md` §3.1 (sub-stars), §3.2 (PP)
- ARCHITECTURE.md: `references/ARCHITECTURE.md` §5 (ML)
