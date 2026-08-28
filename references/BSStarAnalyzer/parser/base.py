from dataclasses import dataclass

@dataclass
class BeatmapObject:
    """
    Classe base para todos os objetos do mapa.
    
    Atributos:
        b (float): Tempo em batidas (beats).
    """
    b: float = 0.0

    def __lt__(self, other):
        return self.b < other.b
