/** Companion surfaces (kiosk/e-ink devices): heartbeat and the screen test. */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

export const recordCompanionSurfaceHeartbeat = (
  surfaceId: string,
  data: components["schemas"]["CompanionSurfaceHeartbeat"],
) =>
  unwrap(
    client.POST("/api/v1/companion-surfaces/{surface_id}/heartbeat", {
      params: { path: { surface_id: surfaceId } },
      body: data,
    }),
  );

/** Wake one registered screen and chime, so a caregiver can see which screen it is. */
export const runCompanionSurfaceTest = (
  surfaceId: string,
  data: components["schemas"]["CompanionSurfaceTestIn"] = { microphone: false },
) =>
  unwrap(
    client.POST("/api/v1/companion-surfaces/{surface_id}/test", {
      params: { path: { surface_id: surfaceId } },
      body: data,
    }),
  );
