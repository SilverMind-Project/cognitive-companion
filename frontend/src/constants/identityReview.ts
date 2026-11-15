/**
 * The words and keys every identity review surface uses for the same decisions.
 *
 * Presentation only: what a decision changes is the server's sentence, read through the
 * `identityReview` store, never written here. Each surface accepts only the verdicts the server
 * lists for it.
 */

import type { components } from "@/generated/api-types";
import type { ReviewSurface, ReviewVerdict } from "@/services/modules/identity_targets";

export type { ReviewVerdict };

/** Button labels for each verdict, the same on every surface. */
export const VERDICT_LABELS: Record<ReviewVerdict, string> = {
  is_member: "Someone enrolled",
  new_person: "Someone new",
  not_enrolled: "Not in the household",
  not_usable: "Not usable",
};

/**
 * Visitors offers one "Dismiss" for both negative verdicts: a dismissed cluster is closed the same
 * way whether it was a stranger or an unusable face, so two buttons would say one thing.
 */
export const VISITOR_DISMISS_LABEL = "Dismiss";

/**
 * The keyboard shortcut for each verdict on a one-at-a-time review surface. A member is chosen
 * with its number (1 to 9) instead of `is_member`'s own key.
 */
export const VERDICT_KEYS: Partial<Record<ReviewVerdict, string>> = {
  not_enrolled: "n",
  not_usable: "x",
};

/** Members reachable by a single number key. */
export const MAX_KEYED_MEMBERS = 9;

const REVIEW_ERROR_LABELS: Record<string, string> = {
  not_found: "no longer exists",
  already_named: "is already named",
  unknown_member: "names someone who is not enrolled",
  not_enrolled_member: "names someone without enrolled faces",
  conflict: "changed since it was loaded",
  upstream_error: "could not be updated",
};

export type BatchReviewResponse = components["schemas"]["BatchReviewResponse"];

/**
 * The notices a batch decision produces: the server's effect when anything applied, and a count
 * with distinct reasons when some subjects could not be updated (never a failed batch).
 */
export function batchReviewNotices(result: BatchReviewResponse): {
  success: string;
  warning: string;
} {
  const reasons = [
    ...new Set(
      result.results
        .filter((r) => !r.ok)
        .map((r) => REVIEW_ERROR_LABELS[r.error_code ?? ""] ?? "could not be updated"),
    ),
  ];
  return {
    success: result.reviewed ? result.effect : "",
    warning: result.failed ? `${result.failed} not updated: ${reasons.join("; ")}.` : "",
  };
}

/** The ids a batch decision applied to, to drop from a selection or queue. */
export function appliedIds(result: BatchReviewResponse): Set<string> {
  return new Set(result.results.filter((r) => r.ok).map((r) => r.id));
}

/** Each review queue: where it lives and what an operator decides there. */
export const REVIEW_QUEUE_PRESENTATION: Record<
  ReviewSurface,
  { title: string; subject: string; to: string }
> = {
  visitors: {
    title: "Visitors",
    subject: "Recurring unrecognized faces: a member's, someone new, or dismiss",
    to: "/admin/visitors",
  },
  face_calibration: {
    title: "Face calibration",
    subject: "Sampled faces labeled for the calibration fit",
    to: "/admin/face-calibration",
  },
  reid_review: {
    title: "ReID Review Queue",
    subject: "Body-appearance samples proposed by a calibrated face match",
    to: "/admin/cts/reid-review",
  },
};
