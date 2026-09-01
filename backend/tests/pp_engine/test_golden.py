"""Golden tests do motor de PP.

- Paridade TOTAL com o módulo legado (``backend/references/scorecalc.py``,
  cópia do `references/bsbr/app/scorecalc/__init__.py` — o legado tem `.git`
  próprio e não sobe no repo principal), importado dinamicamente via
  importlib: get_pp numa grade stars × acc.
- Invariantes de ``decompose_pp`` (Plan.md §3.2).
- Contrato de ``weighted_pp`` e da calculadora +1pp.
"""

from __future__ import annotations

import importlib.util
import math
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.pp_engine import (  # noqa: E402
    CALIBRATION_ACC,
    STAR_MULTIPLIER,
    WEIGHT_COEFFICIENT,
    calc_raw_pp_at_idx,
    calc_raw_pp_for_expected_pp,
    decompose_pp,
    get_modifier,
    get_pp,
    get_raw_pp_for_weighted_pp_gain,
    raw_pp_for_expected_gain,
    weighted_pp,
)


def _load_legacy():
    spec = importlib.util.spec_from_file_location(
        "legacy_scorecalc",
        REPO_ROOT / "backend" / "references" / "scorecalc.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = _load_legacy()
# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
def test_constants_match_legacy():
    assert STAR_MULTIPLIER == legacy.STAR_MULTIPLIER == 42.117208413
    assert WEIGHT_COEFFICIENT == legacy.WEIGHT_COEFFICIENT == 0.965
    # Ponto de calibração: curva em acc=95% (percentual) vale exatamente 1.0.
    assert get_modifier(95) == legacy.get_modifier(95) == 1.0

# ---------------------------------------------------------------------------
# Golden: paridade total get_pp / get_modifier com o legado
# ---------------------------------------------------------------------------


def _golden_cases():
    cases = []
    for stars in [i * 0.5 for i in range(2, 31)]:  # 1.0 .. 15.0 passo 0.5
        for acc_pct in range(60, 101):  # 60..100 inteiro
            cases.append((stars, acc_pct))
    return cases


@pytest.mark.parametrize("stars,acc_pct", _golden_cases())
def test_golden_get_pp_matches_legacy(stars, acc_pct):
    expected = legacy.get_pp(stars=stars, accuracy=acc_pct)
    assert get_pp(stars, acc_pct) == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize(
    "acc",
    [
        0.0, 0.001, 0.5, 0.5999, 0.6, 0.625, 0.7, 0.8, 0.85, 0.875,
        0.9, 0.93, 0.95, 0.96, 0.9712345, 0.98, 0.99, 0.9951234,
        0.999, 0.99999, 1.0, 1.00001, 50.0, 87.33, 100.0, 105.0, -3.0,
    ],
)
def test_golden_get_modifier_matches_legacy(acc):
    assert get_modifier(acc) == pytest.approx(legacy.get_modifier(acc), abs=1e-12)


def test_curve_endpoints_and_edges():
    assert get_modifier(0) == 0.0
    assert get_modifier(-1) == 0.0
    # Saturação no último multiplicador (acc normalizada >= 1 => >= 100%).
    assert get_modifier(100) == get_modifier(105) == 5.367394282890631
    # Valor bruto em 1.0 é idêntico ao legado (cai no primeiro segmento).
    assert get_modifier(1.0) == pytest.approx(legacy.get_modifier(1.0), abs=1e-15)


def test_golden_get_pp_fraction_matches_legacy():
    rng = random.Random(42)
    for _ in range(200):
        stars = rng.uniform(1, 15)
        acc = rng.uniform(0.5, 1.0)
        assert get_pp(stars, acc) == pytest.approx(
            legacy.get_pp(stars=stars, accuracy=acc), abs=1e-9
        )


# ---------------------------------------------------------------------------
# decompose_pp — invariantes (Plan.md §3.2)
# ---------------------------------------------------------------------------


def test_decompose_sum_equals_total_random_grid():
    rng = random.Random(2024)
    checked = 0
    while checked < 300:
        total_stars = rng.uniform(0.5, 16)
        acc = rng.uniform(0.6, 1.0)
        s_acc = rng.uniform(0, 10)
        s_tech = rng.uniform(0, 10)
        s_speed = rng.uniform(0, 10)
        if s_acc + s_tech + s_speed == 0:
            continue
        sub = decompose_pp(total_stars, acc, s_acc, s_tech, s_speed)
        total = sub["pp_acc"] + sub["pp_tech"] + sub["pp_speed"]
        assert total == pytest.approx(sub["pp_total"], abs=1e-9)
        expected_total = get_pp(total_stars, acc)
        assert sub["pp_total"] == pytest.approx(expected_total, abs=1e-12)
        checked += 1


def test_decompose_normalizes_shares():
    a = decompose_pp(8.0, 0.97, 5, 1, 1)
    b = decompose_pp(8.0, 0.97, 50, 10, 10)
    for key in ("pp_acc", "pp_tech", "pp_speed", "pp_total"):
        assert a[key] == pytest.approx(b[key], abs=1e-9)


def test_decompose_at_calibration_is_proportional_to_shares():
    sub = decompose_pp(10.0, 0.95, share_acc=5, share_tech=3, share_speed=2)
    total = sub["pp_total"]
    assert sub["pp_acc"] == pytest.approx(total * 0.5, abs=1e-9)
    assert sub["pp_tech"] == pytest.approx(total * 0.3, abs=1e-9)
    assert sub["pp_speed"] == pytest.approx(total * 0.2, abs=1e-9)


def test_decompose_tech_monotonic_in_accuracy():
    prev = None
    for i in range(96, 101):
        acc = i / 100
        sub = decompose_pp(7.0, acc, 1, 1, 0)
        if prev is not None:
            assert sub["pp_tech"] > prev
        prev = sub["pp_tech"]


def test_decompose_high_accuracy_shifts_to_tech():
    low = decompose_pp(7.0, 0.95, 5, 1, 1)
    high = decompose_pp(7.0, 0.995, 5, 1, 1)
    assert high["pp_tech"] > low["pp_tech"]
    assert high["pp_acc"] < low["pp_acc"]


def test_decompose_high_accuracy_shifts_to_tech():
    # Sensibilidade do tech à acc (1.9) é maior que a do speed (1.2): a razão
    # entre as fatias tech/speed cresce estritamente com a acurácia.
    prev_ratio = None
    for i in range(95, 100):
        acc = i / 100
        sub = decompose_pp(7.0, acc, 1, 1, 1)
        ratio = sub["pp_tech"] / sub["pp_speed"]
        if prev_ratio is not None:
            assert ratio > prev_ratio
        prev_ratio = ratio


def test_decompose_validations():
    with pytest.raises(ValueError):
        decompose_pp(0, 0.95, 1, 1, 1)
    with pytest.raises(ValueError):
        decompose_pp(-1, 0.95, 1, 1, 1)
    with pytest.raises(ValueError):
        decompose_pp(7.0, 0.95, -0.1, 1, 1)


def test_decompose_all_zero_shares_falls_back_to_acc():
    sub = decompose_pp(7.0, 0.95, 0, 0, 0)
    assert sub["pp_acc"] == pytest.approx(sub["pp_total"], abs=1e-12)
    assert sub["pp_tech"] == 0.0
    assert sub["pp_speed"] == 0.0


# ---------------------------------------------------------------------------
# weighted_pp e calculadora
# ---------------------------------------------------------------------------


def test_weighted_pp_known_case():
    assert weighted_pp([100, 50]) == pytest.approx(100 + 50 * WEIGHT_COEFFICIENT)
    assert weighted_pp([50, 100]) == pytest.approx(100 + 50 * WEIGHT_COEFFICIENT)
    assert weighted_pp([]) == 0.0
    assert weighted_pp([42]) == 42.0
    assert weighted_pp([10, 20, 30]) == pytest.approx(30 + 20 * 0.965 + 10 * 0.965**2)


def test_weighted_pp_order_independent_random():
    rng = random.Random(7)
    for _ in range(50):
        pps = [rng.uniform(0, 900) for _ in range(rng.randint(1, 25))]
        shuffled = pps.copy()
        rng.shuffle(shuffled)
        assert weighted_pp(shuffled) == pytest.approx(weighted_pp(pps), rel=1e-12)


def test_weighted_pp_matches_legacy_on_sorted_input():
    rng = random.Random(11)
    pps = sorted([rng.uniform(0, 700) for _ in range(40)], reverse=True)
    assert weighted_pp(pps) == pytest.approx(
        legacy.get_total_weighted_pp(list(pps)), abs=1e-9
    )


def test_calculator_plus_one_pp_matches_legacy():
    rng = random.Random(13)
    for _ in range(100):
        n = rng.randint(1, 30)
        scores = sorted([rng.uniform(10, 800) for _ in range(n)], reverse=True)
        expected_raw = legacy.calc_raw_pp_for_expected_pp(list(scores), 1)
        got = calc_raw_pp_for_expected_pp(scores, 1)
        assert got == pytest.approx(expected_raw, abs=1e-9)
        # O PP cru encontrado realmente rende ~+1pp quando inserido no topo.
        gain = legacy.get_raw_pp_for_weighted_pp_gain(list(scores), got)
        assert gain == pytest.approx(1.0, rel=1e-9)
        # Paridade também do ganho real.
        assert (
            get_raw_pp_for_weighted_pp_gain(scores, got)
            == pytest.approx(gain, abs=1e-12)
        )


def test_calculator_helpers_match_legacy():
    scores = [650.0, 540.2, 430.0, 320.7, 210.1]
    for idx in range(len(scores)):
        assert calc_raw_pp_at_idx(scores, idx, 1.0) == pytest.approx(
            legacy.calc_raw_pp_at_idx(list(scores), idx, 1), abs=1e-12
        )
    empty = raw_pp_for_expected_gain([], 1.0)
    assert empty == pytest.approx(legacy.calc_raw_pp_for_expected_pp([], 1))
    assert raw_pp_for_expected_gain([500.0]) == pytest.approx(
        legacy.calc_raw_pp_for_expected_pp([500.0]), abs=1e-12
    )


    sub = decompose_pp(8.5, 0.9788, 0.5, 0.3, 0.2)
def test_math_smoke():
    # Sanity: fórmulas coerentes entre si (não é golden, só smoke determinístico).
    sub = decompose_pp(8.5, 0.9788, 0.5, 0.3, 0.2)
    pp = get_pp(8.5, 0.9788)
    assert pp == pytest.approx(get_modifier(97.88) * 8.5 * STAR_MULTIPLIER)
    assert sum(sub[k] for k in ("pp_acc", "pp_tech", "pp_speed")) == pytest.approx(
        pp, abs=1e-9
    )
    assert not any(math.isnan(v) or math.isinf(v) for v in sub.values())
