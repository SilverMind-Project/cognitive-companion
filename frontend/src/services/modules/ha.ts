/** Home Assistant sync and entity lookups. */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

export type HaEntityOut = components["schemas"]["HaEntityOut"];

export const syncRooms = () => unwrap(client.POST("/api/v1/ha/sync/rooms", {}));

/** `room_name` was raw-interpolated by the previous client; it is encoded now. */
export const syncSensors = (roomName?: string) =>
  unwrap(
    client.POST("/api/v1/ha/sync/sensors", {
      params: { query: roomName ? { room_name: roomName } : {} },
    }),
  );

export const getHAMediaPlayers = () => unwrap(client.GET("/api/v1/ha/media-players", {}));

export const getHAEntities = (domain?: string) =>
  unwrap(client.GET("/api/v1/ha/entities", { params: { query: domain ? { domain } : {} } }));
