import os
import re
import sys
from logging.config import fileConfig
from pathlib import Path

# Ensure the parent of backend/ is in sys.path so we can import backend.* modules
# env.py is at backend/alembic/env.py, so parent.parent.parent gives us cognitive-companion/
workspace_root = Path(__file__).resolve().parent.parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))


def _load_dotenv(path: Path) -> None:
    """Load repo .env values for local Alembic CLI runs.

    Docker injects these variables through compose, but direct `alembic`
    commands do not. Existing process environment wins so deployment overrides
    are preserved.
    """
    if not path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        _load_dotenv_fallback(path)
        return

    load_dotenv(path, override=False)


def _load_dotenv_fallback(path: Path) -> None:
    env_ref = re.compile(r"\$\{([^}]+)\}")

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if key in os.environ:
            continue
        value = raw_value.strip().strip("\"'")
        os.environ[key] = env_ref.sub(lambda match: os.environ.get(match.group(1), ""), value)


_load_dotenv(workspace_root / ".env")

import sqlalchemy as sa  # noqa: E402
from alembic.ddl.impl import DefaultImpl  # noqa: E402
from sqlalchemy import engine_from_config, pool  # noqa: E402

import backend.models  # noqa: E402, F401
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

_IGNORED_TABLES = {"spatial_ref_sys"}


def _include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Exclude extension-owned tables from autogenerate drift checks."""
    return not (type_ == "table" and name in _IGNORED_TABLES)


# -- Revision id length -------------------------------------------------------
# Alembic hardcodes ``Column("version_num", String(32))`` in
# ``alembic.ddl.impl.DefaultImpl.version_table_impl``. A revision id longer than
# 32 characters passes file generation and graph resolution, then fails at apply
# time when Alembic writes the head, and transactional DDL rolls the whole
# migration back. ``version_table_impl`` is a documented override hook (added
# in Alembic 1.14), so widen the column there.
VERSION_NUM_LENGTH = 128

_original_version_table_impl = DefaultImpl.version_table_impl


def _wide_version_table_impl(self, **kw):
    """Return alembic's version table with a wider ``version_num`` column."""
    table = _original_version_table_impl(self, **kw)
    table.c.version_num.type = sa.String(VERSION_NUM_LENGTH)
    return table


DefaultImpl.version_table_impl = _wide_version_table_impl


def _widen_existing_version_table(connection) -> None:
    """Widen ``version_num`` on databases created before the override landed.

    The override only affects table *creation*; a database whose
    ``alembic_version`` already exists keeps ``varchar(32)`` until altered.
    No-op when the table is absent (fresh database) or already wide enough.

    Online mode only. ``alembic upgrade --sql`` emits SQL without connecting, so
    an offline script does not carry this ALTER; widen such databases by hand.
    """
    current_length = connection.exec_driver_sql(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_name = 'alembic_version' AND column_name = 'version_num'"
    ).scalar()
    if current_length is None or current_length >= VERSION_NUM_LENGTH:
        return
    connection.exec_driver_sql(
        f"ALTER TABLE alembic_version ALTER COLUMN version_num "
        f"TYPE VARCHAR({VERSION_NUM_LENGTH})"
    )


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
        include_object=_include_object,
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

    # Widen on a separate connection that we commit ourselves. Issuing any
    # statement on the migration connection before context.configure() starts a
    # transaction Alembic does not own, and it then silently declines to commit
    # the migration.
    with connectable.connect() as connection:
        _widen_existing_version_table(connection)
        connection.commit()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
