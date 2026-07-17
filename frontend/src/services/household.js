/**
 * Household settings and rooms API client.
 */

import { requestForm, requestJson } from "./http";

/** Requests go through the shared core in `http.ts` (auth, ApiError, network-error wrapping). */
function req(path, options = {}) {
  return requestJson(`/api/v1${path}`, options);
}

export const household = {
  getFloorPlan: () => req("/household/floor-plan"),

  /**
   * Upload or update floor plan settings.
   * @param {FormData} formData - may contain: file, floor_plan_width, floor_plan_height, floor_meters_per_pixel
   */
  postFloorPlan: (formData) => requestForm("/api/v1/household/floor-plan", "POST", formData),

  getRooms: () => req("/rooms"),

  putRoom: (id, data) =>
    req(`/rooms/${id}`, { method: "PUT", body: JSON.stringify(data) }),
};
