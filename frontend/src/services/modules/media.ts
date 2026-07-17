/** Camera media buffer and aggregator telemetry. */

import { client, unwrap } from "@/services/http";
import type { operations } from "@/generated/api-types";

type BufferParams = operations["get_media_buffer"]["parameters"]["query"];
type AggregatorParams = operations["get_aggregators"]["parameters"]["query"];

export const getMediaBuffer = (params: BufferParams = {}) =>
  unwrap(client.GET("/api/v1/media/buffer", { params: { query: params } }));

export const getAggregatorState = (params: AggregatorParams = {}) =>
  unwrap(client.GET("/api/v1/media/aggregators", { params: { query: params } }));
