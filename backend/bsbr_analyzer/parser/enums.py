from enum import IntEnum


class NoteColor(IntEnum):
    RED = 0
    BLUE = 1
    BOMB = 3  # Bombas são tipo 3 no Beat Saber


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


class NoteLineIndex(IntEnum):  # Coluna
    LEFT_MOST = 0
    LEFT = 1
    RIGHT = 2
    RIGHT_MOST = 3


class NoteLineLayer(IntEnum):  # Linha
    BOTTOM = 0
    MIDDLE = 1
    TOP = 2
