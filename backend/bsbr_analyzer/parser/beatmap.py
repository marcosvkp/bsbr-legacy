from typing import Any, Dict, List

from .enums import NoteColor, NoteCutDirection
from .objects import Note, Obstacle


def detect_version(data: Dict[str, Any]) -> str:
    """Detecta a versão do formato a partir das chaves presentes."""
    if "_version" in data:
        return str(data["_version"])
    if "version" in data:
        return str(data["version"])
    raise ValueError("Formato de mapa desconhecido (nem V2 nem V3 detectado).")


class Beatmap:
    """
    Representa um mapa de Beat Saber completo (Difficulty).
    Contém listas de Notas, Obstáculos e Bombas normalizadas.
    """

    def __init__(self, version: str = "2.0.0"):
        self.version = version
        self.notes: List[Note] = []
        self.obstacles: List[Obstacle] = []
        self.bombs: List[Note] = []  # Separamos bombas de notas normais

    def parse_json(self, data: Dict[str, Any]):
        """
        Lê um dicionário JSON (seja V2 ou V3) e popula as listas de objetos.
        Detecta automaticamente a versão baseada nas chaves presentes.
        """
        self.version = detect_version(data)
        if "_version" in data:
            self._parse_v2(data)
        else:
            self._parse_v3(data)

    def _parse_v2(self, data: Dict[str, Any]):
        for n in data.get("_notes", []):
            note = Note.from_v2_dict(n)
            if note.c == NoteColor.BOMB:
                self.bombs.append(note)
            else:
                self.notes.append(note)
        for o in data.get("_obstacles", []):
            self.obstacles.append(Obstacle.from_v2_dict(o))

    def _parse_v3(self, data: Dict[str, Any]):
        for n in data.get("colorNotes", []):
            self.notes.append(Note.from_v3_dict(n))
        for b in data.get("bombNotes", []):
            self.bombs.append(
                Note(
                    b=float(b["b"]),
                    x=int(b["x"]),
                    y=int(b["y"]),
                    c=NoteColor.BOMB,
                    d=NoteCutDirection.ANY,
                    a=0,
                )
            )
        for o in data.get("obstacles", []):
            self.obstacles.append(Obstacle.from_v3_dict(o))
