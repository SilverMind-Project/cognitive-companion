/**
 * Gate graphs: callable rules (`trigger_types == []`) used as vision-confirm validation graphs.
 *
 * They are deliberately excluded from the normal rules surfaces (scheduling, telegram,
 * webhooks, rule listings), which is why they have their own endpoints rather than riding on
 * `modules/rules.ts`.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export const getGateGraphs = () => unwrap(client.GET("/api/v1/gate-graphs", {}));

export const createGateGraph = (data: Schemas["GateGraphCreate"]) =>
  unwrap(client.POST("/api/v1/gate-graphs", { body: data }));

export const getGateGraph = (id: number) =>
  unwrap(client.GET("/api/v1/gate-graphs/{rule_id}", { params: { path: { rule_id: id } } }));

export const validateGateGraph = (id: number) =>
  unwrap(
    client.POST("/api/v1/gate-graphs/{rule_id}/validate", { params: { path: { rule_id: id } } }),
  );

export const testRunGateGraph = (id: number, data: Schemas["GateTestRunRequest"]) =>
  unwrap(
    client.POST("/api/v1/gate-graphs/{rule_id}/test-run", {
      params: { path: { rule_id: id } },
      body: data,
    }),
  );

export const getGatePresets = () => unwrap(client.GET("/api/v1/gate-presets", {}));
