/**
 * Presentation for the identity readiness steps: titles, where each sits in the identity chain,
 * and what each server-chosen next action says and links to. The server decides every state and
 * action; this file only words them. An action with no `to` is a configuration change made
 * outside the admin UI on purpose (it needs a restart), so the copy says what to change.
 */

import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];
export type ReadinessStepKey = Schemas["ReadinessStep"]["key"];
export type ReadinessNextAction = Schemas["ReadinessStep"]["next_action"];
export type ReadinessState = Schemas["ReadinessStep"]["state"];

/** The chain has eight links; the face calibration page is link 3. */
export const IDENTITY_CHAIN_LENGTH = 8;

export interface StepPresentation {
  title: string;
  /** Link numbers in the eight-link chain; empty for a prerequisite outside the chain. */
  chain: number[];
}

export const STEP_PRESENTATION: Record<ReadinessStepKey, StepPresentation> = {
  ingest: { title: "Cameras deliver frames", chain: [] },
  floor_frame: { title: "Floor plan, rooms, and camera calibration", chain: [] },
  roster: { title: "Enroll everyone", chain: [1] },
  capture: { title: "Capture face crops", chain: [2] },
  labeling: { title: "Label the captures (Face calibration)", chain: [3] },
  artifact: { title: "Fit and deploy the calibration artifact", chain: [4] },
  face_policy: { title: "Calibrated face evidence: shadow, then live", chain: [5] },
  templates: { title: "Face templates (optional)", chain: [] },
  body_gallery: {
    title: "Body-appearance samples: proposed, reviewed, voting",
    chain: [6, 7, 8],
  },
};

export const PREREQUISITE_KEYS: ReadinessStepKey[] = ["ingest", "floor_frame"];

export interface ActionPresentation {
  text: string;
  to?: string;
}

export const ACTION_PRESENTATION: Record<ReadinessNextAction, ActionPresentation> = {
  none: { text: "" },
  enroll_members: {
    text: "List and enroll every person who lives in or regularly visits the house",
    to: "/admin/persons",
  },
  review_visitors: { text: "Name or dismiss recurring visitors", to: "/admin/visitors" },
  fix_camera_ingest: { text: "Check the cameras", to: "/admin/cts/cameras" },
  upload_floor_plan: {
    text: "Upload the floor plan and set its scale",
    to: "/admin/tracking?panel=live-floor",
  },
  draw_room_polygons: {
    text: "Draw every room on the floor plan",
    to: "/admin/tracking?panel=live-floor",
  },
  calibrate_cameras: { text: "Calibrate the cameras", to: "/admin/cts/calibration" },
  enable_capture: {
    text: "Set calibration_capture.enabled to true in the person identification settings and redeploy it",
  },
  label_captures: { text: "Label captured faces", to: "/admin/face-calibration" },
  fit_and_deploy_artifact: {
    text: "Fit, validate, and mount the calibration artifact with the person identification calibration tools",
  },
  refit_artifact: {
    text: "Refit the calibration artifact so it covers everyone enrolled since the last fit",
  },
  review_shadow: {
    text: "Review the shadow results, then change the tracking orchestrator setting",
  },
  set_policy_calibrated: {
    text: "Set face_id.evidence_policy to calibrated in the tracking orchestrator after the shadow review",
  },
  enable_templates: { text: "Review the template shadow results, then set face_templates.mode" },
  review_body_samples: { text: "Review body-appearance samples", to: "/admin/cts/reid-review" },
  check_service: { text: "Check that the service is running" },
};

export const STATE_PRESENTATION: Record<ReadinessState, { label: string; color?: string }> = {
  ready: { label: "Ready", color: "success" },
  attention: { label: "Needs attention", color: "warning" },
  blocked: { label: "Blocked", color: "error" },
  unknown: { label: "Unknown" },
};
