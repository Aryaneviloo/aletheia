"""
Alembic environment configuration.

wires in db.models and core.config so
`alembic revision --autogenerate` can actually compare our real
models against the real database and `alembic upgrade head` uses the
same Settings every other service reads from not a hardcoded URL
duplicated here
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from aletheia_core.config import get_settings
from aletheia_core.db.base import Base
from aletheia_core.db import models  # noqa: F401 — import registers every model onto Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", str(get_settings().database_url))


def run_migrations_offline() -> None:
    """
    Generate SQL without a live DB connection.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a real, live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # migrations are a one-shot operation — no need to pool connections
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()