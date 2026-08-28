"""Enums de domínio usados pelos models do BSBR.

`native_enum=False` em todos: gera VARCHAR + CHECK constraint portável,
funcionando identicamente em SQLite (dev/testes) e PostgreSQL (produção).
"""

import enum

from sqlalchemy import Enum


class MapStatus(str, enum.Enum):
    """Ciclo de vida de um mapa no pool rankeado."""

    CANDIDATE = "candidate"
    QUALIFIED = "qualified"
    RANKED = "ranked"
    REMOVED = "removed"


class SuggestionStatus(str, enum.Enum):
    """Estado de uma sugestão de reweight pendente de revisão staff."""

    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class BatchKind(str, enum.Enum):
    """Origem de um batch de recálculo."""

    WEEKLY = "weekly"
    MANUAL = "manual"


def enum_column(enum_cls: type[enum.Enum], **kwargs: object) -> Enum:
    """Coluna Enum portável que persiste os valores lowercase (`value`)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=16,
        values_callable=lambda e: [m.value for m in e],
        **kwargs,
    )
