/**
 * Face calibration review.
 *
 * Proxies person-identification-service's calibration capture set through the CC BFF: sampled
 * faces from the household's cameras that an operator labels so raw similarity can be calibrated
 * into a match probability. Crops arrive as presigned URLs; embeddings never reach the browser.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export type CalibrationCandidateView = Schemas["CalibrationCandidateView"];
export type FaceCalibrationSummary = Schemas["FaceCalibrationSummaryEnvelope"];
export type CalibrationLabel = Schemas["LabelCalibrationCandidateRequest"];
export type CalibrationBatchReview = Schemas["FaceCalibrationReviewRequest"];
export type PersonPrototypeView = Schemas["PersonPrototypeView"];
export type PersonPrototypesResponse = Schemas["PersonPrototypesResponse"];
export type CalibrationState = "unlabeled" | "labeled" | "rejected";

export const listCalibrationCandidates = (
  state: CalibrationState,
  cursor?: string | null,
  limit = 50,
) =>
  unwrap(
    client.GET("/api/v1/face-calibration/candidates", {
      params: { query: { state, limit, ...(cursor ? { cursor } : {}) } },
    }),
  );

export const labelCalibrationCandidate = (candidateId: string, body: CalibrationLabel) =>
  unwrap(
    client.POST("/api/v1/face-calibration/candidates/{candidate_id}/label", {
      params: { path: { candidate_id: candidateId } },
      body,
    }),
  );

export const rejectCalibrationCandidate = (candidateId: string) =>
  unwrap(
    client.POST("/api/v1/face-calibration/candidates/{candidate_id}/reject", {
      params: { path: { candidate_id: candidateId } },
    }),
  );

export const deleteCalibrationCandidate = (candidateId: string) =>
  unwrap(
    client.DELETE("/api/v1/face-calibration/candidates/{candidate_id}", {
      params: { path: { candidate_id: candidateId } },
    }),
  );

export const getFaceCalibrationSummary = () =>
  unwrap(client.GET("/api/v1/face-calibration/summary", {}));

/** Label several captures not in the household or not usable; member labels go one at a time. */
export const reviewCalibrationCandidates = (body: CalibrationBatchReview) =>
  unwrap(client.POST("/api/v1/face-calibration/candidates/review", { body }));

/** Explicitly promote one labeled member capture into that person's face gallery. */
export const promoteCalibrationCandidate = (candidateId: string) =>
  unwrap(
    client.POST("/api/v1/face-calibration/candidates/{candidate_id}/promote", {
      params: { path: { candidate_id: candidateId } },
    }),
  );

export const listPersonPrototypes = (personId: string) =>
  unwrap(
    client.GET("/api/v1/persons/{person_id}/prototypes", {
      params: { path: { person_id: personId } },
    }),
  );

export const rebuildPersonPrototypes = (personId: string) =>
  unwrap(
    client.POST("/api/v1/persons/{person_id}/prototypes/rebuild", {
      params: { path: { person_id: personId } },
    }),
  );

export const deletePersonPrototype = (personId: string, prototypeId: string) =>
  unwrap(
    client.DELETE("/api/v1/persons/{person_id}/prototypes/{prototype_id}", {
      params: { path: { person_id: personId, prototype_id: prototypeId } },
    }),
  );
