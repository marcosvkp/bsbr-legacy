from dataclasses import dataclass
from typing import Any, Dict

from .base import BeatmapObject
from .enums import NoteColor, NoteCutDirection


@dataclass
class Note(BeatmapObject):
    """
    Representa uma nota ou bomba no Beat Saber.
    Normaliza V2 (_time, _lineIndex, _lineLayer, _type, _cutDirection)
    e V3 (b, x, y, c, d, a) para um formato unificado.
    """

    x: int = 0  # Coluna (lineIndex)
    y: int = 0  # Linha (lineLayer)
    c: NoteColor = NoteColor.RED  # Cor (type)
    d: NoteCutDirection = NoteCutDirection.ANY  # Direção de corte (cutDirection)
    a: int = 0  # Ângulo de rotação (angleOffset - apenas V3)

    @classmethod
    def from_v2_dict(cls, data: Dict[str, Any]) -> "Note":
        return cls(
            b=float(data["_time"]),
            x=int(data["_lineIndex"]),
            y=int(data["_lineLayer"]),
            c=NoteColor(data["_type"]),
            d=NoteCutDirection(data["_cutDirection"]),
            a=0,  # V2 não tem angleOffset
        )

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> "Note":
        return cls(
            b=float(data["b"]),
            x=int(data["x"]),
            y=int(data["y"]),
            c=NoteColor(data["c"]),
            d=NoteCutDirection(data["d"]),
            a=int(data.get("a", 0)),  # 'a' é opcional em V3
        )


@dataclass
class Obstacle(BeatmapObject):
    """
    Representa um obstáculo (parede) no Beat Saber.
    Normaliza V2 (_time, _lineIndex, _type, _duration, _width)
    e V3 (b, x, y, d, w, h) para um formato unificado.
    """

    x: int = 0  # Coluna (lineIndex)
    y: int = 0  # Linha (lineLayer - V3) / Tipo normalizado (V2)
    d: float = 0.0  # Duração em beats
    w: int = 0  # Largura
    h: int = 0  # Altura

    @classmethod
    def from_v2_dict(cls, data: Dict[str, Any]) -> "Obstacle":
        # V2 _type para obstáculos: 0 = parede inteira, 1 = parede de chão, 2 = parede de teto
        # Mapeamos para y e h do V3
        obstacle_type = data["_type"]
        if obstacle_type == 0:  # Parede inteira
            y, h = 0, 3
        elif obstacle_type == 1:  # Parede de chão
            y, h = 0, 2
        elif obstacle_type == 2:  # Parede de teto
            y, h = 2, 1
        else:  # Fallback
            y, h = 0, 3

        return cls(
            b=float(data["_time"]),
            x=int(data["_lineIndex"]),
            y=y,
            d=float(data["_duration"]),
            w=int(data["_width"]),
            h=h,
        )

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> "Obstacle":
        return cls(
            b=float(data["b"]),
            x=int(data["x"]),
            y=int(data["y"]),
            d=float(data["d"]),
            w=int(data["w"]),
            h=int(data.get("h", 0)),
        )
