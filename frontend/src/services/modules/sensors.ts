/** Sensors (HA-sourced and local hardware). */

import { client, unwrap } from "@/services/http";
import type { components, operations } from "@/generated/api-types";

type Schemas = components["schemas"];

export type SensorOut = Schemas["SensorOut"];

type ListParams = operations["list_sensors"]["parameters"]["query"];

export const getSensors = (params: ListParams = {}) =>
  unwrap(client.GET("/api/v1/sensors", { params: { query: params } }));

export const createSensor = (data: Schemas["SensorCreate"]) =>
  unwrap(client.POST("/api/v1/sensors", { body: data }));

export const updateSensor = (id: string, data: Schemas["SensorUpdate"]) =>
  unwrap(
    client.PUT("/api/v1/sensors/{sensor_id}", { params: { path: { sensor_id: id } }, body: data }),
  );

export const deleteSensor = (id: string) =>
  unwrap(client.DELETE("/api/v1/sensors/{sensor_id}", { params: { path: { sensor_id: id } } }));
