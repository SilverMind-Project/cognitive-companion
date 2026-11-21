/**
 * Wearable device registry, consented bindings, and fixed RF node API client.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

type Schemas = components["schemas"];

export type WearableDeviceOut = Schemas["WearableDeviceOut"];
export type WearableDeviceCreate = Schemas["WearableDeviceCreate"];
export type WearableDeviceUpdate = Schemas["WearableDeviceUpdate"];
export type WearableBindingOut = Schemas["WearableBindingOut"];
export type WearableBindingCreate = Schemas["WearableBindingCreate"];
export type WearableAssignmentsOut = Schemas["WearableAssignmentsOut"];
export type RfNodeOut = Schemas["RfNodeOut"];
export type RfNodeCreate = Schemas["RfNodeCreate"];
export type RfNodeUpdate = Schemas["RfNodeUpdate"];
export type RfNodeSurveyCheckRequest = Schemas["RfNodeSurveyCheckRequest"];
export type RfNodeSurveyCheckOut = Schemas["RfNodeSurveyCheckOut"];
export type FloorPlanOut = Schemas["FloorPlanOut"];
export type WearableDeviceAssociationsOut = Schemas["WearableDeviceAssociationsOut"];

export const getWearableAssignments = () => unwrap(client.GET("/api/v1/wearables/assignments", {}));

export const createWearableDevice = (body: WearableDeviceCreate) =>
  unwrap(client.POST("/api/v1/wearables/devices", { body }));

export const updateWearableDevice = (deviceId: string, body: WearableDeviceUpdate) =>
  unwrap(
    client.PATCH("/api/v1/wearables/devices/{device_id}", {
      params: { path: { device_id: deviceId } },
      body,
    }),
  );

export const listDeviceBindings = (deviceId: string) =>
  unwrap(
    client.GET("/api/v1/wearables/devices/{device_id}/bindings", {
      params: { path: { device_id: deviceId } },
    }),
  );

export const bindWearableDevice = (deviceId: string, body: WearableBindingCreate) =>
  unwrap(
    client.POST("/api/v1/wearables/devices/{device_id}/bind", {
      params: { path: { device_id: deviceId } },
      body,
    }),
  );

export const unbindWearableDevice = (deviceId: string) =>
  unwrap(
    client.POST("/api/v1/wearables/devices/{device_id}/unbind", {
      params: { path: { device_id: deviceId } },
    }),
  );

export const listRfNodes = (activeOnly = false) =>
  unwrap(client.GET("/api/v1/wearables/nodes", { params: { query: { active_only: activeOnly } } }));

export const createRfNode = (body: RfNodeCreate) =>
  unwrap(client.POST("/api/v1/wearables/nodes", { body }));

export const updateRfNode = (nodeId: string, body: RfNodeUpdate) =>
  unwrap(
    client.PATCH("/api/v1/wearables/nodes/{node_id}", {
      params: { path: { node_id: nodeId } },
      body,
    }),
  );

export const deleteRfNode = (nodeId: string) =>
  unwrap(
    client.DELETE("/api/v1/wearables/nodes/{node_id}", {
      params: { path: { node_id: nodeId } },
    }),
  );

export const checkRfNodeSurvey = (body: RfNodeSurveyCheckRequest) =>
  unwrap(client.POST("/api/v1/wearables/nodes/survey-check", { body }));

export const getHouseholdFloorPlan = () => unwrap(client.GET("/api/v1/household/floor-plan", {}));

export const listDeviceAssociations = (deviceId: string, limit = 25) =>
  unwrap(
    client.GET("/api/v1/wearables/devices/{device_id}/associations", {
      params: { path: { device_id: deviceId }, query: { limit } },
    }),
  );

export const revokeWearableAssociation = (segmentId: string) =>
  unwrap(
    client.POST("/api/v1/wearables/associations/{segment_id}/revoke", {
      params: { path: { segment_id: segmentId } },
    }),
  );

export const resumeWearableTagTeaching = (tagId: string) =>
  unwrap(
    client.POST("/api/v1/wearables/tags/{tag_id}/resume-teaching", {
      params: { path: { tag_id: tagId } },
    }),
  );
