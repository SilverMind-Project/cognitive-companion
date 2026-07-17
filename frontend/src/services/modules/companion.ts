/** Companion surfaces (kiosk/e-ink devices) heartbeat. */

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
