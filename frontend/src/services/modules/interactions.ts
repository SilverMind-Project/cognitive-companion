/** Read-only review of what the senior actually saw and answered. */

import { client, unwrap } from "@/services/http";
import type { operations } from "@/generated/api-types";

type QueriesParams = operations["list_queries"]["parameters"]["query"];
type SessionsParams = operations["list_quiz_sessions"]["parameters"]["query"];
type DeliveriesParams = operations["list_info_card_deliveries"]["parameters"]["query"];

export const getSeniorKnowledgeQueries = (params: QueriesParams = {}) =>
  unwrap(client.GET("/api/v1/knowledge-interactions/queries", { params: { query: params } }));

export const getQuizSessions = (params: SessionsParams = {}) =>
  unwrap(client.GET("/api/v1/knowledge-interactions/quiz-sessions", { params: { query: params } }));

export const getQuizSession = (id: number) =>
  unwrap(
    client.GET("/api/v1/knowledge-interactions/quiz-sessions/{session_id}", {
      params: { path: { session_id: id } },
    }),
  );

export const getInfoCardDeliveries = (params: DeliveriesParams = {}) =>
  unwrap(
    client.GET("/api/v1/knowledge-interactions/info-card-deliveries", {
      params: { query: params },
    }),
  );
