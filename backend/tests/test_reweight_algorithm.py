"""Testes do algoritmo de reweight (porta do player_performance.py).

Semântica do delta: delta = -(mediana_observada - esperada) × 100 × 0.25.
- Mapa FÁCIL demais (mediana acima da esperada) → delta negativo → NERF
  (joga como se tivesse menos estrelas; também corta o farm de PP).
- Mapa DURO demais (mediana abaixo da esperada) → delta positivo → BUFF.
"""

import pytest

from app.services.reweight import analyze_difficulty, expected_median_acc, extract_scores_from_leaderboard


def make_scores(n: int, acc: float, player_pp: float = 2000.0, base_score: float = 900_000):
    return [
        {"acc": acc, "base_score": base_score, "full_combo": acc > 0.9, "player_pp": player_pp}
        for _ in range(n)
    ]


def test_expected_curve_matches_legacy():
    assert expected_median_acc(5) == pytest.approx(0.905)
    assert expected_median_acc(14) == pytest.approx(0.78)  # piso (0.98 - 0.21 < 0.78)
    assert expected_median_acc(1) == pytest.approx(0.965)


def test_insufficient_sample_no_suggestion():
    result = analyze_difficulty(make_scores(5, 0.99), current_stars=5.0)
    assert result.sample_size == 5
    assert result.confidence == "none"
    assert result.delta_stars == 0.0
    assert not result.can_auto_apply


def test_too_easy_map_gets_nerfed():
    # esperada p/ 5★ é 90.5%; todos cravando 93% → joga como ~4.4★
    result = analyze_difficulty(make_scores(50, 0.93), current_stars=5.0)
    assert result.median_acc == pytest.approx(0.93, abs=1e-6)
    assert result.expected_acc == pytest.approx(0.905, abs=1e-6)
    assert result.direction == "decrease"
    assert result.delta_stars == pytest.approx(-0.63)  # -(0.93-0.905)*100*0.25, round 2 casas
    assert result.suggested_stars == pytest.approx(4.37)  # 5.00 - 0.63 (delta arredondado)


def test_too_hard_map_gets_buffed_with_clamp():
    # mediana 70% << esperada 90.5% → mapa muito mais duro que 5★
    result = analyze_difficulty(make_scores(60, 0.70), current_stars=5.0)
    assert result.direction == "increase"
    assert result.delta_stars == pytest.approx(2.0)  # clamp ±2★
    assert result.suggested_stars == pytest.approx(7.0)


def test_confidence_levels():
    low = analyze_difficulty(make_scores(15, 0.91), current_stars=5.0)
    mid = analyze_difficulty(make_scores(45, 0.91), current_stars=5.0)
    high = analyze_difficulty(make_scores(120, 0.91), current_stars=5.0)
    assert low.confidence == "low"
    assert mid.confidence == "medium"
    assert high.confidence == "high"


def test_auto_apply_requires_high_confidence_and_small_delta():
    # confiança alta e |delta| ≤ 1★ → auto-aplica
    ok = analyze_difficulty(make_scores(120, 0.91), current_stars=5.0)  # delta ≈ -0.13★
    assert ok.confidence == "high"
    assert abs(ok.delta_stars) <= 1.0
    assert ok.can_auto_apply

    # confiança alta mas |delta| > 1★ → revisão staff
    big = analyze_difficulty(make_scores(150, 0.80), current_stars=5.0)
    assert big.confidence == "high"
    assert abs(big.delta_stars) > 1.0
    assert not big.can_auto_apply

    # delta pequeno mas confiança baixa → revisão staff
    shy = analyze_difficulty(make_scores(15, 0.911), current_stars=5.0)
    assert shy.confidence == "low"
    assert not shy.can_auto_apply


def test_filters_casuals_and_impossible_scores():
    scores = make_scores(20, 0.95, player_pp=100)  # abaixo do filtro de PP
    scores += [{"acc": 1.3, "base_score": 999_999, "full_combo": True, "player_pp": 5000} for _ in range(5)]
    result = analyze_difficulty(scores, current_stars=5.0)
    assert result.sample_size == 0
    assert result.confidence == "none"


def test_min_player_pp_none_accepts_global_scores():
    """A chamada padrão filtra player_pp=0; min_player_pp=None aceita os
    scores globais (o payload do ScoreSaber não entrega PP confiável)."""
    scores = make_scores(45, 0.95, player_pp=0)

    filtered = analyze_difficulty(scores, current_stars=5.0)
    assert filtered.sample_size == 0
    assert filtered.confidence == "none"

    accepted = analyze_difficulty(scores, current_stars=5.0, min_player_pp=None)
    assert accepted.sample_size == 45
    assert accepted.confidence == "medium"  # 45 >= MEDIUM_MIN=40
    # -(0.95 - 0.905) * 100 * 0.25 = -1.125 → round 2 casas
    assert accepted.delta_stars == pytest.approx(-1.12)


def test_weighted_acc_privileges_top_ranks():
    scores = [{"acc": 0.99, "base_score": 1, "full_combo": True, "player_pp": 3000}] * 10
    scores += [{"acc": 0.80, "base_score": 1, "full_combo": False, "player_pp": 3000}] * 30
    result = analyze_difficulty(scores, current_stars=8.0)
    assert result.weighted_acc is not None
    # ponderada > média simples (79.75%) porque os bons ranks pesam mais
    assert result.weighted_acc > 0.7975


def test_extract_from_scoresaber_payload():
    payload = [
        {
            "baseScore": 800000,
            "maxScore": 1000000,
            "fullCombo": True,
            "leaderboardPlayerInfo": {"pp": 5500},
        }
    ]
    extracted = extract_scores_from_leaderboard(payload)[0]
    assert extracted["acc"] == pytest.approx(0.8)
    assert extracted["player_pp"] == 5500
    assert extracted["full_combo"] is True
