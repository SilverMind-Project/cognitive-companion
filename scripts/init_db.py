#!/usr/bin/env python3
"""Database initialization script for PostgreSQL.

This script:
1. Creates the database if it doesn't exist
2. Runs Alembic migrations to create all tables
3. Seeds initial data from auth.yaml (rooms, sensors)

The script is idempotent and safe to run multiple times.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add backend to path so we can import modules
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir.parent))

import psycopg
import yaml
from alembic import command
from alembic.config import Config

from backend.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


def get_db_params() -> dict[str, str]:
    """Read database connection parameters from environment variables."""
    params = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "dbname": os.getenv("POSTGRES_DB", "cognitive-companion"),
    }
    
    if not params["user"]:
        logger.error("POSTGRES_USER environment variable is required")
        sys.exit(1)
    
    if not params["password"]:
        logger.error("POSTGRES_PASSWORD environment variable is required")
        sys.exit(1)
    
    return params


def create_database_if_not_exists(params: dict[str, str]) -> None:
    """Create the database if it doesn't exist.
    
    Connects to the 'postgres' database to create the target database.
    """
    admin_params = params.copy()
    admin_params["dbname"] = "postgres"
    
    try:
        logger.info(f"Connecting to PostgreSQL at {params['host']}:{params['port']}")
        with psycopg.connect(**admin_params) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Check if database exists
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (params["dbname"],)
                )
                exists = cur.fetchone()
                
                if exists:
                    logger.info(f"Database '{params['dbname']}' already exists")
                else:
                    logger.info(f"Creating database '{params['dbname']}'")
                    cur.execute(f'CREATE DATABASE "{params["dbname"]}"')
                    logger.info(f"Database '{params['dbname']}' created successfully")
    except psycopg.Error as e:
        logger.error(f"Failed to create database: {e}")
        sys.exit(1)


def run_migrations(params: dict[str, str]) -> None:
    """Run Alembic migrations to create all tables."""
    try:
        logger.info("Running Alembic migrations")
        
        # Construct database URL
        db_url = f"postgresql+psycopg://{params['user']}:{params['password']}@{params['host']}:{params['port']}/{params['dbname']}"
        
        # Configure Alembic
        alembic_ini = backend_dir / "alembic.ini"
        if not alembic_ini.exists():
            logger.error(f"Alembic config not found: {alembic_ini}")
            sys.exit(1)
        
        alembic_cfg = Config(str(alembic_ini))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations completed successfully")
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        sys.exit(1)


def seed_initial_data(params: dict[str, str]) -> None:
    """Seed initial data from auth.yaml (rooms, sensors)."""
    try:
        logger.info("Seeding initial data")
        
        # Load auth.yaml
        auth_yaml = backend_dir.parent / "config" / "auth.yaml"
        if not auth_yaml.exists():
            logger.warning(f"auth.yaml not found at {auth_yaml}, skipping seed data")
            return
        
        with open(auth_yaml) as f:
            auth_config = yaml.safe_load(f)
        
        # Connect to database
        db_url = f"host={params['host']} port={params['port']} dbname={params['dbname']} user={params['user']} password={params['password']}"
        
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                # Seed rooms
                rooms = auth_config.get("rooms", [])
                for room in rooms:
                    room_name = room.get("name")
                    if room_name:
                        cur.execute(
                            "INSERT INTO rooms (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                            (room_name,)
                        )
                        logger.info(f"Seeded room: {room_name}")
                
                # Seed sensors
                device_keys = auth_config.get("device_keys", {})
                for device_id, device_info in device_keys.items():
                    device_type = device_info.get("device_type", "unknown")
                    room_name = device_info.get("room")
                    
                    # Map device_type to sensor_type
                    sensor_type_map = {
                        "recamera": "camera",
                        "reterminal": "eink",
                    }
                    sensor_type = sensor_type_map.get(device_type, device_type)
                    
                    # Get room_id
                    if room_name:
                        cur.execute("SELECT id FROM rooms WHERE name = %s", (room_name,))
                        room_row = cur.fetchone()
                        room_id = room_row[0] if room_row else None
                    else:
                        room_id = None
                    
                    # Insert sensor
                    cur.execute(
                        """
                        INSERT INTO sensors (name, sensor_type, room_id, is_active)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (name) DO NOTHING
                        """,
                        (device_id, sensor_type, room_id, True)
                    )
                    logger.info(f"Seeded sensor: {device_id} ({sensor_type})")
                
                conn.commit()
                logger.info("Initial data seeded successfully")
    except Exception as e:
        logger.error(f"Failed to seed initial data: {e}")
        # Don't exit on seed failure, as migrations are more critical
        logger.warning("Continuing despite seed data failure")


def main() -> None:
    """Main entry point."""
    logger.info("Starting database initialization")
    
    # Get database parameters
    params = get_db_params()
    
    # Create database if it doesn't exist
    create_database_if_not_exists(params)
    
    # Run migrations
    run_migrations(params)
    
    # Seed initial data
    seed_initial_data(params)
    
    logger.info("Database initialization completed successfully")


if __name__ == "__main__":
    main()
