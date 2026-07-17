/**
 * Room occupancy from the unified read-model.
 *
 * Note the param handling: the previous client built `?room_name=${roomName}` by raw
 * interpolation, so any room whose name contained a space or `&` produced a wrong request.
 * The typed client encodes it.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

export type RoomOccupancyStateEnvelope = components["schemas"]["RoomOccupancyStateEnvelope"];

export const getOccupancy = (roomName?: string) =>
  unwrap(
    client.GET("/api/v1/occupancy/", {
      params: { query: roomName ? { room_name: roomName } : {} },
    }),
  );
