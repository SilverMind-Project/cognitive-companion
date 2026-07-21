/** Activities, the activity timeline, sessions, and daily reports. */

import { client, unwrap } from "@/services/http";
import type { operations } from "@/generated/api-types";

type ActivitiesParams = operations["list_activities"]["parameters"]["query"];
type TimelineParams = operations["get_timeline"]["parameters"]["query"];
type OpenSessionParams = operations["open_activity_session"]["parameters"]["query"];
type CloseSessionParams = operations["close_activity_session"]["parameters"]["query"];
type ReportParams = operations["get_daily_report"]["parameters"]["query"];
type RegenerateParams = operations["regenerate_daily_report"]["parameters"]["query"];

export const getActivities = (params: ActivitiesParams = {}) =>
  unwrap(client.GET("/api/v1/activities", { params: { query: params } }));

export const getTimeline = (personId: string, params: Omit<TimelineParams, "person_id"> = {}) =>
  unwrap(
    client.GET("/api/v1/activities/timeline", {
      params: { query: { ...params, person_id: personId } },
    }),
  );

// ─── Sessions ──────────────────────────────────────────────────────────────
//
// These endpoints take *query* parameters, not a JSON body. The pre-client sent a body and
// no query string, so every call was a guaranteed 422 -- invisible because nothing calls these
// two today. Migrated to the real contract rather than preserving the broken call.

export const openSession = (personId: string, data: Omit<OpenSessionParams, "person_id">) =>
  unwrap(
    client.POST("/api/v1/activities/sessions/open", {
      params: { query: { ...data, person_id: personId } },
    }),
  );

export const closeSession = (sessionId: string, data: CloseSessionParams) =>
  unwrap(
    client.POST("/api/v1/activities/sessions/{session_id}/close", {
      params: { path: { session_id: sessionId }, query: data },
    }),
  );

export const getOpenSessions = (personId?: string) =>
  unwrap(
    client.GET("/api/v1/activities/sessions/open", {
      params: { query: personId ? { person_id: personId } : {} },
    }),
  );

// ─── Daily reports ─────────────────────────────────────────────────────────
//
// person_id and date are path segments the old client interpolated raw.

export const getDailyReport = (personId: string, date: string, params: ReportParams = {}) =>
  unwrap(
    client.GET("/api/v1/activities/reports/{person_id}/{date}", {
      params: { path: { person_id: personId, date }, query: params },
    }),
  );

/**
 * Force regeneration of a daily report.
 *
 * GET, because that is what the route declares. The old client issued a POST, so this button
 * has been answering 405 and failing silently in `DailyReportCard.vue` -- the typed client is
 * what surfaced it. The endpoint deleting and rebuilding a report behind a GET is its own
 * problem (unsafe/non-idempotent verb, prefetchable); fixing the verb is a backend contract
 * change and is filed separately rather than smuggled into this change.
 */
export const regenerateDailyReport = (
  personId: string,
  date: string,
  params: RegenerateParams = {},
) =>
  unwrap(
    client.GET("/api/v1/activities/reports/{person_id}/{date}/regenerate", {
      params: { path: { person_id: personId, date }, query: params },
    }),
  );
