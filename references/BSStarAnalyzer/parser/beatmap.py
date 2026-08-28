from typing import List, Dict, Any

from .enums import NoteColor, NoteCutDirection
from .objects import Note, Obstacle, Event

class Beatmap:
    """
    Representa um mapa de Beat Saber completo (Difficulty).
    Contém listas de Notas, Obstáculos e Eventos normalizados.
    """
    def __init__(self, version: str = "2.0.0"):
        self.version = version
        self.notes: List[Note] = []
        self.obstacles: List[Obstacle] = []
        self.events: List[Event] = []
        self.bombs: List[Note] = [] # Separamos bombas de notas normais para facilitar

    def parse_json(self, data: Dict[str, Any]):
        """
        Lê um dicionário JSON (seja V2 ou V3) e popula as listas de objetos.
        Detecta automaticamente a versão baseada nas chaves presentes.
        """
        # Detecção de Versão
        if '_version' in data: # V2
            self.version = data['_version']
            self._parse_v2(data)
        elif 'version' in data: # V3
            self.version = data['version']
            self._parse_v3(data)
        else:
            raise ValueError("Formato de mapa desconhecido (nem V2 nem V3 detectado).")

    def _parse_v2(self, data: Dict[str, Any]):
        # Notas e Bombas
        for n in data.get('_notes', []):
            note = Note.from_v2_dict(n)
            if note.c == 3: # Bomba
                self.bombs.append(note)
            else:
                self.notes.append(note)
        
        # Obstáculos
        for o in data.get('_obstacles', []):
            self.obstacles.append(Obstacle.from_v2_dict(o))
            
        # Eventos
        """for e_dict in data.get('_events', []):
            try:
                self.events.append(Event.from_v2_dict(e_dict))
            except ValueError as e:
                # Ignora eventos com EventType desconhecido
                print(f"  Aviso: Ignorando evento V2 com tipo desconhecido: {e_dict.get('_type')}. Erro: {e}")"""

    def _parse_v3(self, data: Dict[str, Any]):
        # Notas (colorNotes)
        for n in data.get('colorNotes', []):
            self.notes.append(Note.from_v3_dict(n))
            
        # Bombas (bombNotes)
        for b in data.get('bombNotes', []):
            bomb = Note(
                b=b['b'],
                x=b['x'],
                y=b['y'],
                c=NoteColor.BOMB, # Cor 3 = Bomba
                d=NoteCutDirection.ANY, # Bombas não têm direção de corte
                a=0  # Bombas não têm ângulo
            )
            self.bombs.append(bomb)

        # Obstáculos (obstacles)
        for o in data.get('obstacles', []):
            self.obstacles.append(Obstacle.from_v3_dict(o))
            
        # Eventos (basicBeatmapEvents)
        """for e_dict in data.get('basicBeatmapEvents', []):
            try:
                self.events.append(Event.from_v3_dict(e_dict))
            except ValueError as e:
                # Ignora eventos com EventType desconhecido
                print(f"  Aviso: Ignorando evento V3 com tipo desconhecido: {e_dict.get('et')}. Erro: {e}")"""

        # TODO: Suportar Arcs (sliders) e Chains (burstSliders) do V3 se necessário
