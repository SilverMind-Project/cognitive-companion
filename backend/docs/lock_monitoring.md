# Lock Contention Monitoring

## Overview

The lock contention monitoring system tracks and logs database lock wait times for `SELECT FOR UPDATE` queries. This helps identify performance bottlenecks and contention issues in concurrent database operations.

## Features

### 1. Automatic Lock Detection
- SQLAlchemy event listeners automatically detect `FOR UPDATE` queries
- No code changes required in application logic
- Works with both optimistic and pessimistic locking strategies

### 2. Wait Time Tracking
- Measures elapsed time for each lock acquisition
- Tracks cumulative statistics across all queries
- Identifies maximum wait times

### 3. Warning Logging
- Logs lock waits exceeding 100ms at WARNING level
- Includes wait time and truncated SQL statement
- Helps identify slow queries in production

### 4. Metrics Collection
- `total_lock_waits`: Total number of FOR UPDATE queries
- `total_wait_time_ms`: Cumulative wait time in milliseconds
- `max_wait_time_ms`: Maximum single wait time
- `waits_over_100ms`: Count of waits exceeding threshold
- `avg_wait_time_ms`: Average wait time (computed)

## Usage

### Accessing Metrics

```python
from backend.core.database import get_lock_contention_metrics

# Get current metrics
metrics = get_lock_contention_metrics()
print(f"Total lock waits: {metrics['total_lock_waits']}")
print(f"Average wait time: {metrics['avg_wait_time_ms']:.2f} ms")
print(f"Waits over 100ms: {metrics['waits_over_100ms']}")
```

### Resetting Metrics

```python
from backend.core.database import reset_lock_contention_metrics

# Reset all metrics to zero
reset_lock_contention_metrics()
```

### Example Log Output

When a lock wait exceeds 100ms, you'll see:

```
2025-01-15 10:23:45 [WARNING ] backend.core.database: lock_wait wait_time_ms=150.25 statement=SELECT * FROM workflow_executions WHERE id = 123 FOR UPDATE
```

## Implementation Details

### Event Listeners

The monitoring uses two SQLAlchemy event listeners:

1. **before_cursor_execute**: Records start time when `FOR UPDATE` is detected
2. **after_cursor_execute**: Calculates elapsed time and updates metrics

### Performance Impact

- Minimal overhead: only tracks queries with `FOR UPDATE`
- Time measurement uses `time.time()` (microsecond precision)
- No database queries or I/O operations
- Metrics stored in memory (dictionary)

### Thread Safety

The current implementation uses a global dictionary for metrics. In multi-threaded environments, consider:
- Using `threading.Lock` for metric updates
- Per-thread metrics collection
- External metrics aggregation (e.g., Prometheus)

## Integration with Monitoring Systems

### Prometheus Example

```python
from prometheus_client import Counter, Histogram
from backend.core.database import get_lock_contention_metrics

# Define metrics
lock_waits_total = Counter('db_lock_waits_total', 'Total database lock waits')
lock_wait_duration = Histogram('db_lock_wait_duration_ms', 'Lock wait duration in milliseconds')

# Export metrics periodically
def export_metrics():
    metrics = get_lock_contention_metrics()
    lock_waits_total.inc(metrics['total_lock_waits'])
    lock_wait_duration.observe(metrics['avg_wait_time_ms'])
```

### Health Check Endpoint

```python
from fastapi import APIRouter
from backend.core.database import get_lock_contention_metrics

router = APIRouter()

@router.get("/health/locks")
def lock_health():
    metrics = get_lock_contention_metrics()
    
    # Alert if too many slow locks
    if metrics['waits_over_100ms'] > 100:
        return {"status": "warning", "metrics": metrics}
    
    return {"status": "healthy", "metrics": metrics}
```

## Testing

The monitoring system includes comprehensive unit tests:

- Event listener installation
- FOR UPDATE detection
- Metric accumulation
- Logging behavior
- Edge cases (zero waits, max tracking)

Run tests:
```bash
pytest tests/core/test_lock_monitoring.py -v
```

## Configuration

### Adjusting the Warning Threshold

To change the 100ms threshold, modify `_install_lock_monitoring` in `backend/core/database.py`:

```python
# Log waits exceeding threshold
THRESHOLD_MS = 100  # Change this value
if wait_time_ms > THRESHOLD_MS:
    _lock_contention_metrics["waits_over_100ms"] += 1
    logger.warning(...)
```

### Disabling Monitoring

To disable monitoring, comment out the installation in `Database.__init__`:

```python
def __init__(self, url: str) -> None:
    # ...
    # _install_lock_monitoring(self._engine)  # Disabled
```

## Best Practices

1. **Monitor in Production**: Enable monitoring in production to identify real-world contention
2. **Set Alerts**: Configure alerts for high `waits_over_100ms` counts
3. **Periodic Reset**: Reset metrics periodically (e.g., hourly) for time-windowed analysis
4. **Correlate with Load**: Compare lock metrics with request rate and database load
5. **Optimize Queries**: Use metrics to identify and optimize slow lock acquisitions

## Related Documentation

- [Race Condition Handling](../../../.kiro/specs/sqlite-to-postgres-migration/design.md#race-condition-handling)
- [Pessimistic Locking Strategy](../../../.kiro/specs/sqlite-to-postgres-migration/design.md#pessimistic-locking-strategy)
- [Database Architecture](../../../.kiro/specs/sqlite-to-postgres-migration/design.md#database-connection-lifecycle)
