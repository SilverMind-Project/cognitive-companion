/** Quizzes and their questions: caregiver-approved, delivered to the senior by voice + buttons. */

import { client, requestForm, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type QuizOut = Schemas["QuizOut"];
export type QuizListOut = Schemas["QuizListOut"];
export type QuizQuestionOut = Schemas["QuizQuestionOut"];

type ListParams = operations["list_quizzes"]["parameters"]["query"];

export const getQuizzes = (params: ListParams = {}) =>
  unwrap(client.GET("/api/v1/quizzes", { params: { query: params } }));

export const getQuiz = (id: number) =>
  unwrap(client.GET("/api/v1/quizzes/{quiz_id}", { params: { path: { quiz_id: id } } }));

export const createQuiz = (data: Schemas["QuizCreate"]) =>
  unwrap(client.POST("/api/v1/quizzes", { body: data }));

export const updateQuiz = (id: number, data: Schemas["QuizUpdate"]) =>
  unwrap(
    client.PATCH("/api/v1/quizzes/{quiz_id}", { params: { path: { quiz_id: id } }, body: data }),
  );

export const deleteQuiz = (id: number) =>
  unwrap(client.DELETE("/api/v1/quizzes/{quiz_id}", { params: { path: { quiz_id: id } } }));

export const approveQuiz = (id: number) =>
  unwrap(client.POST("/api/v1/quizzes/{quiz_id}/approve", { params: { path: { quiz_id: id } } }));

export const archiveQuiz = (id: number) =>
  unwrap(client.POST("/api/v1/quizzes/{quiz_id}/archive", { params: { path: { quiz_id: id } } }));

export const restoreQuiz = (id: number) =>
  unwrap(client.POST("/api/v1/quizzes/{quiz_id}/restore", { params: { path: { quiz_id: id } } }));

// ─── Questions ─────────────────────────────────────────────────────────────

export const createQuizQuestion = (quizId: number, data: Schemas["QuizQuestionCreate"]) =>
  unwrap(
    client.POST("/api/v1/quizzes/{quiz_id}/questions", {
      params: { path: { quiz_id: quizId } },
      body: data,
    }),
  );

export const updateQuizQuestion = (
  quizId: number,
  qid: number,
  data: Schemas["QuizQuestionUpdate"],
) =>
  unwrap(
    client.PATCH("/api/v1/quizzes/{quiz_id}/questions/{qid}", {
      params: { path: { quiz_id: quizId, qid } },
      body: data,
    }),
  );

export const deleteQuizQuestion = (quizId: number, qid: number) =>
  unwrap(
    client.DELETE("/api/v1/quizzes/{quiz_id}/questions/{qid}", {
      params: { path: { quiz_id: quizId, qid } },
    }),
  );

export const reorderQuizQuestions = (
  quizId: number,
  items: Schemas["QuizQuestionReorder"]["items"],
) =>
  unwrap(
    client.POST("/api/v1/quizzes/{quiz_id}/questions/reorder", {
      params: { path: { quiz_id: quizId } },
      body: { items },
    }),
  );

export const setQuizQuestionImage = (quizId: number, qid: number, formData: FormData) =>
  requestForm(`/api/v1/quizzes/${quizId}/questions/${qid}/image`, "PUT", formData);

export const deleteQuizQuestionImage = (quizId: number, qid: number) =>
  unwrap(
    client.DELETE("/api/v1/quizzes/{quiz_id}/questions/{qid}/image", {
      params: { path: { quiz_id: quizId, qid } },
    }),
  );

// ─── LLM suggestions ───────────────────────────────────────────────────────

export const suggestQuiz = (
  documentId: number,
  numQuestions?: number,
  mix?: string,
  modelId?: string,
) =>
  unwrap(
    client.POST("/api/v1/quizzes/suggest", {
      params: {
        query: {
          document_id: documentId,
          ...(numQuestions ? { num_questions: numQuestions } : {}),
          ...(mix ? { mix } : {}),
          ...(modelId ? { model_id: modelId } : {}),
        },
      },
    }),
  );

export const suggestQuizVoiceInstruction = (
  documentId: number,
  resourceType?: string,
  modelId?: string,
) =>
  unwrap(
    client.POST("/api/v1/quizzes/voice-instruction-suggest", {
      params: {
        query: {
          document_id: documentId,
          ...(resourceType ? { resource_type: resourceType } : {}),
          ...(modelId ? { model_id: modelId } : {}),
        },
      },
    }),
  );

export const regenerateQuizQuestion = (quizId: number, qid: number, modelId?: string) =>
  unwrap(
    client.POST("/api/v1/quizzes/{quiz_id}/questions/{qid}/regenerate", {
      params: {
        path: { quiz_id: quizId, qid },
        query: modelId ? { model_id: modelId } : {},
      },
    }),
  );
