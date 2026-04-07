from __future__ import annotations

from typing import Final

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import get_settings
from core.paths import DATA_DIR, DEFAULT_TEMP_DIR
from core.utils import ensure_directories


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base."""



def _build_database_url() -> str:
    db_path = get_settings().db_path.resolve()
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


ENGINE = create_engine(_build_database_url(), echo=False)
SessionFactory: Final[sessionmaker] = sessionmaker(bind=ENGINE, autoflush=False, expire_on_commit=False)



def _import_models() -> None:
    import modules.customer.models  # noqa: F401
    import modules.inventory.models  # noqa: F401
    import modules.returns.models  # noqa: F401
    import modules.sales.models  # noqa: F401



def init_db() -> None:
    settings = get_settings()
    ensure_directories(
        [
            DATA_DIR,
            DEFAULT_TEMP_DIR,
            settings.export_dir,
            settings.backup_dir,
            settings.db_path.parent,
        ]
    )
    _import_models()
    Base.metadata.create_all(bind=ENGINE)
