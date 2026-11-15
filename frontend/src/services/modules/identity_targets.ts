/**
 * The household members an identity decision may name.
 *
 * One list behind every identity decision in the admin UI: track and keyframe corrections, ReID
 * relabels, visitor attribution, and face calibration labels. Read it through the
 * `identityTargets` store, not directly.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

export type IdentityTarget = components["schemas"]["IdentityTargetOut"];

export const getIdentityTargets = () => unwrap(client.GET("/api/v1/identity/targets", {}));
