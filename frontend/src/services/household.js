/**
 * Household settings and rooms API client.
 */

function getApiKey() {
  return localStorage.getItem("cc_api_key") || "";
}

function authHeaders(extra = {}) {
  const key = getApiKey();
  return { ...(key ? { "X-API-Key": key } : {}), ...extra };
}

async function req(path, options = {}) {
  const headers = authHeaders({
    "Content-Type": "application/json",
    ...options.headers,
  });
  const resp = await fetch(`/api/v1${path}`, { ...options, headers });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    const detail = body.detail;
    const msg =
      typeof detail === "object" ? detail.message || JSON.stringify(detail) : detail;
    throw new Error(msg || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const household = {
  getFloorPlan: () => req("/household/floor-plan"),

  /**
   * Upload or update floor plan settings.
   * @param {FormData} formData - may contain: file, floor_plan_width, floor_plan_height, floor_meters_per_pixel
   */
  async postFloorPlan(formData) {
    const key = getApiKey();
    const resp = await fetch("/api/v1/household/floor-plan", {
      method: "POST",
      headers: key ? { "X-API-Key": key } : {},
      body: formData,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      const detail = body.detail;
      const msg =
        typeof detail === "object" ? detail.message || JSON.stringify(detail) : detail;
      throw new Error(msg || `HTTP ${resp.status}`);
    }
    return resp.json();
  },

  getRooms: () => req("/rooms"),

  putRoom: (id, data) =>
    req(`/rooms/${id}`, { method: "PUT", body: JSON.stringify(data) }),
};
