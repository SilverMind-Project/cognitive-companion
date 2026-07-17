/**
 * Rules domain: rules, their steps/edges, contexts, dependencies, cron triggers, import/export.
 *
 * Method names and return shapes match the pre-M17 `api.js` exactly; `api.js` re-exports these
 * under the same names, so views are unchanged. Params go through the typed client rather than
 * string interpolation, so path/query encoding is handled once, correctly.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export type RuleListOut = Schemas["RuleListOut"];
export type RuleOut = Schemas["RuleOut"];
export type RuleCreate = Schemas["RuleCreate"];
export type RuleUpdate = Schemas["RuleUpdate"];
export type RuleBundle = Schemas["RuleBundle"];
export type ImportReport = Schemas["ImportReport"];
export type RuleValidationOut = Schemas["RuleValidationOut"];
export type RuleExecutionStartedOut = Schemas["RuleExecutionStartedOut"];
export type PipelineStepOut = Schemas["PipelineStepOut"];
export type PipelineEdgeOut = Schemas["PipelineEdgeOut"];
export type RuleContextOut = Schemas["RuleContextOut"];
export type RuleDependencyOut = Schemas["RuleDependencyOut"];
export type CronTriggerOut = Schemas["CronTriggerOut"];

// ─── Rules ─────────────────────────────────────────────────────────────────

export const getRules = () => unwrap(client.GET("/api/v1/rules", {}));

export const createRule = (data: RuleCreate) =>
  unwrap(client.POST("/api/v1/rules", { body: data }));

export const getRule = (id: number) =>
  unwrap(client.GET("/api/v1/rules/{rule_id}", { params: { path: { rule_id: id } } }));

export const updateRule = (id: number, data: RuleUpdate) =>
  unwrap(client.PUT("/api/v1/rules/{rule_id}", { params: { path: { rule_id: id } }, body: data }));

export const deleteRule = (id: number) =>
  unwrap(client.DELETE("/api/v1/rules/{rule_id}", { params: { path: { rule_id: id } } }));

export const validateRule = (id: number) =>
  unwrap(client.POST("/api/v1/rules/{rule_id}/validate", { params: { path: { rule_id: id } } }));

export const executeRule = (ruleId: number) =>
  unwrap(client.POST("/api/v1/rules/{rule_id}/execute", { params: { path: { rule_id: ruleId } } }));

// ─── Contexts ──────────────────────────────────────────────────────────────

export const getRuleContexts = (ruleId: number) =>
  unwrap(client.GET("/api/v1/rules/{rule_id}/contexts", { params: { path: { rule_id: ruleId } } }));

export const addRuleContext = (ruleId: number, data: Schemas["ContextCreate"]) =>
  unwrap(
    client.POST("/api/v1/rules/{rule_id}/contexts", {
      params: { path: { rule_id: ruleId } },
      body: data,
    }),
  );

export const deleteRuleContext = (ruleId: number, ctxId: number) =>
  unwrap(
    client.DELETE("/api/v1/rules/{rule_id}/contexts/{context_id}", {
      params: { path: { rule_id: ruleId, context_id: ctxId } },
    }),
  );

// ─── Dependencies ──────────────────────────────────────────────────────────

export const getRuleDeps = (ruleId: number) =>
  unwrap(
    client.GET("/api/v1/rules/{rule_id}/dependencies", { params: { path: { rule_id: ruleId } } }),
  );

export const addRuleDep = (ruleId: number, data: Schemas["DependencyCreate"]) =>
  unwrap(
    client.POST("/api/v1/rules/{rule_id}/dependencies", {
      params: { path: { rule_id: ruleId } },
      body: data,
    }),
  );

export const deleteRuleDep = (ruleId: number, depId: number) =>
  unwrap(
    client.DELETE("/api/v1/rules/{rule_id}/dependencies/{dep_id}", {
      params: { path: { rule_id: ruleId, dep_id: depId } },
    }),
  );

// ─── Cron triggers ─────────────────────────────────────────────────────────

export const getCronTriggers = () => unwrap(client.GET("/api/v1/rules/cron-triggers", {}));

export const createCronTrigger = (data: Schemas["CronTriggerCreate"]) =>
  unwrap(client.POST("/api/v1/rules/cron-triggers", { body: data }));

export const updateCronTrigger = (id: number, data: Schemas["CronTriggerUpdate"]) =>
  unwrap(
    client.PUT("/api/v1/rules/cron-triggers/{ct_id}", {
      params: { path: { ct_id: id } },
      body: data,
    }),
  );

export const deleteCronTrigger = (id: number) =>
  unwrap(client.DELETE("/api/v1/rules/cron-triggers/{ct_id}", { params: { path: { ct_id: id } } }));

// ─── Import / export ───────────────────────────────────────────────────────

export const exportRule = (id: number) =>
  unwrap(client.GET("/api/v1/rules/{rule_id}/export", { params: { path: { rule_id: id } } }));

export const importRulePreview = (bundle: RuleBundle) =>
  unwrap(client.POST("/api/v1/rules/import/preview", { body: bundle }));

export const importRule = (bundle: RuleBundle) =>
  unwrap(client.POST("/api/v1/rules/import", { body: bundle }));

// ─── Steps and edges ───────────────────────────────────────────────────────

export const getRuleSteps = (ruleId: number) =>
  unwrap(client.GET("/api/v1/rules/{rule_id}/steps", { params: { path: { rule_id: ruleId } } }));

export const getRuleEdges = (ruleId: number) =>
  unwrap(client.GET("/api/v1/rules/{rule_id}/edges", { params: { path: { rule_id: ruleId } } }));

export const replaceRuleEdges = (
  ruleId: number,
  edges: Schemas["PipelineEdgeBulkUpdate"]["edges"],
) =>
  unwrap(
    client.PUT("/api/v1/rules/{rule_id}/edges", {
      params: { path: { rule_id: ruleId } },
      body: { edges },
    }),
  );

export const addRuleStep = (ruleId: number, data: Schemas["PipelineStepCreate"]) =>
  unwrap(
    client.POST("/api/v1/rules/{rule_id}/steps", {
      params: { path: { rule_id: ruleId } },
      body: data,
    }),
  );

export const updateRuleStep = (
  ruleId: number,
  stepId: number,
  data: Schemas["PipelineStepUpdate"],
) =>
  unwrap(
    client.PUT("/api/v1/rules/{rule_id}/steps/{step_id}", {
      params: { path: { rule_id: ruleId, step_id: stepId } },
      body: data,
    }),
  );

/** Position-only step update: a narrow alias over updateRuleStep, kept for call-site clarity. */
export const updateRuleStepPosition = (
  ruleId: number,
  stepId: number,
  { position_x, position_y }: { position_x: number; position_y: number },
) => updateRuleStep(ruleId, stepId, { position_x, position_y });

export const batchUpdateStepPositions = (
  ruleId: number,
  positions: Schemas["BatchPositionUpdate"]["positions"],
) =>
  unwrap(
    client.PUT("/api/v1/rules/{rule_id}/steps/positions", {
      params: { path: { rule_id: ruleId } },
      body: { positions },
    }),
  );

export const deleteRuleStep = (ruleId: number, stepId: number) =>
  unwrap(
    client.DELETE("/api/v1/rules/{rule_id}/steps/{step_id}", {
      params: { path: { rule_id: ruleId, step_id: stepId } },
    }),
  );
