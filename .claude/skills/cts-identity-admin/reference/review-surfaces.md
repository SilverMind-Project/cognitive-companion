# Identity Review Surfaces and Shared Review Pieces

Part of the `cts-identity-admin` skill; the rules summary is in `../SKILL.md`.

## Visitor review surface

A dedicated review surface exists for unmatched face clusters (`visitors.review` token required).
The UI connects to the BFF's visitor endpoints, not the ReID endpoints. It displays cross-visit
clusters (seen on >= 3 distinct days within 30 days). Most are often faces of someone already
enrolled, so the first action is "Someone enrolled": attribute the clusters to an existing member
(`POST /api/v1/visitors/clusters/review`, `is_member`), which never touches enrollment. "Someone
new" names a cluster (creates a guest `HouseholdMember` and enrolls its faces), and is blocked when
the person already exists. Dismiss closes a cluster. Decisions apply to one cluster or a selection,
through one batch call with per-item results.

## Shared identity review pieces

Every surface where an operator says who a face, body, or track belongs to converges on the same
pieces. Visitors, Face calibration, and the ReID Review Queue use all of them; track corrections
keep their own workflow. New review code uses them too:

- Targets: the `identityTargets` store over `GET /api/v1/identity/targets` and
  `IdentityTargetPicker` (`require-enrolled-face` disables members without enrolled faces). Never
  load the household list another way.
- Verdicts: `backend/schemas/identity_review.py` (`is_member`, `new_person`, `not_enrolled`,
  `not_usable`); labels and keys in `frontend/src/constants/identityReview.ts`.
- Effects: `backend/services/identity_review/vocabulary.py` states what each verdict changes on
  each surface, once. The browser reads it through the `identityReview` store
  (`GET /api/v1/identity/review-vocabulary`) and previews it before a decision; batch responses
  report the same sentence. Never write an effect sentence in the frontend.
- One subject at a time: `ReviewVerdictBar` (numbered members, the server's other verdicts with
  their keys, the surface's guarantee underneath) and `useReviewKeys` (1 to 9 a member, `n` not in
  the household, `x` not usable, arrows to move). A member decision that grants authority (ReID
  approval) still goes through a confirm, by key or click. Face calibration highlights no member:
  its labels are ground truth.
- Several at once: `ReviewSelectionToolbar` (Select several, Select all, count, Clear, the
  surface's decisions in its slot), then a confirm that states the effect, then one batch call.
- Batch results: `BatchReviewResponse` (`{id, ok, error_code}` per item, the server's `effect`);
  the browser reports them with `batchReviewNotices` and drops `appliedIds` from its selection.
- One backend path: every batch review route calls
  `IdentityReviewRegistry.decide` (`backend/services/identity_review/registry.py`), which checks
  the verdict, the one-at-a-time rule, and the target once, then hands the decision to the
  surface's `ReviewSubjectAdapter` (`VisitorReviewAdapter`, `FaceCalibrationReviewAdapter`,
  `ReIDReviewAdapter`). A new review surface adds its verdicts to `vocabulary.py` and registers
  an adapter in `backend/bootstrap/cts.py::wire_identity_services`; it never validates targets or
  writes effect text itself. Track corrections stay outside the registry (revision ranges and
  projection acknowledgements are their own governance).
- Every confirm states what the decision changes, especially that no review action except naming
  a new person changes enrollment.
- The readiness page lists every review queue with its waiting count (`review_queues`).

## Face calibration review surface

`/admin/face-calibration` (People, Face Calibration) labels the faces person-id samples for
household calibration. It is a biometric-admin surface, separate from visitor review:

- Every BFF route under `/api/v1/face-calibration` requires the strict token
  `face_calibration.review` (granted to `caregiver_admin` only). Do not widen it to a caregiver
  role or fold it into `visitors.review`.
- The labeler recorded on a label is `actor_from_auth(auth)`, never a client-supplied field.
- Batch labeling (`POST /api/v1/face-calibration/candidates/review`, person-id `label-batch`)
  accepts only `not_enrolled` and `not_usable` (stored as `not_a_face`). A member label is a
  genuine pair in the calibration fit, so it is given one face at a time.
- person-id returns MinIO crop keys, never URLs. `backend/routers/face_calibration.py` presigns
  them per request into `crop_url` with the same `MinioClient` and one-hour TTL the visitor routes
  use; the key itself is never sent to the browser, and neither is an embedding.
- MCP exposes only the read-only `get_face_calibration_summary` (labeling progress). Labeling,
  rejecting, deleting, and promoting are BFF-only; an agent never labels or promotes biometric data.
- A label never changes the gallery; only explicit promotion, an operator action, does. Labels for
  `member` must name an identity that is enrolled in person-id (422 otherwise); `not_enrolled`
  (visitors, relatives) is the label the open-set gate needs most, so the UI keeps it one key away
  (`n`). Explicit promotion (`POST /api/v1/face-calibration/candidates/{candidate_id}/promote`,
  requiring `face_calibration.review`, actor from `actor_from_auth(auth)`) is only offered on
  labeled `member` captures that pass server-side eligibility checks, goes through `useConfirm`
  stating that calibrated recognition authority pauses for that member until the next fit, and
  advances `gallery_revision`.
- Per-member pose-binned face prototypes are managed at `GET /api/v1/persons/{person_id}/prototypes`
  (`face_prototypes:read`, caregiver and caregiver_admin, presigned `crop_url` only) and
  `POST /api/v1/persons/{person_id}/prototypes/rebuild` /
  `DELETE /api/v1/persons/{person_id}/prototypes/{prototype_id}` (`face_prototypes:write`,
  caregiver_admin only). Removing a prototype deletes its underlying embedding(s), bumps
  `gallery_revision`, and goes through `useConfirm`.
- Delete removes the row and its crop in person-id and goes through `useConfirm` (if the capture
  was already promoted, its promoted embedding stays in the gallery while the thumbnail reference
  is cleared).

Wearable-attested faces are a third mode of the same page ("Attested faces",
`AttestedFacesPanel` with `useAttestedFaceAudit`): faces a wearable association labeled in
person-id (`label_state = attested`). They never enter the labeling queue. The operator judges a
uniform random sample the server draws (`GET /api/v1/face-calibration/attestations/audit-sample`;
keys `c` right person, `w` wrong person, `x` not a face), sees the audit summary and whether the
precision bar is met (server-computed), and may promote one face at a time through the same
promote route and a confirm that asks to check the person. The auditor is
`actor_from_auth(auth)`; every route uses `face_calibration.review`.

Required tests: router permission and presign tests, the person-id client envelope tests (502 on
a malformed upstream), the MCP/BFF parity test for the summary, and composable and view tests for
keyboard labeling, a failed label keeping the capture, load errors with retry, a 403 shown as the
forbidden state (no queue, no retry), confirm-before-delete, and the empty queue.
