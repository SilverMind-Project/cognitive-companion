/** Rooms and their zones. */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export type RoomOut = Schemas["RoomOut"];

export const getRooms = () => unwrap(client.GET("/api/v1/rooms", {}));

export const createRoom = (data: Schemas["RoomCreate"]) =>
  unwrap(client.POST("/api/v1/rooms", { body: data }));

export const updateRoom = (id: number, data: Schemas["RoomUpdate"]) =>
  unwrap(client.PUT("/api/v1/rooms/{room_id}", { params: { path: { room_id: id } }, body: data }));

export const deleteRoom = (id: number) =>
  unwrap(client.DELETE("/api/v1/rooms/{room_id}", { params: { path: { room_id: id } } }));

export const listRoomZones = (roomId: number) =>
  unwrap(client.GET("/api/v1/rooms/{room_id}/zones", { params: { path: { room_id: roomId } } }));
