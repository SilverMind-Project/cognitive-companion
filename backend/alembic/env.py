import sys
from logging.config import fileConfig
from pathlib import Path

# Ensure the parent of backend/ is in sys.path so we can import backend.* modules
# env.py is at backend/alembic/env.py, so parent.parent.parent gives us cognitive-companion/
workspace_root = Path(__file__).resolve().parent.parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from sqlalchemy import engine_from_config, pool  # noqa: E402

import backend.models  # noqa: E402 F401
from alembic import context  # noqa: E402

# Import settings to read database URL
from backend.core.config import settings  # noqa: E402

# Import Base and all models so Base.metadata is populated
from backend.core.database import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the database URL.
# - If set explicitly (e.g. via _run_alembic_migrations), use it as-is.
# - Otherwise fall back to settings.yaml.
# Both the main option (used by run_migrations_offline) and the section
# option (used by engine_from_config in run_migrations_online) are kept
# in sync so that both modes see the same URL.
url = config.get_main_option("sqlalchemy.url")
if not url:
    url = settings.as_str("database.url")
    config.set_main_option("sqlalchemy.url", url)
config.set_section_option(config.config_ini_section, "sqlalchemy.url", url)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

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
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
