---
name: cts-identity-admin
description: Use when building Cognitive Companion CTS keyframe identity displays, Person Hypothesis correction workflows, ReID review surfaces, or identity provenance APIs.
---

# CTS Identity Admin

Load this skill together with:

- `/home/sriram/code/nanai/cognitive-companion/.claude/skills/front-end/SKILL.md`
- `/home/sriram/code/nanai/cognitive-companion/.claude/skills/engineering-standards/SKILL.md`
- `/home/sriram/code/nanai/cognitive-companion/.claude/skills/bff-api-design/SKILL.md`
- `/home/sriram/code/nanai/continuous-tracking/.claude/skills/cts-identity-governance/SKILL.md`

This skill defines the BFF and admin UX rules for governed CTS identity. It does not redefine the
global design system; the front-end skill remains authoritative for layout, tokens, accessibility,
Vuetify components, testing, and responsive behavior.

## Server-owned semantics

The frontend never derives identity authority, confidence, conflict state, correction boundaries,
or gallery eligibility. The BFF returns server-computed values from validated models.

Use explicit fields: `inferred_identity_id`, `effective_identity_id`, `authority`,
`decision_source`, `revision_id`, `conflict`, and `evidence_summary`.

Do not overload `person_id`. Do not convert raw similarity into a percentage. Operator corrections
display `Verified`, not a fabricated numeric confidence.

## Authoritative correction targets

Identity selectors use one BFF target endpoint, `GET /api/v1/identity/targets` (through the
`identityTargets` store), backed by active household members; it answers whether or not CTS is
enabled.
Gallery contents are metadata, never eligibility. The endpoint must continue to return household
members when the ReID gallery is empty.

API failures are visible. Never silently catch both identity sources and render an empty selector.
Provide loading, error, retry, empty, and permission-denied states.

`Set to Unknown` is an explicit action. An empty selection is not a correction.

## Shared correction workflow

Keyframes, the Person Hypothesis inspector, and the Live view use one reusable correction workflow
(`IdentityCorrectionWorkflow`) and one BFF service contract. The Live view opens it from a clicked
detection with the frame's `event_time` as the anchor and `source_view: "live_view"`.

The workflow supports:

- frame-only identity correction;
- proposed observation-bounded PH segment correction;
- caregiver adjustment at observation boundaries with timestamps and thumbnails;
- proposed boundaries at association discontinuities or authoritative anchors;
- hard stops at split, merge, and operator-revision boundaries;
- reasons `wrong_person`, `identity_uncertain`, `track_handoff`, `duplicate_hypothesis`,
  `bad_bbox`, and `other`, with an optional note;
- stale version rejection and proposal refresh;
- separate optional `Verify ReID crop` action only when server quality gates pass;
- asynchronous revision status and downstream projection acknowledgements.

Default scope:

- From a keyframe bbox: frame-only, with the proposed segment as an explicit alternative.
- From the PH inspector with a selected observation: its proposed bounded segment.
- From the PH inspector without a selected observation: current effective segment, requiring range
  review before submission.
- From the Live view: the proposed segment around the clicked frame.

Identity and bbox geometry corrections share an audit envelope but are separate revision types.

## Keyframe presentation

One card represents one physical source frame, even when multiple PHs triggered sampling.

The card receives one batched server summary and shows:

- every unique effective identity with count;
- explicit `Unknown` and conflict counts;
- source badges `ArcFace`, `ArcFace / Uncalibrated`, `ReID`, `Prior`, `Operator`, `Conflict`;
- final calibrated decision confidence, or `Verified` for operator authority;
- pending-review indicator when applicable.

The card shows only effective identity after correction. The detail dialog shows original inference
and revision history.

### Authority-to-badge mapping

`authority` is the bounded `IdentityAuthority` vocabulary produced by CTS
(`operator | direct_face | posterior | temporal_prior | none`, plus `reid_gallery` reserved for a
future governed-gallery rung, and `unknown` / `height_proxy` legacy members the current producer
never emits); it is never an identity id. The badge formatter
(`frontend/src/components/cts/identity/identityEvidence.js`, mirrored in
`backend/services/cts/keyframe_read_service.py::_source_badge`) maps it, not `decision_source`
alone:

| `authority` | Badge |
| --- | --- |
| `operator` | `Verified` |
| `direct_face` | calibrated-face badge (`ArcFace`) |
| `posterior` | face/ReID badge, chosen by `decision_source` |
| `temporal_prior` | `Prior` |
| `none` | no badge (deferred: `sourceBadge()` still falls back to the `decision_source` string rather than rendering nothing; the F9 leak-prevention property holds either way since `decision_source` is itself a bounded value, never an identity id) |
| `unknown` / `height_proxy` / `reid_gallery` | not handled as distinct cases; falls through to the `decision_source` string like `none` above. Never emitted by the current producer, so this is dormant, not untested-in-practice. |

Never render an `authority` string verbatim as a person label; that was the F9 bug
(`authority: "amma"`). `IdentityRevisionRange.authority` (`RevisionAuthority`: `operator | inferred`)
is a distinct vocabulary from decision `authority` and must not be normalized through the same
fallback path.

The detail overlay labels every bbox with effective identity, source, and confidence/`Verified`.
Use stable identity colors plus distinct unknown and conflict styling. Color is not the only signal.
Clicking a bbox opens the shared correction workflow.

Filtering, identity aggregation, and pagination are server-side. Filter options come from the
authoritative target endpoint (`GET /api/v1/identity/targets`), not the current result page.

## ReID review queue

The queue requires `cts.identity.gallery_review`, separate from `cts.identity.correct`.

Each item shows:

- body crop and full frame with bbox;
- nearby observations in the same PH segment;
- proposed identity and ArcFace evidence;
- quality, orientation, camera, timestamp, model/preprocessing version;
- source PH, observation, keyframe, and correction links;
- a state chip visually distinct for all four lifecycle states (`pending_review`, `auto_verified`,
  `operator_verified`, `rejected`; identity-continuity M02 added `auto_verified`), and a state
  filter option covering all four.

Actions are `Approve`, `Reject`, `Relabel`, and `Demote`, offered through the shared verdict bar:
choosing the proposed member approves, choosing another relabels, "Not in the household" rejects as
`wrong_person`, and "Not usable" rejects with a chosen reason code. No bulk approval. Batch rejection is
allowed (`POST /api/v1/cts/identity/reid-review/review`, verdict `not_enrolled` or `not_usable`
with its reason, per-item `base_audit_version`, `BatchReviewResponse` with `conflict` for a sample
that moved). Approval/relabel/reject act on a row in
`pending_review` or `auto_verified` (an `auto_verified` row is machine-trusted but still fully
operator-governable); demote acts only on `auto_verified` and returns it to `pending_review`
without touching its embedding, unlike reject. Approval/relabel require individual visual review.
The frontend never derives which states are reviewable or what demote/undo restore to; it renders
the server's `eligible`/`reasons` and the row's current `state` as returned.

Use the existing blur behavior and a blur toggle consistent with other CTS pages. Respect auth and
never reveal unblurred media to an unauthorized user.

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
pieces; the design and its phases are
`/home/sriram/code/nanai/identity-recognition-s06-unified-identity-review.md`. Visitors, Face
calibration, and the ReID Review Queue use all of them; track corrections keep their own workflow.
New review code uses them too:

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
  an adapter in `bootstrap/cts.py::wire_identity_services`; it never validates targets or writes
  effect text itself. Track corrections stay outside the registry (revision ranges and
  projection acknowledgements are their own governance).
- Every confirm states what the decision changes, especially that no review action except naming
  a new person changes enrollment.
- The readiness page lists every review queue with its waiting count (`review_queues`).

## Face calibration review surface

`/admin/face-calibration` (People, Face Calibration) labels the faces person-id samples for
household calibration. It is a biometric-admin surface, separate from visitor review:

- Every BFF route under `/api/v1/face-calibration` requires the strict token
  `face_calibration.review` (granted to `caregiver_admin` only). Do not widen it to a caregiver
  role or fold it into `cts.identity.visitors.review`.
- The labeler recorded on a label is `actor_from_auth(auth)`, never a client-supplied field.
- Batch labeling (`POST /api/v1/face-calibration/candidates/review`, person-id
  `label-batch`) accepts only `not_enrolled` and `not_usable` (stored as `not_a_face`). A member
  label is a genuine pair in the calibration fit, so it is given one face at a time.
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

Required tests: router permission and presign tests, the person-id client envelope tests (502 on
a malformed upstream), the MCP/BFF parity test for the summary, and composable and view tests for
keyboard labeling, a failed label keeping the capture, load errors with retry, a 403 shown as the
forbidden state (no queue, no retry), confirm-before-delete, and the empty queue.

## Who did it

Every review, correction, visitor, or approval action records its actor with
`actor_from_auth(auth)` (`backend/core/auth.py`) on the `AuthContext` the route received from
`require_permission` or `require_token`: the API key's name. Never read `request.state`, never
accept an actor from the request body, and never fall back to a placeholder such as "system".

## Identity setup readiness

`/admin/identity-setup` (`IdentityReadinessView`) is the one status surface for the identity
chain: enroll, capture, label, fit and deploy, calibrated faces, body samples, review, vote.
Identity admin pages link to it instead of explaining the chain themselves, and a new step joins
`IdentityReadinessService` (`backend/services/identity_readiness_rules.py`) instead of becoming a
new panel. The server decides every state and next action; `constants/identityReadiness.ts` only
words them. A page that shows a readiness hint must work when readiness fails to load.

## Component and composable boundaries

Required shared ownership:

- one BFF service module for identity targets, segment proposals, revisions, and review actions;
- one correction composable returning `{ state, actions }`;
- one correction component used by Keyframes, the PH inspector, and the Live view;
- one evidence badge component and formatter;
- one bbox overlay component or composable for identity presentation;
- one correction-job status component.

Views coordinate these modules; they do not duplicate request or identity-resolution logic.

## Required states and accessibility

Every async surface implements loading, empty, partial, error, stale-version, forbidden, and retry
states. Icon buttons use familiar icons and tooltips. Dialogs and drawers trap focus, restore focus
on close, expose accessible labels, and support keyboard operation.

Use design tokens and semantic Vuetify colors from the front-end skill. Do not create nested cards,
custom color systems, oversized headings, or marketing-style composition in the operational admin
UI.

## Required tests

- service contract tests for correction targets and explicit identity fields;
- composable tests for loading, stale proposal refresh, validation, async job states, and errors;
- component tests proving Keyframes, the PH inspector, and the Live view use the same correction
  component;
- keyframe card tests with two identities, duplicate identity counts, unknown, conflict, operator,
  uncalibrated ArcFace, and pending review;
- detail overlay tests for all bboxes and click-to-correct;
- selector tests with empty gallery but populated household identities;
- review queue permission, blur, approve/reject/relabel/demote, and no-bulk-approval tests;
- server-side filter and pagination tests;
- responsive visual checks at desktop and mobile widths;
- full build and test suite with zero Vue warnings or console errors.

## Review checklist

- [ ] One correction workflow, not separate Keyframe, PH, and Live implementations.
- [ ] No client-derived confidence or authority.
- [ ] Identity targets are independent from the ReID gallery.
- [ ] Every bbox and every effective identity is visible.
- [ ] Original inference remains available in details.
- [ ] Operator corrections show `Verified`.
- [ ] Raw ArcFace similarity is details-only and never formatted as confidence.
- [ ] Permission and blur behavior are explicit and tested.
- [ ] Server-side aggregation avoids N+1 calls.
