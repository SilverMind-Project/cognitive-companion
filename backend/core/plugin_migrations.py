"""Config migration infrastructure for plugin evolution.

When a step, filter, or channel changes its config_schema shape, the author
adds a ConfigMigration entry to the handler's metadata. The import system runs
the migration chain to bring older configs up to the current schema_version.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigMigration:
    """A pure function that transforms config dicts from one version to the next.

    Each migration moves exactly one version step (e.g. v1 -> v2). Chains
    are built by composing multiple ConfigMigration entries.
    """

    from_version: int
    to_version: int
    description: str
    apply: Callable[[dict], dict]


def migrate_config(
    config: dict[str, Any],
    migrations: tuple[ConfigMigration, ...],
    from_version: int,
    to_version: int,
) -> dict[str, Any]:
    """Apply a migration chain to bring *config* from *from_version* to *to_version*.

    Args:
        config: The config dict to migrate (not mutated in place).
        migrations: All available migrations for this plugin.
        from_version: The version of the input config.
        to_version: The target (current) version.

    Returns:
        A new config dict at *to_version*.

    Raises:
        ValueError: If no migration path exists between the two versions.
    """
    if from_version == to_version:
        return dict(config)

    migration_map: dict[tuple[int, int], ConfigMigration] = {}
    for m in migrations:
        migration_map[(m.from_version, m.to_version)] = m

    result = dict(config)
    current = from_version
    while current < to_version:
        key = (current, current + 1)
        if key not in migration_map:
            raise ValueError(
                f"No migration from v{current} to v{current + 1}. "
                f"Available migrations: {sorted(migration_map.keys())}"
            )
        result = migration_map[key].apply(result)
        current += 1

    return result
