from dataclasses import dataclass, field
from typing import List, Dict, Any
from .base import BeatmapObject
from .enums import NoteColor, NoteCutDirection, NoteLineIndex, NoteLineLayer, EventType

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
    def from_v2_dict(cls, data: Dict[str, Any]) -> 'Note':
        return cls(
            b=data['_time'],
            x=data['_lineIndex'],
            y=data['_lineLayer'],
            c=NoteColor(data['_type']),
            d=NoteCutDirection(data['_cutDirection']),
            a=0 # V2 não tem angleOffset
        )

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> 'Note':
        return cls(
            b=data['b'],
            x=data['x'],
            y=data['y'],
            c=NoteColor(data['c']),
            d=NoteCutDirection(data['d']),
            a=data.get('a', 0) # 'a' é opcional em V3
        )

@dataclass
class Obstacle(BeatmapObject):
    """
    Representa um obstáculo (parede) no Beat Saber.
    Normaliza V2 (_time, _lineIndex, _type, _duration, _width)
    e V3 (b, x, y, d, w, h) para um formato unificado.
    """
    x: int = 0  # Coluna (lineIndex)
    y: int = 0  # Linha (lineLayer - V3) / Tipo (V2)
    d: float = 0.0  # Duração em beats
    w: int = 0  # Largura
    h: int = 0  # Altura (apenas V3)

    @classmethod
    def from_v2_dict(cls, data: Dict[str, Any]) -> 'Obstacle':
        # V2 _type para obstáculos: 0 = parede inteira, 1 = parede de chão, 2 = parede de teto
        # Mapeamos para y e h do V3
        obstacle_type = data['_type']
        if obstacle_type == 0: # Parede inteira
            y = 0
            h = 3
        elif obstacle_type == 1: # Parede de chão
            y = 0
            h = 2
        elif obstacle_type == 2: # Parede de teto
            y = 2
            h = 1
        else: # Fallback
            y = 0
            h = 3

        return cls(
            b=data['_time'],
            x=data['_lineIndex'],
            y=y,
            d=data['_duration'],
            w=data['_width'],
            h=h
        )

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> 'Obstacle':
        return cls(
            b=data['b'],
            x=data['x'],
            y=data['y'],
            d=data['d'],
            w=data['w'],
            h=data['h']
        )

@dataclass
class Event(BeatmapObject):
    """
    Representa um evento de iluminação, rotação, BPM, etc.
    Normaliza V2 (_time, _type, _value)
    e V3 (b, et, i, f) para um formato unificado.
    """
    et: EventType = EventType.BACK_LIGHTS  # Tipo de evento (type)
    i: int = 0  # Valor inteiro (value)
    f: float = 0.0  # Valor float (apenas V3)

    @classmethod
    def from_v2_dict(cls, data: Dict[str, Any]) -> 'Event':
        return cls(
            b=data['_time'],
            et=EventType(data['_type']),
            i=data['_value'],
            f=0.0 # V2 não tem valor float
        )

    @classmethod
    def from_v3_dict(cls, data: Dict[str, Any]) -> 'Event':
        return cls(
            b=data['b'],
            et=EventType(data['et']),
            i=data['i'],
            f=data.get('f', 0.0) # 'f' é opcional em V3
        )

# Adicione outras classes de objetos se necessário (ex: Arc, Chain para V3)
# Por enquanto, focaremos nos objetos principais para o mapeamento.
