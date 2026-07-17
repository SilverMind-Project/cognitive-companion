/**
 * Read-only feeds: the unified signals feed, raw events, and recorded interactive responses.
 *
 * The signals feed merges CTS dementia signals with pipeline-rule notifications; it is the
 * single source for "what has the system noticed", and panels consume it rather than
 * re-deriving signals client-side.
 */

import { client, unwrap } from "@/services/http";
import type { operations } from "@/generated/api-types";

type FeedParams = operations["get_signals_feed"]["parameters"]["query"];
type EventsParams = operations["list_events"]["parameters"]["query"];
type InteractiveParams = operations["get_interactive_responses"]["parameters"]["query"];

export const getSignalsFeed = (params: FeedParams = {}) =>
  unwrap(client.GET("/api/v1/signals/feed", { params: { query: params } }));

export const getEvents = (params: EventsParams = {}) =>
  unwrap(client.GET("/api/v1/events", { params: { query: params } }));

export const getInteractiveResponses = (params: InteractiveParams = {}) =>
  unwrap(client.GET("/api/v1/interactive-responses", { params: { query: params } }));
