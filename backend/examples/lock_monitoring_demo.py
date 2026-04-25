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

    print("Lock Contention Monitoring Demo")
    print("=" * 50)
    print()

    # Note: SQLite doesn't support SELECT FOR UPDATE, so this is a conceptual demo
    # In production with PostgreSQL, you would use actual FOR UPDATE queries

    print("In production with PostgreSQL, the monitoring will:")
    print("1. Track all SELECT FOR UPDATE queries")
    print("2. Measure lock wait times")
    print("3. Log waits exceeding 100ms at WARNING level")
    print("4. Maintain metrics for monitoring dashboards")
    print()

    # Show current metrics
    metrics = get_lock_contention_metrics()
    print("Current Lock Contention Metrics:")
    print(f"  Total lock waits: {metrics['total_lock_waits']}")
    print(f"  Total wait time: {metrics['total_wait_time_ms']:.2f} ms")
    print(f"  Max wait time: {metrics['max_wait_time_ms']:.2f} ms")
    print(f"  Average wait time: {metrics['avg_wait_time_ms']:.2f} ms")
    print(f"  Waits over 100ms: {metrics['waits_over_100ms']}")
    print()

    print("Example PostgreSQL query that would be monitored:")
    print("  SELECT * FROM workflow_executions")
    print("  WHERE id = 123")
    print("  FOR UPDATE;")
    print()

    print("If this query takes 150ms, you would see:")
    print("  WARNING lock_wait wait_time_ms=150.0 statement=SELECT * FROM...")
    print()

    # Cleanup
    db.dispose()
    print("Demo complete!")


if __name__ == "__main__":
    main()
