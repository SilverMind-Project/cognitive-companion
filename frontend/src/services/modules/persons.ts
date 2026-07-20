/**
 * Household members, their locations/history, and face enrollment.
 *
 * `getPersonLocations` / `getPersonLocation` return `PersonLocationEnvelope` from
 * PersonLocationService (the SSOT shared with the MCP tools). They were shadowed by legacy
 * routes until C17; see `usePersonPresence` for the single fetch owner of current locations --
 * panels consume that composable rather than calling these directly.
 */

import { client, requestForm, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type PersonLocationEnvelope = Schemas["PersonLocationEnvelope"];
export type HouseholdMemberOut = Schemas["HouseholdMemberOut"];

type HeatmapParams = operations["get_heatmap"]["parameters"]["query"];

export const getPersons = () => unwrap(client.GET("/api/v1/persons", {}));

export const createPerson = (data: Schemas["HouseholdMemberCreate"]) =>
  unwrap(client.POST("/api/v1/persons", { body: data }));

export const getPerson = (id: string) =>
  unwrap(client.GET("/api/v1/persons/{person_id}", { params: { path: { person_id: id } } }));

export const updatePerson = (id: string, data: Schemas["HouseholdMemberUpdate"]) =>
  unwrap(
    client.PATCH("/api/v1/persons/{person_id}", {
      params: { path: { person_id: id } },
      body: data,
    }),
  );

export const deletePerson = (id: string) =>
  unwrap(client.DELETE("/api/v1/persons/{person_id}", { params: { path: { person_id: id } } }));

// ─── Location ──────────────────────────────────────────────────────────────

export const getPersonLocations = () => unwrap(client.GET("/api/v1/persons/locations", {}));

export const getPersonLocation = (id: string) =>
  unwrap(
    client.GET("/api/v1/persons/{person_id}/location", { params: { path: { person_id: id } } }),
  );

export const getPersonHistory = async (id: string, hours = 24) => [] as any[];

export const getPersonSightings = async (id: string, limit = 20) => [] as any[];

/**
 * `person_id`, `start_time` and `end_time` are required by the endpoint. The old client
 * defaulted params to `{}`, which could only ever 422; the type makes that unrepresentable.
 */
export const getHeatmap = (params: HeatmapParams) =>
  unwrap(client.GET("/api/v1/cts/analytics/heatmap", { params: { query: params } }));

// ─── Face enrollment (person-ID service proxy) ─────────────────────────────

export const getEnrolledPersons = () => unwrap(client.GET("/api/v1/persons/enrolled", {}));

export const getEnrollmentStatus = (id: string) =>
  unwrap(
    client.GET("/api/v1/persons/{person_id}/enrollment", { params: { path: { person_id: id } } }),
  );

/** Multipart: the browser must set its own boundary, so this bypasses the JSON client. */
export const enrollPerson = (id: string, formData: FormData) =>
  requestForm(`/api/v1/persons/${encodeURIComponent(id)}/enroll`, "POST", formData);

export const deleteEnrollment = (id: string) =>
  unwrap(
    client.DELETE("/api/v1/persons/{person_id}/enrollment", {
      params: { path: { person_id: id } },
    }),
  );
