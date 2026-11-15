/**
 * Identity setup readiness.
 *
 * One read-only BFF call that says, for this household, which link of the identity chain is
 * broken (roster, camera ingest, floor frame, capture, labeling, calibration artifact, face
 * policy, templates, body-appearance gallery) and the next action for each step.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export type IdentityReadiness = Schemas["IdentityReadinessEnvelope"];
export type ReadinessStep = Schemas["ReadinessStep"];

export const getIdentityReadiness = () => unwrap(client.GET("/api/v1/identity/readiness", {}));
