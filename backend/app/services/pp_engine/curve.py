"""Curva de PP do BSBR (porte exato do legado).

Fonte da verdade: ``references/bsbr/app/scorecalc/__init__.py``.

O multiplicador de acurácia é piecewise-linear sobre 36 pontos de calibração
(``_CURVE_POINTS``): em acc = 0.95 o multiplicador é exatamente 1.0 (ponto de
calibração) e cresce de forma explosiva perto de 1.00 (até ~5.3674).
"""

from __future__ import annotations

STAR_MULTIPLIER = 42.117208413

#: Coeficiente de decaimento da agregação ponderada do jogador.
WEIGHT_COEFFICIENT = 0.965

CALIBRATION_ACC = 0.95


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# (acc_fraction, multiplier) — 36 pontos de segmento, idênticos ao legado.
_CURVE_POINTS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (0.6, 0.18223233667439062),
    (0.65, 0.5866010012767576),
    (0.7, 0.6125565959114954),
    (0.75, 0.6451808210101443),
    (0.8, 0.6872268862950283),
    (0.825, 0.7150465663454271),
    (0.85, 0.7462290664143185),
    (0.875, 0.7816934560296046),
    (0.9, 0.825756123560842),
    (0.91, 0.8488375988124467),
    (0.92, 0.8728710341448851),
    (0.93, 0.9039994071865736),
    (0.94, 0.9417362980580238),
    (0.95, 1.0),
    (0.955, 1.0388633331418984),
    (0.96, 1.0871883573850478),
    (0.965, 1.1552120359501035),
    (0.97, 1.2485807759957321),
    (0.9725, 1.3090333065057616),
    (0.975, 1.3807102743105126),
    (0.9775, 1.4664726399289512),
    (0.98, 1.5702410055532239),
    (0.9825, 1.697536248647543),
    (0.985, 1.8563887693647105),
    (0.9875, 2.058947159052738),
    (0.99, 2.324506282149922),
    (0.99125, 2.4902905794106913),
    (0.9925, 2.685667856592722),
    (0.99375, 2.9190155639254955),
    (0.995, 3.2022017597337955),
    (0.99625, 3.5526145337555373),
    (0.9975, 3.996793606763322),
    (0.99825, 4.325027383589547),
    (0.999, 4.715470646416203),
    (0.9995, 5.019543595874787),
    (1.0, 5.367394282890631),
)


def get_modifier(acc_fraction: float) -> float:
    """Multiplicador de PP — porte EXATO do ``get_modifier`` do legado.

    Como o legado, recebe a acurácia em percentual 0..100 (clamp + divisão
    por 100 internos). Comportamento idêntico:
    - normalizada <= 0 -> 0.0;
    - normalizada >= 1 -> último multiplicador da curva (5.367394282890631);
    - caso contrário, interpolação linear entre os dois pontos que contêm acc.

    ATENÇÃO: por causa da divisão por 100 do legado, um valor 0..1 cai no
    primeiro segmento da curva — para consultar a curva por fração use
    ``curve_calibration`` ou multiplique por 100 antes de chamar.
    """
    accuracy = _clamp(acc_fraction, 0, 100) / 100

    if accuracy <= 0:
        return 0

    if accuracy >= 1:
        return _CURVE_POINTS[-1][1]

    for i in range(len(_CURVE_POINTS) - 1):
        acc_a, mult_a = _CURVE_POINTS[i]
        acc_b, mult_b = _CURVE_POINTS[i + 1]

        if acc_a <= accuracy <= acc_b:
            t = (accuracy - acc_a) / (acc_b - acc_a)
            return _lerp(mult_a, mult_b, t)
    return 0


def curve_calibration(acc_fraction: float) -> float:
    """g_acc normalizada: mod(acc) / mod(0.95).

    ``acc_fraction`` é a fração 0..1; como o legado divide a acurácia por 100
    antes de aplicar a curva, aqui convertemos de volta para percentual antes
    de consultar a tabela — assim acc = 0.95 cai exatamente no ponto de
    calibração da curva (multiplicador 1.0) e a razão vale 1.
    """
    return get_modifier(acc_fraction * 100) / get_modifier(CALIBRATION_ACC * 100)


__all__ = [
    "STAR_MULTIPLIER",
    "CALIBRATION_ACC",
    "get_modifier",
    "curve_calibration",
    "WEIGHT_COEFFICIENT",
]
