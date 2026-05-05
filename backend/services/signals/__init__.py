"""SignalsService: async read API for CTS dementia signals.

Wraps :class:`~backend.services.cts.signal_store.SignalStore` so pipeline
steps never touch ``db_factory`` or ``SignalStore`` directly.
"""

from __future__ import annotations

from backend.services.signals.service import SignalsService

__all__ = ["SignalsService"]
