"""Bootstrap phase: boot preliminaries and core integration clients.

Moved verbatim from ``backend/main.py``'s lifespan (M20). Covers: settings
reload, DB init, hardware sensor upsert, plugin discovery, the integration
clients (MinIO, Home Assistant, Telegram, TTS), the WebSocket connection
managers, the realtime LLM provider, the named LLM model registry, the
conversation manager, and the e-ink renderer. See ``bootstrap/README.md``
for the full attribute inventory.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.core.config import Settings
from backend.core.database import get_session, init_db
from backend.core.logging import get_logger

logger = get_logger(__name__)

# Maps device_type values (from auth.yaml) to Sensor.sensor_type values.
_DEVICE_TYPE_TO_SENSOR_TYPE: dict[str, str] = {
    "recamera": "camera",
    "reterminal": "eink",
}


def _upsert_device_key_sensors(settings: Settings) -> None:
    """Upsert sensors for every entry in auth.yaml device_keys.

    Runs once at startup so hardware devices defined in the auth config are
    immediately queryable via the sensors API without a manual create step.
    Existing sensors are updated (name refresh); new ones are inserted.
    """
    from backend.models.sensor import Sensor

    device_keys = settings.as_list("auth.device_keys")
    if not device_keys:
        return

    db = get_session()
    try:
        for entry in device_keys:
            sensor_id = entry.get("sensor_id")
            if not sensor_id:
                continue
            sensor_type = _DEVICE_TYPE_TO_SENSOR_TYPE.get(entry.get("device_type", ""), "generic")
            name = entry.get("name", sensor_id)

            existing = db.get(Sensor, sensor_id)
            if existing:
                existing.name = name
                existing.sensor_type = sensor_type
            else:
                db.add(
                    Sensor(
                        id=sensor_id,
                        name=name,
                        sensor_type=sensor_type,
                        source="local",
                        enabled=True,
                    )
                )
        db.commit()
    except Exception:
        logger.exception("device_key_sensor_upsert_error")
        db.rollback()
    finally:
        db.close()


def wire_boot_preamble(app: FastAPI, settings: Settings) -> None:
    """Settings/logging/DB/plugin-registry bootstrapping that precedes every
    other phase and does not itself belong to any one of them."""
    from backend.core.auth import invalidate_lookup_cache
    from backend.core.logging import setup_logging

    settings.reload()
    setup_logging()
    # Invalidate the auth key cache so it is rebuilt from the freshly loaded config.
    invalidate_lookup_cache()
    logger.info("Starting Cognitive Companion v2")

    # Database
    init_db()
    logger.info("Database initialized")

    # -- Upsert hardware devices from auth.yaml device_keys ---------------
    _upsert_device_key_sensors(settings)
    logger.info("device_key_sensors_upserted")

    # -- Plugin discovery (steps, channels, filters) -----------------------
    from backend.channels import ChannelRegistry
    from backend.filters import FilterRegistry
    from backend.steps import StepRegistry

    StepRegistry.discover()
    ChannelRegistry.discover()
    FilterRegistry.discover()
    logger.info(
        "plugins_discovered",
        steps=StepRegistry.all_names(),
        channels=ChannelRegistry.all_names(),
        filters=FilterRegistry.all_names(),
    )


def wire_core_services(app: FastAPI, settings: Settings) -> None:
    """Integration clients, WS managers, LLM registry, conversation manager,
    e-ink renderer. All assigned onto ``app.state``."""
    # -- Integration clients -----------------------------------------------
    from backend.integrations.homeassistant import HomeAssistantClient
    from backend.integrations.minio_client import get_config_minio_client, get_minio_client
    from backend.integrations.telegram import TelegramClient
    from backend.integrations.tts import TTSClient

    minio_client = get_minio_client()
    config_minio_client = get_config_minio_client()
    ha_client = HomeAssistantClient()
    telegram_client = TelegramClient()
    tts_client = TTSClient()

    app.state.minio_client = minio_client
    app.state.config_minio_client = config_minio_client
    app.state.ha_client = ha_client
    app.state.telegram_client = telegram_client
    app.state.tts_client = tts_client

    # -- WebSocket connection manager --------------------------------------
    from backend.websocket.connection_manager import ConnectionManager
    from backend.websocket.pipeline_manager import PipelineConnectionManager

    ws_manager = ConnectionManager()
    app.state.ws_manager = ws_manager

    pipeline_ws_manager = PipelineConnectionManager()
    app.state.pipeline_ws_manager = pipeline_ws_manager

    # -- Realtime LLM provider (lazy - only connects when needed) ----------
    from backend.integrations.llm.realtime import create_realtime_provider

    realtime_provider = create_realtime_provider(settings)
    app.state.realtime_provider = realtime_provider

    # -- LLM providers for the pipeline ------------------------------------
    from backend.integrations.llm import LLMModelRegistry
    from backend.integrations.llm.admission import LLMAdmissionController

    # -- Admission controller (DL5/DL-M09): the single choke point in front
    # of every local vision/text LLM provider, sized for one DGX Spark. ----
    llm_admission_controller = LLMAdmissionController(
        max_concurrent_vision=settings.as_int("llm.admission.max_concurrent_vision"),
        max_concurrent_text=settings.as_int("llm.admission.max_concurrent_text"),
        queue_timeout_s=settings.as_float("llm.admission.queue_timeout_s"),
    )
    app.state.llm_admission_controller = llm_admission_controller

    from backend.services.inference_telemetry import InferenceTelemetryService

    app.state.inference_telemetry = InferenceTelemetryService(llm_admission_controller)

    # -- Named model registry (for the unified llm_call step) --------------
    llm_model_registry = LLMModelRegistry(admission_controller=llm_admission_controller)
    llm_model_registry.load_from_settings()
    app.state.llm_model_registry = llm_model_registry
    logger.info(
        "llm_model_registry_loaded",
        models=[c.id for c in llm_model_registry.all_configs()],
    )

    # -- Conversation manager ----------------------------------------------
    from backend.services.conversation_manager import ConversationManager

    conversation_manager = ConversationManager(get_session)
    app.state.conversation_manager = conversation_manager

    # -- E-Ink renderer (internal integration) --------------------------------
    from backend.integrations.eink_renderer import EInkRenderer

    eink_renderer = EInkRenderer(db_session_factory=get_session, minio_client=config_minio_client)
    eink_renderer.seed_templates()
    app.state.eink_renderer = eink_renderer
