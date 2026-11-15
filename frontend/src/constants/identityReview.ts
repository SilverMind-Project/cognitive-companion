/**
 * The words every identity review surface uses for the same decisions.
 *
 * The server owns what a decision does and reports its effect after it applies; these are the
 * labels and the one-sentence preview shown before the operator confirms. Each surface accepts
 * only the verdicts that make sense for it.
 */

import type { components } from "@/generated/api-types";

export type ReviewVerdict = components["schemas"]["VisitorReviewRequest"]["verdict"] | "new_person";

/** Button labels for each verdict, the same on every surface. */
export const VERDICT_LABELS: Record<ReviewVerdict, string> = {
  is_member: "Someone enrolled",
  new_person: "Someone new",
  not_enrolled: "Not in the household",
  not_usable: "Dismiss",
};

/** What a visitor decision changes, shown before it is confirmed. */
export const VISITOR_EFFECTS: Record<Exclude<ReviewVerdict, "new_person">, string> = {
  is_member:
    "These groups are marked as this member's faces and stop appearing for review. Nothing is " +
    "added to their enrollment, so recognition does not change.",
  not_enrolled:
    "These groups are dismissed and stop appearing for review. Nothing is enrolled anywhere.",
  not_usable:
    "These groups are dismissed and stop appearing for review. Nothing is enrolled anywhere.",
};

export const REVIEW_ERROR_LABELS: Record<string, string> = {
  not_found: "no longer exists",
  already_named: "is already named",
  unknown_member: "names someone who is not enrolled",
  not_enrolled_member: "names someone without enrolled faces",
  upstream_error: "could not be updated",
};
