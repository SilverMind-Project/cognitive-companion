/**
 * A review vocabulary as the server serves it, for specs that render effect previews.
 *
 * The sentences are deliberately not the real ones: a spec that finds them on the page proves the
 * page shows the server's words rather than a copy of its own.
 */

import type { ReviewVocabulary } from "@/services/modules/identity_targets";

const PLACEHOLDER = "{member}";

export const REVIEW_VOCABULARY: ReviewVocabulary = {
  member_placeholder: PLACEHOLDER,
  surfaces: [
    {
      surface: "visitors",
      guarantee: "Server: only naming changes enrollment.",
      verdicts: [
        {
          verdict: "is_member",
          effect: `Server: marked as ${PLACEHOLDER}'s faces; nothing added to ${PLACEHOLDER}'s enrollment.`,
          needs_target: true,
          needs_enrolled_face: true,
          batch: true,
        },
        {
          verdict: "new_person",
          effect: "Server: a new person is enrolled.",
          needs_target: false,
          needs_enrolled_face: false,
          batch: false,
        },
        {
          verdict: "not_enrolled",
          effect: "Server: dismissed, nothing enrolled.",
          needs_target: false,
          needs_enrolled_face: false,
          batch: true,
        },
        {
          verdict: "not_usable",
          effect: "Server: dismissed, nothing enrolled.",
          needs_target: false,
          needs_enrolled_face: false,
          batch: true,
        },
      ],
    },
    {
      surface: "face_calibration",
      guarantee: "Server: labels feed only the calibration fit.",
      verdicts: [
        {
          verdict: "is_member",
          effect: `Server: labeled as ${PLACEHOLDER}.`,
          needs_target: true,
          needs_enrolled_face: true,
          batch: false,
        },
        {
          verdict: "not_enrolled",
          effect: "Server: labeled as outside the household.",
          needs_target: false,
          needs_enrolled_face: false,
          batch: false,
        },
        {
          verdict: "not_usable",
          effect: "Server: left out of the fit.",
          needs_target: false,
          needs_enrolled_face: false,
          batch: false,
        },
      ],
    },
    {
      surface: "reid_review",
      guarantee: "Server: body samples never change face enrollment.",
      verdicts: [
        {
          verdict: "is_member",
          effect: `Server: verified as ${PLACEHOLDER}.`,
          needs_target: true,
          needs_enrolled_face: false,
          batch: false,
        },
        {
          verdict: "not_enrolled",
          effect: "Server: rejected as the wrong person.",
          needs_target: false,
          needs_enrolled_face: false,
          batch: true,
        },
        {
          verdict: "not_usable",
          effect: "Server: rejected as unusable.",
          needs_target: false,
          needs_enrolled_face: false,
          batch: true,
        },
      ],
    },
  ],
};

/** A `vi.mock` factory body for `@/services/modules/identity_targets` serving this vocabulary. */
export function identityTargetsModuleMock(targets: unknown[] = []) {
  return {
    getIdentityTargets: () =>
      Promise.resolve({ targets, enrollment_available: true, gallery_available: true }),
    getReviewVocabulary: () => Promise.resolve(REVIEW_VOCABULARY),
  };
}
