from typing import Any, Dict, List

from .enums import NoteColor, NoteCutDirection
from .objects import Arc, BpmEvent, Chain, NjsEvent, Note, Obstacle


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
        self.chains: List[Chain] = []
        self.arcs: List[Arc] = []
        self.bpm_events: List[BpmEvent] = []
        self.njs_events: List[NjsEvent] = []

    def parse_json(self, data: Dict[str, Any]):
        """
        Lê um dicionário JSON (seja V2, V3 ou V4.1) e popula as listas de objetos.
        Detecta automaticamente a versão baseada nas chaves presentes.
        """
        self.version = detect_version(data)
        if "_version" in data:
            self._parse_v2(data)
        elif "colorNotesData" in data or str(data.get("version", "")).startswith("4"):
            self._parse_v41(data)
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
        # V3: sliders = arcs, burstSliders = chains (nomenclatura do BL parser)
        for ar in data.get("sliders", []):
            self.arcs.append(Arc.from_v3_dict(ar))
        for ch in data.get("burstSliders", []):
            self.chains.append(Chain.from_v3_dict(ch))
        for be in data.get("bpmEvents", []):
            self.bpm_events.append(BpmEvent.from_v3_dict(be))
        for ne in data.get("njsEvents", []):
            self.njs_events.append(NjsEvent.from_v3_dict(ne))

    def _parse_v41(self, data: Dict[str, Any]):
        """
        Formato 4.1.0 (Beat Saber 1.40+): tempo e "data" em arrays paralelos.

        ``colorNotes[i]`` guarda só o beat (``b``) e opcionalmente um índice
        ``i`` que aponta para ``colorNotesData[i]`` — um *delta* parcial
        (x/y/c/d/a) que se acumula sobre o estado anterior. Notas sem ``i``
        mantêm o estado corrente. O item ``colorNotesData[0]`` é o estado
        base (nenhuma nota referencia o índice 0). O mesmo vale para
        ``bombNotesData`` e ``obstaclesData``.
        """

        def apply_delta(state: Dict[str, Any], delta: Dict[str, Any]) -> None:
            for key, value in (delta or {}).items():
                if key in state:
                    state[key] = value

        def base_state(data_arr: List[Dict[str, Any]], defaults: Dict[str, Any]) -> Dict[str, Any]:
            state = dict(defaults)
            if data_arr:
                for key, value in (data_arr[0] or {}).items():
                    if key in state:
                        state[key] = value
            return state

        # Notas (vermelhas/azuis)
        color_data = data.get("colorNotesData") or []
        state = base_state(color_data, {"x": 0, "y": 0, "c": 0, "d": 0, "a": 0})
        for n in data.get("colorNotes", []):
            i = n.get("i")
            if i is not None and i < len(color_data):
                apply_delta(state, color_data[i])
            note = Note(
                b=float(n["b"]),
                x=int(state["x"]),
                y=int(state["y"]),
                c=NoteColor(state["c"]),
                d=NoteCutDirection(state["d"]),
                a=int(state.get("a", 0)),
            )
            if note.c == NoteColor.BOMB:
                self.bombs.append(note)
            else:
                self.notes.append(note)

        # Bombas
        bomb_data = data.get("bombNotesData") or []
        state = base_state(bomb_data, {"x": 0, "y": 0})
        for b in data.get("bombNotes", []):
            i = b.get("i")
            if i is not None and i < len(bomb_data):
                apply_delta(state, bomb_data[i])
            self.bombs.append(
                Note(
                    b=float(b["b"]),
                    x=int(state["x"]),
                    y=int(state["y"]),
                    c=NoteColor.BOMB,
                    d=NoteCutDirection.ANY,
                    a=0,
                )
            )

        # Obstáculos
        obstacle_data = data.get("obstaclesData") or []
        state = base_state(obstacle_data, {"x": 0, "y": 0, "d": 0.0, "w": 0, "h": 0})
        for o in data.get("obstacles", []):
            i = o.get("i")
            if i is not None and i < len(obstacle_data):
                apply_delta(state, obstacle_data[i])
            self.obstacles.append(
                Obstacle(
                    b=float(o["b"]),
                    x=int(state["x"]),
                    y=int(state["y"]),
                    d=float(state["d"]),
                    w=int(state["w"]),
                    h=int(state["h"]),
                )
            )

        # Chains (V4.1 — delta em chainsData)
        chain_data = data.get("chainsData") or []
        state = base_state(
            chain_data,
            {"x": 0, "y": 0, "c": 0, "d": 0, "a": 0, "tx": 0, "ty": 0, "tb": 0.0, "sc": 8, "s": 1.0},
        )
        for ch in data.get("chains", []):
            i = ch.get("i")
            if i is not None and i < len(chain_data):
                apply_delta(state, chain_data[i])
            self.chains.append(
                Chain(
                    b=float(ch["b"]),
                    x=int(state["x"]),
                    y=int(state["y"]),
                    c=NoteColor(state["c"]),
                    d=NoteCutDirection(state["d"]),
                    a=int(state.get("a", 0)),
                    tx=int(state.get("tx", 0)),
                    ty=int(state.get("ty", 0)),
                    tail_in_beats=float(state.get("tb", 0.0)),
                    slice_count=int(state.get("sc", 8)),
                    squish=float(state.get("s", 1.0)),
                )
            )

        # Arcs (V4.1 — delta em arcsData)
        arc_data = data.get("arcsData") or []
        state = base_state(
            arc_data,
            {"x": 0, "y": 0, "c": 0, "d": 0, "a": 0, "tx": 0, "ty": 0, "tb": 0.0, "mu": 1.0, "tmu": 1.0, "m": 0},
        )
        for ar in data.get("arcs", []):
            i = ar.get("i")
            if i is not None and i < len(arc_data):
                apply_delta(state, arc_data[i])
            self.arcs.append(
                Arc(
                    b=float(ar["b"]),
                    x=int(state["x"]),
                    y=int(state["y"]),
                    c=NoteColor(state["c"]),
                    d=NoteCutDirection(state["d"]),
                    a=int(state.get("a", 0)),
                    tx=int(state.get("tx", 0)),
                    ty=int(state.get("ty", 0)),
                    tail_in_beats=float(state.get("tb", 0.0)),
                    multiplier=float(state.get("mu", 1.0)),
                    tail_multiplier=float(state.get("tmu", 1.0)),
                    anchor_mode=int(state.get("m", 0)),
                )
            )
