"""Bootstrap phase: knowledge repository services + notification dispatcher.

Moved verbatim from ``backend/main.py``'s lifespan (M20): the embedding
client, layout/voice-instruction registries, image pipeline, the four
knowledge services (ingestion, query, content generation, delivery), and
the notification dispatcher. The dispatcher sits here (rather than in
``core_services.py``) only because that is where it sits in the original
source -- it depends solely on core-services outputs, but is constructed
after the knowledge block in ``main.py``, and this module preserves exact
construction order. See ``bootstrap/README.md``.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.core.config import Settings
from backend.core.database import get_session
from backend.core.logging import get_logger

logger = get_logger(__name__)


def wire_knowledge(app: FastAPI, settings: Settings) -> None:
    minio_client = app.state.minio_client
    ws_manager = app.state.ws_manager
    eink_renderer = app.state.eink_renderer
    llm_model_registry = app.state.llm_model_registry

    # -- Embedding client ---------------------------------------------------
    from backend.integrations.triton_embedding_client import TritonEmbeddingClient

    embedding_client = TritonEmbeddingClient()
    # Shared with the guided-task bridge (DL-M05): one lazy Triton
    # connection for text embeddings, not a second client instance.
    app.state.embedding_client = embedding_client

    # -- Knowledge services -------------------------------------------------
    from backend.services.knowledge.content_generation import ContentGenerationService
    from backend.services.knowledge.delivery_service import KnowledgeDeliveryService
    from backend.services.knowledge.image_pipeline import ImagePipeline
    from backend.services.knowledge.ingestion_service import KnowledgeIngestionService
    from backend.services.knowledge.layout_registry import LayoutRegistry
    from backend.services.knowledge.query_service import KnowledgeQueryService
    from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

    layouts_file = settings.as_str("knowledge.layouts_file")
    layout_registry = LayoutRegistry.load(layouts_file)
    app.state.layout_registry = layout_registry

    voice_config_file = settings.as_str("knowledge.voice_config_file")
    voice_instructions = VoiceInstructionConfig.load(voice_config_file)
    app.state.voice_instructions = voice_instructions

    image_pipeline = ImagePipeline(minio_client=minio_client, layouts=layout_registry)
    app.state.image_pipeline = image_pipeline

    knowledge_ingestion = KnowledgeIngestionService(
        db_factory=get_session,
        minio_client=minio_client,
        image_pipeline=image_pipeline,
        embedding_client=embedding_client,
    )
    app.state.knowledge_ingestion = knowledge_ingestion

    knowledge_query = KnowledgeQueryService(
        db_factory=get_session,
        embedding_client=embedding_client,
        llm_model_registry=llm_model_registry,
    )
    app.state.knowledge_query = knowledge_query

    knowledge_content_gen = ContentGenerationService(
        db_factory=get_session,
        llm_model_registry=llm_model_registry,
    )
    app.state.knowledge_content_gen = knowledge_content_gen

    knowledge_delivery = KnowledgeDeliveryService(
        db_factory=get_session,
        ws_manager=ws_manager,
        minio_client=minio_client,
        eink_renderer=eink_renderer,
        voice_instructions=voice_instructions,
        content_generation=knowledge_content_gen,
    )
    app.state.knowledge_delivery = knowledge_delivery

    logger.info(
        "knowledge_services_initialized",
        layouts=[lt.id for lt in layout_registry.all_layouts()],
    )

    # -- Notification dispatcher -------------------------------------------
    from backend.services.notification_dispatcher import NotificationDispatcher

    notifier = NotificationDispatcher(
        telegram_client=app.state.telegram_client,
        ws_manager=ws_manager,
        tts_client=app.state.tts_client,
        image_renderer=eink_renderer.render,
        minio_client=minio_client,
        ha_client=app.state.ha_client,
    )
    app.state.notification_dispatcher = notifier
