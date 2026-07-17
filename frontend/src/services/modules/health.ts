/**
 * Health probes for the backend and the upstream services it depends on.
 *
 * Each probe returns `configured` plus whatever the upstream health body carried, so the
 * response type is intentionally open (the backend's ServiceHealthOut allows extras). Callers
 * read service-specific keys off it -- the dashboard reads TTS's `default_engine`, for example.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

export type ServiceHealthOut = components["schemas"]["ServiceHealthOut"];
export type LivenessOut = components["schemas"]["LivenessOut"];

/** Liveness probe. Unauthenticated: it must answer before the app holds a key. */
export const health = () => unwrap(client.GET("/api/v1/health", {}));

export const ttsHealth = () => unwrap(client.GET("/api/v1/admin/health/tts", {}));

export const personIdHealth = () => unwrap(client.GET("/api/v1/admin/health/person-id", {}));

export const trackingOrchestratorHealth = () =>
  unwrap(client.GET("/api/v1/admin/health/tracking-orchestrator", {}));

export const sceneAnalysisHealth = () =>
  unwrap(client.GET("/api/v1/admin/health/scene-analysis", {}));

export const semanticMemoryHealth = () =>
  unwrap(client.GET("/api/v1/admin/health/semantic-memory", {}));

export const tritonHealth = () => unwrap(client.GET("/api/v1/admin/health/triton", {}));

export const llmHealth = () => unwrap(client.GET("/api/v1/admin/health/llm-models", {}));
