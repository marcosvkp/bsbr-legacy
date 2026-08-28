from enum import IntEnum

class NoteColor(IntEnum):
    RED = 0
    BLUE = 1
    BOMB = 3 # Bombas são tipo 3 no Beat Saber

class NoteCutDirection(IntEnum):
    UP = 0
    DOWN = 1
    LEFT = 2
    RIGHT = 3
    UP_LEFT = 4
    UP_RIGHT = 5
    DOWN_LEFT = 6
    DOWN_RIGHT = 7
    ANY = 8

class NoteLineIndex(IntEnum): # Coluna
    LEFT_MOST = 0
    LEFT = 1
    RIGHT = 2
    RIGHT_MOST = 3

class NoteLineLayer(IntEnum): # Linha
    BOTTOM = 0
    MIDDLE = 1
    TOP = 2

class EventType(IntEnum):
    # Eventos de Iluminação
    BACK_LIGHTS = 0
    RING_LIGHTS = 1
    LEFT_LASERS = 2
    RIGHT_LASERS = 3
    CENTER_LIGHTS = 4
    BOOST_COLOR = 5 # Cor de boost (V3)
    
    # Eventos de Rotação de Anéis
    RING_ROTATION = 8
    RING_ZOOM = 9

    # Eventos de BPM
    BPM_CHANGE = 10 # V2 e V3

    # Eventos de Cor de Luz
    LIGHT_COLOR = 12
    
    # Eventos de Rotação
    ROTATION_EVENT = 14 # V2 e V3
    
    # V3 Specific Events (do BeatLeader Parser) - Estes são mais complexos e podem não ser diretamente mapeáveis para um único IntEnum
    # LIGHT_COLOR_EVENT_BOX_GROUP = 40
    # LIGHT_ROTATION_EVENT_BOX_GROUP = 41
    # LIGHT_TRANSLATION_EVENT_BOX_GROUP = 42
    # BASIC_EVENT_TYPES_WITH_KEYWORDS = 43
