/** Info cards: caregiver-approved paraphrases delivered to the senior. */

import { client, requestForm, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type InfoCardOut = Schemas["InfoCardOut"];
export type InfoCardListOut = Schemas["InfoCardListOut"];

type ListParams = operations["list_info_cards"]["parameters"]["query"];
type SuggestParams = operations["suggest_info_card"]["parameters"]["query"];

export const getInfoCards = (params: ListParams = {}) =>
  unwrap(client.GET("/api/v1/info-cards", { params: { query: params } }));

export const getInfoCard = (id: number) =>
  unwrap(client.GET("/api/v1/info-cards/{card_id}", { params: { path: { card_id: id } } }));

export const createInfoCard = (data: Schemas["InfoCardCreate"]) =>
  unwrap(client.POST("/api/v1/info-cards", { body: data }));

export const updateInfoCard = (id: number, data: Schemas["InfoCardUpdate"]) =>
  unwrap(
    client.PATCH("/api/v1/info-cards/{card_id}", { params: { path: { card_id: id } }, body: data }),
  );

export const deleteInfoCard = (id: number) =>
  unwrap(client.DELETE("/api/v1/info-cards/{card_id}", { params: { path: { card_id: id } } }));

export const approveInfoCard = (id: number) =>
  unwrap(client.POST("/api/v1/info-cards/{card_id}/approve", { params: { path: { card_id: id } } }));

export const archiveInfoCard = (id: number) =>
  unwrap(client.POST("/api/v1/info-cards/{card_id}/archive", { params: { path: { card_id: id } } }));

export const restoreInfoCard = (id: number) =>
  unwrap(client.POST("/api/v1/info-cards/{card_id}/restore", { params: { path: { card_id: id } } }));

export const suggestInfoCard = (documentId: number, modelId?: string) =>
  unwrap(
    client.POST("/api/v1/info-cards/suggest", {
      params: { query: { document_id: documentId, ...(modelId ? { model_id: modelId } : {}) } },
    }),
  );

// ─── Image slots ───────────────────────────────────────────────────────────

export const setInfoCardSlot = (cardId: number, slotIndex: number, formData: FormData) =>
  requestForm(`/api/v1/info-cards/${cardId}/slots/${slotIndex}`, "PUT", formData);

export const patchInfoCardSlot = (
  cardId: number,
  slotIndex: number,
  data: Schemas["InfoCardSlotPatch"],
) =>
  unwrap(
    client.PATCH("/api/v1/info-cards/{card_id}/slots/{slot_index}", {
      params: { path: { card_id: cardId, slot_index: slotIndex } },
      body: data,
    }),
  );

export const deleteInfoCardSlot = (cardId: number, slotIndex: number) =>
  unwrap(
    client.DELETE("/api/v1/info-cards/{card_id}/slots/{slot_index}", {
      params: { path: { card_id: cardId, slot_index: slotIndex } },
    }),
  );
