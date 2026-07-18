/** Routines: the authored step graphs the guided companion walks a senior through. */

import { client, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type RoutineOut = Schemas["RoutineOut"];

type ListParams = operations["list_routines"]["parameters"]["query"];

export const listRoutines = (params: ListParams = {}) =>
  unwrap(client.GET("/api/v1/routines", { params: { query: params } }));

export const getLanguageOptions = () => unwrap(client.GET("/api/v1/routines/language-options", {}));

export const getRoutine = (id: number) =>
  unwrap(client.GET("/api/v1/routines/{routine_id}", { params: { path: { routine_id: id } } }));

export const createRoutine = (data: Schemas["RoutineCreate"]) =>
  unwrap(client.POST("/api/v1/routines", { body: data }));

export const updateRoutine = (id: number, data: Schemas["RoutineUpdate"]) =>
  unwrap(
    client.PATCH("/api/v1/routines/{routine_id}", {
      params: { path: { routine_id: id } },
      body: data,
    }),
  );

export const deleteRoutine = (id: number) =>
  unwrap(client.DELETE("/api/v1/routines/{routine_id}", { params: { path: { routine_id: id } } }));

export const replaceRoutineSteps = (id: number, steps: Schemas["RoutineStepsReplaceIn"]["steps"]) =>
  unwrap(
    client.PUT("/api/v1/routines/{routine_id}/steps", {
      params: { path: { routine_id: id } },
      body: { steps },
    }),
  );

export const testRunRoutine = (id: number, data: Schemas["RoutineTestRunIn"]) =>
  unwrap(
    client.POST("/api/v1/routines/{routine_id}/test-run", {
      params: { path: { routine_id: id } },
      body: data,
    }),
  );
