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
class Chain(BeatmapObject):
    """Linker (chain) V3 — squishy connector entre head e tail.

    ``tb`` é o beat do tail (relativo ao head em alguns formatos, absoluto
    em outros — o parser do BL usa ``TailInBeats``). ``sc`` = slice count,
    ``s`` = squish.
    """

    x: int = 0
    y: int = 0
    c: NoteColor = NoteColor.RED
    d: NoteCutDirection = NoteCutDirection.ANY
    a: int = 0
    tx: int = 0
    ty: int = 0
    tail_in_beats: float = 0.0
    slice_count: int = 8
    squish: float = 1.0

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> "Chain":
        return cls(
            b=float(data["b"]),
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            c=NoteColor(data.get("c", 0)),
            d=NoteCutDirection(data.get("d", 8)),
            a=int(data.get("a", 0)),
            tx=int(data.get("tx", 0)),
            ty=int(data.get("ty", 0)),
            tail_in_beats=float(data.get("tb", 0.0)),
            slice_count=int(data.get("sc", 8)),
            squish=float(data.get("s", 1.0)),
        )


@dataclass
class Arc(BeatmapObject):
    """Arc V3 — slider com multiplicador e anchor mode.

    Extende Chain com ``mu`` (multiplier), ``tmu`` (tail multiplier) e
    ``m`` (anchor mode: 0=Straight, 1=Clockwise, 2=CounterClockwise).
    """

    x: int = 0
    y: int = 0
    c: NoteColor = NoteColor.RED
    d: NoteCutDirection = NoteCutDirection.ANY
    a: int = 0
    tx: int = 0
    ty: int = 0
    tail_in_beats: float = 0.0
    multiplier: float = 1.0
    tail_multiplier: float = 1.0
    anchor_mode: int = 0

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> "Arc":
        return cls(
            b=float(data["b"]),
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            c=NoteColor(data.get("c", 0)),
            d=NoteCutDirection(data.get("d", 8)),
            a=int(data.get("a", 0)),
            tx=int(data.get("tx", 0)),
            ty=int(data.get("ty", 0)),
            tail_in_beats=float(data.get("tb", 0.0)),
            multiplier=float(data.get("mu", 1.0)),
            tail_multiplier=float(data.get("tmu", 1.0)),
            anchor_mode=int(data.get("m", 0)),
        )


@dataclass
class BpmEvent(BeatmapObject):
    """Evento de mudança de BPM (V3 ``bpmEvents``). ``m`` = novo BPM."""

    bpm: float = 0.0

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> "BpmEvent":
        return cls(
            b=float(data["b"]),
            bpm=float(data.get("m", 0.0)),
        )


@dataclass
class NjsEvent(BeatmapObject):
    """Evento de mudança de NJS (V3 ``njsEvents``).

    ``d`` = delta, ``p`` = usePrevious, ``e`` = easing.
    """

    delta: float = 0.0
    use_previous: int = 0
    easing: int = 0

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> "NjsEvent":
        return cls(
            b=float(data["b"]),
            delta=float(data.get("d", 0.0)),
            use_previous=int(data.get("p", 0)),
            easing=int(data.get("e", 0)),
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
