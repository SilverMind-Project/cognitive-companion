"""Tests for database connection string utilities."""

from __future__ import annotations

import pytest

from backend.core.db_utils import (
    PostgresConnectionParams,
    mask_password,
    parse_postgres_url,
    serialize_postgres_url,
    validate_postgres_params,
)


class TestParsePostgresUrl:
    """Tests for parse_postgres_url function."""

    def test_parses_basic_url(self) -> None:
        """Test parsing a basic PostgreSQL URL."""
        url = "postgresql://user:pass@localhost:5432/mydb"
        params = parse_postgres_url(url)

        assert params.user == "user"
        assert params.password == "pass"
        assert params.host == "localhost"
        assert params.port == 5432
        assert params.database == "mydb"

    def test_parses_url_with_dialect(self) -> None:
        """Test parsing URL with SQLAlchemy dialect."""
        url = "postgresql+psycopg://user:pass@localhost:5432/mydb"
        params = parse_postgres_url(url)

        assert params.user == "user"
        assert params.password == "pass"

    def test_parses_url_with_special_characters(self) -> None:
        """Test parsing URL with URL-encoded special characters."""
        url = "postgresql://user:p%40ss%21@localhost:5432/my-db"
        params = parse_postgres_url(url)

        assert params.password == "p@ss!"
        assert params.database == "my-db"

    def test_rejects_invalid_url_format(self) -> None:
        """Test that invalid URL format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid PostgreSQL URL format"):
            parse_postgres_url("not-a-valid-url")

    def test_rejects_invalid_port(self) -> None:
        """Test that invalid port raises ValueError."""
        with pytest.raises(ValueError, match="Invalid port number"):
            parse_postgres_url("postgresql://user:pass@localhost:abc/mydb")

    def test_rejects_port_out_of_range(self) -> None:
        """Test that port out of range raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between"):
            parse_postgres_url("postgresql://user:pass@localhost:99999/mydb")


class TestSerializePostgresUrl:
    """Tests for serialize_postgres_url function."""

    def test_serializes_basic_params(self) -> None:
        """Test serializing basic connection parameters."""
        params = PostgresConnectionParams(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="mydb",
        )
        url = serialize_postgres_url(params)

        assert url == "postgresql+psycopg://user:pass@localhost:5432/mydb"

    def test_serializes_with_custom_dialect(self) -> None:
        """Test serializing with custom dialect."""
        params = PostgresConnectionParams(
            host="localhost",
            port=5432,
            user="user",
            password="pass",
            database="mydb",
        )
        url = serialize_postgres_url(params, dialect="postgresql")

        assert url == "postgresql://user:pass@localhost:5432/mydb"

    def test_url_encodes_special_characters(self) -> None:
        """Test that special characters are URL-encoded."""
        params = PostgresConnectionParams(
            host="localhost",
            port=5432,
            user="user",
            password="p@ss!",
            database="my-db",
        )
        url = serialize_postgres_url(params)

        assert "p%40ss%21" in url  # @ and ! are encoded


class TestRoundTripConsistency:
    """Property tests for round-trip consistency."""

    def test_round_trip_preserves_values(self) -> None:
        """Test that parsing then serializing produces equivalent URL.
        
        This validates requirement 19.5: round-trip consistency.
        """
        original_url = "postgresql+psycopg://testuser:testpass@dbhost:5432/testdb"

        # Parse the URL
        params = parse_postgres_url(original_url)

        # Serialize back to URL
        reconstructed_url = serialize_postgres_url(params)

        # Parse again to compare values
        reconstructed_params = parse_postgres_url(reconstructed_url)

        # Values should be identical
        assert params.user == reconstructed_params.user
        assert params.password == reconstructed_params.password
        assert params.host == reconstructed_params.host
        assert params.port == reconstructed_params.port
        assert params.database == reconstructed_params.database

    def test_round_trip_with_special_characters(self) -> None:
        """Test round-trip with special characters in password."""
        original_url = "postgresql://user:p%40ss%21%23@localhost:5432/mydb"

        params = parse_postgres_url(original_url)
        reconstructed_url = serialize_postgres_url(params, dialect="postgresql")
        reconstructed_params = parse_postgres_url(reconstructed_url)

        # Password should be preserved
        assert params.password == reconstructed_params.password
        assert params.password == "p@ss!#"


class TestMaskPassword:
    """Tests for mask_password function."""

    def test_masks_password_in_url(self) -> None:
        """Test that password is masked in URL."""
        url = "postgresql://user:secretpass@localhost:5432/mydb"
        masked = mask_password(url)

        assert "secretpass" not in masked
        assert "***" in masked
        assert "user" in masked
        assert "localhost" in masked

    def test_masks_password_with_dialect(self) -> None:
        """Test masking with SQLAlchemy dialect."""
        url = "postgresql+psycopg://user:secretpass@localhost:5432/mydb"
        masked = mask_password(url)

        assert "secretpass" not in masked
        assert "***" in masked


class TestValidatePostgresParams:
    """Tests for validate_postgres_params function."""

    def test_validates_complete_params(self) -> None:
        """Test that complete valid params pass validation."""
        params = {
            "host": "localhost",
            "port": 5432,
            "user": "user",
            "password": "pass",
            "database": "mydb",
        }
        errors = validate_postgres_params(params)

        assert errors == []

    def test_detects_missing_required_params(self) -> None:
        """Test that missing required params are detected."""
        params = {
            "host": "localhost",
            "port": 5432,
        }
        errors = validate_postgres_params(params)

        assert len(errors) == 3  # Missing user, password, database
        assert any("user" in err for err in errors)
        assert any("password" in err for err in errors)
        assert any("database" in err for err in errors)

    def test_detects_invalid_port(self) -> None:
        """Test that invalid port is detected."""
        params = {
            "host": "localhost",
            "port": "not-a-number",
            "user": "user",
            "password": "pass",
            "database": "mydb",
        }
        errors = validate_postgres_params(params)

        assert len(errors) == 1
        assert "port" in errors[0].lower()

    def test_detects_port_out_of_range(self) -> None:
        """Test that port out of range is detected."""
        params = {
            "host": "localhost",
            "port": 99999,
            "user": "user",
            "password": "pass",
            "database": "mydb",
        }
        errors = validate_postgres_params(params)

        assert len(errors) == 1
        assert "port" in errors[0].lower()

    def test_detects_invalid_host_format(self) -> None:
        """Test that invalid host format is detected."""
        params = {
            "host": "host with spaces",
            "port": 5432,
            "user": "user",
            "password": "pass",
            "database": "mydb",
        }
        errors = validate_postgres_params(params)

        assert len(errors) == 1
        assert "host" in errors[0].lower()

    def test_detects_invalid_database_name(self) -> None:
        """Test that invalid database name is detected."""
        params = {
            "host": "localhost",
            "port": 5432,
            "user": "user",
            "password": "pass",
            "database": "db with spaces",
        }
        errors = validate_postgres_params(params)

        assert len(errors) == 1
        assert "database" in errors[0].lower()
