/**
 * Pipeline domain: live/recent run lists and authoring metadata (step/channel/filter types).
 *
 * `getPipelineRuns` is for lightweight live and recent-run lists only. For inspector data use
 * `getWorkflowDetail` in `modules/workflows.ts` -- that is the detail contract.
 *
 * The metadata endpoints back the authoring palette. `vocabularies.json` (M14) is the
 * synchronous fallback for code that cannot await a network call; these are the live source.
 */

import { client, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type PipelineRunEnvelope = Schemas["PipelineRunEnvelope"];
export type StepTypeOut = Schemas["StepTypeOut"];

type RunsParams = operations["list_pipeline_runs"]["parameters"]["query"];
type IngestActivityParams = operations["list_ingest_activity"]["parameters"]["query"];
type SampleImageParams = operations["get_sample_image"]["parameters"]["query"];

// ─── Runs ──────────────────────────────────────────────────────────────────

export const getPipelineRuns = (params: RunsParams = {}) =>
  unwrap(client.GET("/api/v1/pipeline/runs", { params: { query: params } }));

export const getPipelineRun = (executionId: number) =>
  unwrap(
    client.GET("/api/v1/pipeline/runs/{execution_id}", {
      params: { path: { execution_id: executionId } },
    }),
  );

export const getIngestActivity = (params: IngestActivityParams = {}) =>
  unwrap(client.GET("/api/v1/pipeline/ingest/activity", { params: { query: params } }));

// ─── Authoring metadata ────────────────────────────────────────────────────

export const getStepTypes = () => unwrap(client.GET("/api/v1/pipeline/step-types", {}));

export const getChannelTypes = () => unwrap(client.GET("/api/v1/pipeline/channel-types", {}));

export const getFilterTypes = () => unwrap(client.GET("/api/v1/pipeline/filter-types", {}));

export const getLLMModels = () => unwrap(client.GET("/api/v1/pipeline/llm-models", {}));

export const getDataKeys = () => unwrap(client.GET("/api/v1/pipeline/data-keys", {}));

export const getCronPreview = (data: Schemas["CronPreviewRequest"]) =>
  unwrap(client.POST("/api/v1/pipeline/cron/preview", { body: data }));

/** `source_type` is required by the endpoint, so unlike the old client this cannot be omitted. */
export const getSampleImage = (params: SampleImageParams) =>
  unwrap(client.GET("/api/v1/pipeline/image-sources/sample", { params: { query: params } }));
