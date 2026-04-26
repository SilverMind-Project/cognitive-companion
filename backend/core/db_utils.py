"""Database connection string utilities.

Provides parsing, validation, and serialization of PostgreSQL connection strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote


@dataclass
class PostgresConnectionParams:
    """Parsed PostgreSQL connection parameters."""

    host: str
    port: int
    user: str
    password: str
    database: str

    def __repr__(self) -> str:
        """String representation with masked password."""
        return (
            f"PostgresConnectionParams(host={self.host!r}, port={self.port}, "
            f"user={self.user!r}, password='***', database={self.database!r})"
        )


def parse_postgres_url(url: str) -> PostgresConnectionParams:
    """Parse a PostgreSQL connection URL.

    Supports formats:
    - postgresql://user:password@host:port/database
    - postgresql+psycopg://user:password@host:port/database

    Args:
        url: PostgreSQL connection URL

    Returns:
        Parsed connection parameters

    Raises:
        ValueError: If URL is invalid or missing required parameters
    """
    # Pattern to match PostgreSQL URLs — port is captured as any non-slash chars
    # so we can give a specific error for non-numeric ports
    pattern = r"^postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:/]+):([^/]+)/(.+)$"
    match = re.match(pattern, url)

    if not match:
        raise ValueError(
            "Invalid PostgreSQL URL format. Expected: "
            "postgresql://user:password@host:port/database"
        )

    user, password, host, port_str, database = match.groups()

    # URL decode components
    user = unquote(user)
    password = unquote(password)
    host = unquote(host)
    database = unquote(database)

    # Validate port
    try:
        port = int(port_str)
    except ValueError as err:
        raise ValueError(f"Invalid port number: {port_str}") from err

    if not (1 <= port <= 65535):
        raise ValueError(f"Port must be between 1 and 65535, got: {port}")

    # Validate required fields
    if not user:
        raise ValueError("User is required")
    if not password:
        raise ValueError("Password is required")
    if not host:
        raise ValueError("Host is required")
    if not database:
        raise ValueError("Database name is required")

    return PostgresConnectionParams(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )


def serialize_postgres_url(
    params: PostgresConnectionParams,
    dialect: str = "postgresql+psycopg",
) -> str:
    """Serialize connection parameters to a PostgreSQL URL.

    Args:
        params: Connection parameters
        dialect: SQLAlchemy dialect (default: postgresql+psycopg)

    Returns:
        PostgreSQL connection URL
    """
    # URL encode components that might contain special characters
    user = quote(params.user, safe="")
    password = quote(params.password, safe="")
    host = quote(params.host, safe="")
    database = quote(params.database, safe="")

    return f"{dialect}://{user}:{password}@{host}:{params.port}/{database}"


def mask_password(url: str) -> str:
    """Mask the password in a connection URL for safe logging.

    Args:
        url: PostgreSQL connection URL

    Returns:
        URL with password replaced by '***'
    """
    pattern = r"(postgresql(?:\+\w+)?://[^:]+:)([^@]+)(@.+)"
    return re.sub(pattern, r"\1***\3", url)


def validate_postgres_params(params: dict[str, Any]) -> list[str]:
    """Validate PostgreSQL connection parameters.

    Args:
        params: Dictionary of connection parameters

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check required parameters
    required = ["host", "port", "user", "password", "database"]
    for param in required:
        if param not in params or not params[param]:
            errors.append(f"Missing required parameter: {param}")

    # Validate port
    if "port" in params:
        try:
            port = int(params["port"])
            if not (1 <= port <= 65535):
                errors.append(f"Port must be between 1 and 65535, got: {port}")
        except (ValueError, TypeError):
            errors.append(f"Invalid port value: {params['port']}")

    # Validate host (basic check for valid characters)
    if params.get("host"):
        host = params["host"]
        # Allow alphanumeric, dots, hyphens, and underscores
        if not re.match(r"^[a-zA-Z0-9._-]+$", host):
            errors.append(f"Invalid host format: {host}")

    # Validate database name (basic check)
    if params.get("database"):
        database = params["database"]
        # PostgreSQL database names: alphanumeric, underscore, hyphen
        if not re.match(r"^[a-zA-Z0-9_-]+$", database):
            errors.append(f"Invalid database name format: {database}")

    return errors
