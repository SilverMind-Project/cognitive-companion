/** Guided sessions: live runs of a routine, plus caregiver takeover and metrics. */

import { client, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type GuidedSessionOut = Schemas["GuidedSessionOut"];

type ListParams = operations["list_guided_sessions"]["parameters"]["query"];
type MetricsParams = operations["get_guided_metrics_dashboard"]["parameters"]["query"];

export const listGuidedSessions = (params: ListParams = {}) =>
  unwrap(client.GET("/api/v1/guided-sessions", { params: { query: params } }));

export const getGuidedSessionDetail = (id: number) =>
  unwrap(
    client.GET("/api/v1/guided-sessions/{session_id}/detail", {
      params: { path: { session_id: id } },
    }),
  );

// ─── Caregiver takeover ────────────────────────────────────────────────────

export const beginGuidedSessionTakeover = (id: number) =>
  unwrap(
    client.POST("/api/v1/guided-sessions/{session_id}/takeover", {
      params: { path: { session_id: id } },
    }),
  );

export const sayGuidedSession = (id: number, text: string) =>
  unwrap(
    client.POST("/api/v1/guided-sessions/{session_id}/say", {
      params: { path: { session_id: id } },
      body: { text },
    }),
  );

export const advanceGuidedSession = (id: number) =>
  unwrap(
    client.POST("/api/v1/guided-sessions/{session_id}/advance", {
      params: { path: { session_id: id } },
    }),
  );

export const completeGuidedSession = (id: number) =>
  unwrap(
    client.POST("/api/v1/guided-sessions/{session_id}/complete", {
      params: { path: { session_id: id } },
    }),
  );

export const releaseGuidedSession = (id: number) =>
  unwrap(
    client.POST("/api/v1/guided-sessions/{session_id}/release", {
      params: { path: { session_id: id } },
    }),
  );

// ─── Metrics ───────────────────────────────────────────────────────────────

/** `person_id` is required by the endpoint; the sole caller already supplies it. */
export const getGuidedMetricsDashboard = (params: MetricsParams) =>
  unwrap(client.GET("/api/v1/guided-metrics/dashboard", { params: { query: params } }));
