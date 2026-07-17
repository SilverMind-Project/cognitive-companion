/**
 * Workflows domain: execution list, detail, cancel, rerun.
 *
 * `GET /workflows/{id}/detail` is the canonical execution-inspector contract; the pipeline-runs
 * endpoints (see `modules/pipeline.ts`) stay lightweight and are not a substitute for it.
 */

import { client, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type WorkflowExecutionListOut = Schemas["WorkflowExecutionListOut"];
export type WorkflowExecutionOut = Schemas["WorkflowExecutionOut"];
export type ExecutionDetailOut = Schemas["ExecutionDetailOut"];
export type ExecutionCancelledOut = Schemas["ExecutionCancelledOut"];
export type ExecutionRerunOut = Schemas["ExecutionRerunOut"];

type ListParams = operations["list_executions"]["parameters"]["query"];

export const getWorkflows = (params: ListParams = {}) =>
  unwrap(client.GET("/api/v1/workflows", { params: { query: params } }));

export const getWorkflow = (id: number) =>
  unwrap(
    client.GET("/api/v1/workflows/{execution_id}", { params: { path: { execution_id: id } } }),
  );

export const getWorkflowDetail = (id: number) =>
  unwrap(
    client.GET("/api/v1/workflows/{execution_id}/detail", {
      params: { path: { execution_id: id } },
    }),
  );

export const cancelWorkflow = (id: number) =>
  unwrap(
    client.POST("/api/v1/workflows/{execution_id}/cancel", {
      params: { path: { execution_id: id } },
    }),
  );

export const rerunWorkflow = (id: number) =>
  unwrap(
    client.POST("/api/v1/workflows/{execution_id}/rerun", {
      params: { path: { execution_id: id } },
      body: {},
    }),
  );
