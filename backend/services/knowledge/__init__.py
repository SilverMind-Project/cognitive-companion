"""Knowledge repository services.

layout_registry   - typed layout config loaded from YAML at startup
image_pipeline    - variant rendering, purge, and upload-time validation
ingestion_service - document CRUD with status transition guards
query_service     - RAG query path (Phase 2)
content_generation- LLM paraphrase and quiz suggestion (Phase 4)
delivery_service  - ws fanout + eink rendering for pipeline steps (Phase 3)
"""
