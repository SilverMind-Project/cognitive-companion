"""
Demo script showing lock contention monitoring in action.

This script demonstrates how the lock monitoring system tracks
SELECT FOR UPDATE queries and logs waits exceeding 100ms.

Usage:
    python examples/lock_monitoring_demo.py
"""

from backend.core.database import (
    Database,
    get_lock_contention_metrics,
    reset_lock_contention_metrics,
)
from backend.core.logging import setup_logging


def main():
    """Demonstrate lock contention monitoring."""
    # Setup logging to see WARNING messages
    setup_logging(level="INFO")

    # Create a test database
    db = Database("sqlite:///./data/lock_demo.db")
    db.create_all()

    # Reset metrics
    reset_lock_contention_metrics()


    # Note: SQLite doesn't support SELECT FOR UPDATE, so this is a conceptual demo
    # In production with PostgreSQL, you would use actual FOR UPDATE queries


    # Show current metrics
    get_lock_contention_metrics()



    # Cleanup
    db.dispose()


if __name__ == "__main__":
    main()
