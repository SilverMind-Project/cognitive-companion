---
paths: ["**/backend/**/*.py", "**/frontend/src/**"]
---

# Time

- Store and compare timezone-aware UTC (`datetime.now(UTC)`, `TIMESTAMPTZ`). A naive datetime
  is a bug.
- Wall-clock rules (schedules, time-of-day windows, daily counters) use `app.timezone` from
  `config/settings.yaml`: convert to local time before comparing a time of day.
- Logic with deadlines, cooldowns, or windows takes an injectable clock; tests advance a fake
  clock and never sleep.
- The frontend formats time only through `services/timezone.js`, never `toLocaleString()` or
  `getHours()`.
