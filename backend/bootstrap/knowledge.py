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
from backend.integrations.llm import LLMModelRegistry

logger = get_logger(__name__)

KNOWLEDGE_MODEL_SETTING_KEYS: tuple[str, ...] = (
    "knowledge.answer_model",
    "knowledge.paraphrase_model",
    "knowledge.quiz_generation_model",
)


def validate_knowledge_models(settings: Settings, registry: LLMModelRegistry) -> list[str]:
    """Return the knowledge model setting keys whose id is not in ``llm.models``.

    An unknown id makes every senior RAG answer, paraphrase, and quiz draft fail at call time
    with an empty or raised result, which is invisible until a resident asks a question. Each
    offender is logged at startup with the ids that do exist. Startup still continues: the
    knowledge features degrade, but the safety watch and escalation must not go down over a
    knowledge-model typo, so the shipped config is pinned by a unit test instead.
    """
    available = sorted(c.id for c in registry.all_configs())
    invalid: list[str] = []
    for key in KNOWLEDGE_MODEL_SETTING_KEYS:
        model_id = settings.as_str(key, allow_empty=True)
        if registry.get_config(model_id) is None:
            invalid.append(key)
            logger.error(
                "knowledge_invalid_model_id_configured",
                setting_key=key,
                model_id=model_id,
                available_models=available,
            )
    return invalid


def knowledge_model_requirements(settings: Settings) -> dict[str, str]:
    """The model id each knowledge feature depends on, keyed by its setting."""
    return {key: settings.as_str(key, allow_empty=True) for key in KNOWLEDGE_MODEL_SETTING_KEYS}


def wire_knowledge(app: FastAPI, settings: Settings) -> None:
    minio_client = app.state.minio_client
    ws_manager = app.state.ws_manager
    eink_renderer = app.state.eink_renderer
    llm_model_registry = app.state.llm_model_registry
    validate_knowledge_models(settings, llm_model_registry)

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
    from backend.services.knowledge.info_card_service import InfoCardService
    from backend.services.knowledge.ingestion_service import KnowledgeIngestionService
    from backend.services.knowledge.interaction_service import KnowledgeInteractionService
    from backend.services.knowledge.layout_registry import LayoutRegistry
    from backend.services.knowledge.query_service import KnowledgeQueryService
    from backend.services.knowledge.quiz_service import QuizService
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

    app.state.info_card_service = InfoCardService(
        db_factory=get_session,
        minio_client=minio_client,
        image_pipeline=image_pipeline,
        layout_registry=layout_registry,
    )
    app.state.quiz_service = QuizService(
        db_factory=get_session,
        minio_client=minio_client,
        image_pipeline=image_pipeline,
        layout_registry=layout_registry,
    )
    app.state.knowledge_interaction_service = KnowledgeInteractionService(
        db_factory=get_session,
    )

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
        base_instruction=settings.as_str("llm.realtime.system_instruction"),
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
