/**
 * API client for the Cognitive Companion backend.
 */

const BASE = "/api/v1";

function getApiKey() {
  return localStorage.getItem("cc_api_key") || "";
}

async function request(path, options = {}) {
  const key = getApiKey();
  const headers = {
    "Content-Type": "application/json",
    ...(key ? { "X-API-Key": key } : {}),
    ...options.headers,
  };

  const resp = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const api = {
  setApiKey(key) {
    localStorage.setItem("cc_api_key", key);
  },

  // Health
  health: () => fetch(`${BASE}/health`).then((r) => r.json()),
  ttsHealth: () => request("/admin/health/tts"),
  personIdHealth: () => request("/admin/health/person-id"),

  // Rooms
  getRooms: () => request("/rooms"),
  createRoom: (data) => request("/rooms", { method: "POST", body: JSON.stringify(data) }),
  updateRoom: (id, data) => request(`/rooms/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteRoom: (id) => request(`/rooms/${id}`, { method: "DELETE" }),

  // Sensors
  getSensors: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/sensors${qs ? "?" + qs : ""}`);
  },
  createSensor: (data) => request("/sensors", { method: "POST", body: JSON.stringify(data) }),
  updateSensor: (id, data) => request(`/sensors/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteSensor: (id) => request(`/sensors/${id}`, { method: "DELETE" }),

  // Rules
  getRules: () => request("/rules"),
  createRule: (data) => request("/rules", { method: "POST", body: JSON.stringify(data) }),
  getRule: (id) => request(`/rules/${id}`),
  updateRule: (id, data) => request(`/rules/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteRule: (id) => request(`/rules/${id}`, { method: "DELETE" }),

  // Rule contexts
  getRuleContexts: (ruleId) => request(`/rules/${ruleId}/contexts`),
  addRuleContext: (ruleId, data) =>
    request(`/rules/${ruleId}/contexts`, { method: "POST", body: JSON.stringify(data) }),
  deleteRuleContext: (ruleId, ctxId) =>
    request(`/rules/${ruleId}/contexts/${ctxId}`, { method: "DELETE" }),

  // Rule dependencies
  getRuleDeps: (ruleId) => request(`/rules/${ruleId}/dependencies`),
  addRuleDep: (ruleId, data) =>
    request(`/rules/${ruleId}/dependencies`, { method: "POST", body: JSON.stringify(data) }),
  deleteRuleDep: (ruleId, depId) =>
    request(`/rules/${ruleId}/dependencies/${depId}`, { method: "DELETE" }),

  // Alerts
  getAlerts: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/alerts${qs ? "?" + qs : ""}`);
  },
  alertAction: (id, action) =>
    request(`/alerts/${id}/action`, { method: "POST", body: JSON.stringify(action) }),

  // Events
  getEvents: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/events${qs ? "?" + qs : ""}`);
  },

  // Occupancy
  getOccupancy: (roomName) => {
    const qs = roomName ? `?room_name=${roomName}` : "";
    return request(`/occupancy${qs}`);
  },

  // HA Sync
  syncRooms: () => request("/ha/sync/rooms", { method: "POST" }),
  syncSensors: (roomName) => {
    const qs = roomName ? `?room_name=${roomName}` : "";
    return request(`/ha/sync/sensors${qs}`, { method: "POST" });
  },
  getHAMediaPlayers: () => request("/ha/media-players"),
  getHAEntities: (domain) => {
    const qs = domain ? `?domain=${encodeURIComponent(domain)}` : "";
    return request(`/ha/entities${qs}`);
  },

  // Persons
  getPersons: () => request("/persons"),
  createPerson: (data) => request("/persons", { method: "POST", body: JSON.stringify(data) }),
  getPerson: (id) => request(`/persons/${id}`),
  updatePerson: (id, data) =>
    request(`/persons/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deletePerson: (id) => request(`/persons/${id}`, { method: "DELETE" }),
  getPersonLocations: () => request("/persons/locations"),
  getPersonLocation: (id) => request(`/persons/${id}/location`),
  getPersonHistory: (id, hours = 24) => request(`/persons/${id}/history?hours=${hours}`),
  getPersonSightings: (id, limit = 20) => request(`/persons/${id}/sightings?limit=${limit}`),

  // Face Enrollment (person-ID service proxy)
  getEnrolledPersons: () => request("/persons/enrolled"),
  getEnrollmentStatus: (id) => request(`/persons/${id}/enrollment`),
  enrollPerson: (id, formData) => {
    const key = getApiKey();
    return fetch(`${BASE}/persons/${id}/enroll`, {
      method: "POST",
      headers: key ? { "X-API-Key": key } : {},
      body: formData,
    }).then((r) => {
      if (!r.ok) return r.json().then((b) => { throw new Error(b.detail || `HTTP ${r.status}`); });
      return r.json();
    });
  },
  deleteEnrollment: (id) => request(`/persons/${id}/enrollment`, { method: "DELETE" }),

  // Pipeline Steps
  getRuleSteps: (ruleId) => request(`/rules/${ruleId}/steps`),
  addRuleStep: (ruleId, data) =>
    request(`/rules/${ruleId}/steps`, { method: "POST", body: JSON.stringify(data) }),
  updateRuleStep: (ruleId, stepId, data) =>
    request(`/rules/${ruleId}/steps/${stepId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteRuleStep: (ruleId, stepId) =>
    request(`/rules/${ruleId}/steps/${stepId}`, { method: "DELETE" }),
  reorderRuleSteps: (ruleId, steps) =>
    request(`/rules/${ruleId}/steps/reorder`, {
      method: "PUT",
      body: JSON.stringify({ steps }),
    }),
  executeRule: (ruleId) =>
    request(`/rules/${ruleId}/execute`, { method: "POST" }),

  // Workflows
  getWorkflows: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/workflows${qs ? "?" + qs : ""}`);
  },
  getWorkflow: (id) => request(`/workflows/${id}`),
  cancelWorkflow: (id) => request(`/workflows/${id}/cancel`, { method: "POST" }),

  // Activities
  getActivities: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/activities${qs ? "?" + qs : ""}`);
  },

  // Image Templates
  getImageTemplates: () => request("/image/templates"),
  createImageTemplate: (formData) => {
    const key = getApiKey();
    return fetch(`${BASE}/image/templates`, {
      method: "POST",
      headers: key ? { "X-API-Key": key } : {},
      body: formData,
    }).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
  },
  updateImageTemplate: (id, data) =>
    request(`/image/templates/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  updateImageTemplateImage: (id, formData) => {
    const key = getApiKey();
    return fetch(`${BASE}/image/templates/${id}/image`, {
      method: "PUT",
      headers: key ? { "X-API-Key": key } : {},
      body: formData,
    }).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
  },
  deleteImageTemplate: (id) => request(`/image/templates/${id}`, { method: "DELETE" }),
  getImageFonts: () => request("/image/fonts"),

  // E-Ink Display State
  getImageStates: () => request("/image/states"),
  renderImage: (data) =>
    request("/image/render", { method: "POST", body: JSON.stringify(data) }),
  resetImage: (sensorIds) =>
    request("/image/reset", {
      method: "POST",
      body: JSON.stringify({ sensor_ids: sensorIds }),
    }),
  previewImage: async (data) => {
    const key = getApiKey();
    const resp = await fetch(`${BASE}/image/preview`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(key ? { "X-API-Key": key } : {}),
      },
      body: JSON.stringify(data),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return URL.createObjectURL(await resp.blob());
  },

  // Pipeline metadata (step types, channels, filters, LLM models)
  getStepTypes: () => request("/pipeline/step-types"),
  getChannelTypes: () => request("/pipeline/channel-types"),
  getFilterTypes: () => request("/pipeline/filter-types"),
  getLLMModels: () => request("/pipeline/llm-models"),

  // Webhooks
  triggerWebhook: (ruleId, payload, secret) =>
    fetch(`${BASE}/webhooks/${ruleId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Webhook-Secret": secret,
      },
      body: JSON.stringify(payload),
    }).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    }),
  generateWebhookSecret: (ruleId) =>
    request(`/webhooks/${ruleId}/generate-secret`, { method: "POST" }),

  // Media buffer (camera feed)
  getMediaBuffer: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/media/buffer${qs ? "?" + qs : ""}`);
  },

  // Admin
  reloadConfig: () => request("/admin/config/reload", { method: "POST" }),
  getTelegramTriggerDefaults: () => request("/admin/telegram/trigger-defaults"),

  /**
   * Return public application metadata (name, version, timezone).
   * No API key required — used during app bootstrap to initialise timezone.
   *
   * @returns {Promise<{name: string, version: string, timezone: string}>}
   */
  getAppInfo: () => fetch(`${BASE}/admin/app-info`).then((r) => r.json()),
};
