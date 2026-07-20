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

Identity selectors use one BFF correction-target endpoint backed by active household members.
Gallery contents are metadata, never eligibility. The endpoint must continue to return household
members when the ReID gallery is empty.

API failures are visible. Never silently catch both identity sources and render an empty selector.
Provide loading, error, retry, empty, and permission-denied states.

`Set to Unknown` is an explicit action. An empty selection is not a correction.

## Shared correction workflow

Keyframes and the Person Hypothesis inspector use one reusable correction workflow and one BFF
service contract.

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

### Authority-to-badge mapping (M07)

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
| `none` | no badge (deferred — `sourceBadge()` still falls back to the `decision_source` string rather than rendering nothing; the F9 leak-prevention property holds either way since `decision_source` is itself a bounded value, never an identity id) |
| `unknown` / `height_proxy` / `reid_gallery` | not handled as distinct cases; falls through to the `decision_source` string like `none` above. Never emitted by the current producer, so this is dormant, not untested-in-practice. |

Never render an `authority` string verbatim as a person label — that was the F9 bug
(`authority: "amma"`). `IdentityRevisionRange.authority` (`RevisionAuthority`: `operator | inferred`)
is a distinct vocabulary from decision `authority` and must not be normalized through the same
fallback path.

The detail overlay labels every bbox with effective identity, source, and confidence/`Verified`.
Use stable identity colors plus distinct unknown and conflict styling. Color is not the only signal.
Clicking a bbox opens the shared correction workflow.

Filtering, identity aggregation, and pagination are server-side. Filter options come from the
authoritative correction-target endpoint, not the current result page.

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

Actions are `Approve`, `Reject`, `Relabel`, and `Demote`. No bulk approval. Batch rejection is
allowed for obvious low-quality candidates. Approval/relabel/reject act on a row in
`pending_review` or `auto_verified` (an `auto_verified` row is machine-trusted but still fully
operator-governable); demote acts only on `auto_verified` and returns it to `pending_review`
without touching its embedding, unlike reject. Approval/relabel require individual visual review.
The frontend never derives which states are reviewable or what demote/undo restore to; it renders
the server's `eligible`/`reasons` and the row's current `state` as returned.

Use the existing blur behavior and a blur toggle consistent with other CTS pages. Respect auth and
never reveal unblurred media to an unauthorized user.

## Component and composable boundaries

Required shared ownership:

- one BFF service module for identity targets, segment proposals, revisions, and review actions;
- one correction composable returning `{ state, actions }`;
- one correction component used by both Keyframes and PH inspector;
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
- component tests proving Keyframes and PH inspector use the same correction component;
- keyframe card tests with two identities, duplicate identity counts, unknown, conflict, operator,
  uncalibrated ArcFace, and pending review;
- detail overlay tests for all bboxes and click-to-correct;
- selector tests with empty gallery but populated household identities;
- review queue permission, blur, approve/reject/relabel/demote, and no-bulk-approval tests;
- server-side filter and pagination tests;
- responsive visual checks at desktop and mobile widths;
- full build and test suite with zero Vue warnings or console errors.

## Review checklist

- [ ] One correction workflow, not separate Keyframe and PH implementations.
- [ ] No client-derived confidence or authority.
- [ ] Identity targets are independent from the ReID gallery.
- [ ] Every bbox and every effective identity is visible.
- [ ] Original inference remains available in details.
- [ ] Operator corrections show `Verified`.
- [ ] Raw ArcFace similarity is details-only and never formatted as confidence.
- [ ] Permission and blur behavior are explicit and tested.
- [ ] Server-side aggregation avoids N+1 calls.
