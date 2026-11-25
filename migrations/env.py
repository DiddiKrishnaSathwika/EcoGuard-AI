from alembic import context

from api.database import create_engine_for_url, metadata
from config import DATABASE_URL


target_metadata = metadata


def _require_database_url():
    if not DATABASE_URL:
        raise RuntimeError(
            "Set DATABASE_URL to the PostgreSQL database before running Alembic."
        )


def run_migrations_offline():
    raise RuntimeError(
        "Offline migrations are disabled; connect to the target PostgreSQL database."
    )


def run_migrations_online():
    _require_database_url()
    engine = create_engine_for_url(DATABASE_URL)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
