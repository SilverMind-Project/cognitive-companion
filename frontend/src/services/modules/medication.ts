/** A person's medication schedule. */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export type MedicationEntryOut = Schemas["MedicationEntryOut"];

const entryPath = (personId: string, entryId: number) => ({
  params: { path: { person_id: personId, entry_id: entryId } },
});

export const getMedicationSchedule = (personId: string) =>
  unwrap(
    client.GET("/api/v1/persons/{person_id}/medication-schedule", {
      params: { path: { person_id: personId } },
    }),
  );

export const createMedicationEntry = (personId: string, data: Schemas["MedicationEntryCreate"]) =>
  unwrap(
    client.POST("/api/v1/persons/{person_id}/medication-schedule", {
      params: { path: { person_id: personId } },
      body: data,
    }),
  );

export const updateMedicationEntry = (
  personId: string,
  entryId: number,
  data: Schemas["MedicationEntryUpdate"],
) =>
  unwrap(
    client.PATCH("/api/v1/persons/{person_id}/medication-schedule/{entry_id}", {
      ...entryPath(personId, entryId),
      body: data,
    }),
  );

export const deleteMedicationEntry = (personId: string, entryId: number) =>
  unwrap(
    client.DELETE(
      "/api/v1/persons/{person_id}/medication-schedule/{entry_id}",
      entryPath(personId, entryId),
    ),
  );
