from globalroamer_platform.config import get_settings
from globalroamer_platform.infrastructure.database.base import Base
from globalroamer_platform.infrastructure.database import models

settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    settings.alembic_database_url,
)

target_metadata = Base.metadata
