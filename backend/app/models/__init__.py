"""Models do BSBR — reexportados para import único (`from app import models`).

Importar este pacote registra todos os mappers em `Base.metadata`
(necessário para Alembic autogenerate e `create_all`).
"""

from app.core.db import Base

# Convenção de nomes de constraints: essencial para o Alembic conseguir
# alterar/derrubar constraints de forma determinística no PostgreSQL.
Base.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

from app.models.batch import Batch  # noqa: E402
from app.models.difficulty import Difficulty  # noqa: E402
from app.models.enums import BatchKind, MapStatus, SuggestionStatus  # noqa: E402,F401
from app.models.map import Map  # noqa: E402
from app.models.player import Player  # noqa: E402
from app.models.rank_snapshot import RankSnapshot  # noqa: E402
from app.models.rating_history import RatingHistory  # noqa: E402
from app.models.reweight_suggestion import ReweightSuggestion  # noqa: E402
from app.models.score import Score  # noqa: E402
from app.models.staff_user import StaffUser  # noqa: E402

__all__ = [
    "Base",
    "Batch",
    "BatchKind",
    "Difficulty",
    "Map",
    "MapStatus",
    "Player",
    "RankSnapshot",
    "RatingHistory",
    "ReweightSuggestion",
    "Score",
    "StaffUser",
    "SuggestionStatus",
]
