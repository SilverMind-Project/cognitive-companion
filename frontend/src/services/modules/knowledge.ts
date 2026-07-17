/** Knowledge documents: the source material info cards and quizzes are generated from. */

import { client, requestForm, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type KnowledgeDocumentOut = Schemas["KnowledgeDocumentOut"];
export type KnowledgeDocumentListOut = Schemas["KnowledgeDocumentListOut"];

type ListParams = operations["list_documents"]["parameters"]["query"];

export const getKnowledgeDocuments = (params: ListParams = {}) =>
  unwrap(client.GET("/api/v1/knowledge/documents", { params: { query: params } }));

export const getKnowledgeDocument = (id: number) =>
  unwrap(client.GET("/api/v1/knowledge/documents/{doc_id}", { params: { path: { doc_id: id } } }));

/** Multipart: the document may carry an uploaded source file. */
export const createKnowledgeDocument = (formData: FormData) =>
  requestForm("/api/v1/knowledge/documents", "POST", formData);

export const updateKnowledgeDocument = (id: number, data: Schemas["KnowledgeDocumentUpdate"]) =>
  unwrap(
    client.PATCH("/api/v1/knowledge/documents/{doc_id}", {
      params: { path: { doc_id: id } },
      body: data,
    }),
  );

export const deleteKnowledgeDocument = (id: number) =>
  unwrap(
    client.DELETE("/api/v1/knowledge/documents/{doc_id}", { params: { path: { doc_id: id } } }),
  );

export const approveKnowledgeDocument = (id: number) =>
  unwrap(
    client.POST("/api/v1/knowledge/documents/{doc_id}/approve", {
      params: { path: { doc_id: id } },
    }),
  );

export const archiveKnowledgeDocument = (id: number) =>
  unwrap(
    client.POST("/api/v1/knowledge/documents/{doc_id}/archive", {
      params: { path: { doc_id: id } },
    }),
  );

export const restoreKnowledgeDocument = (id: number) =>
  unwrap(
    client.POST("/api/v1/knowledge/documents/{doc_id}/restore", {
      params: { path: { doc_id: id } },
    }),
  );

export const reembedKnowledgeDocument = (id: number) =>
  unwrap(
    client.POST("/api/v1/knowledge/documents/{doc_id}/reembed", {
      params: { path: { doc_id: id } },
    }),
  );

// ─── Document images ───────────────────────────────────────────────────────

export const addKnowledgeDocumentImage = (docId: number, formData: FormData) =>
  requestForm(`/api/v1/knowledge/documents/${docId}/images`, "POST", formData);

export const updateKnowledgeDocumentImage = (
  docId: number,
  imgId: number,
  data: Schemas["KnowledgeDocumentImageUpdate"],
) =>
  unwrap(
    client.PATCH("/api/v1/knowledge/documents/{doc_id}/images/{img_id}", {
      params: { path: { doc_id: docId, img_id: imgId } },
      body: data,
    }),
  );

export const deleteKnowledgeDocumentImage = (docId: number, imgId: number) =>
  unwrap(
    client.DELETE("/api/v1/knowledge/documents/{doc_id}/images/{img_id}", {
      params: { path: { doc_id: docId, img_id: imgId } },
    }),
  );
