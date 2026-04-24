/**
 * API client for the Cognitive Companion backend.
 */

const BASE = "/api/v1";

function getApiKey() {
  return localStorage.getItem("cc_api_key") || "";
}

/** Build auth headers, optionally merging extra headers. */
function authHeaders(extra = {}) {
  const key = getApiKey();
  return { ...(key ? { "X-API-Key": key } : {}), ...extra };
}

/** JSON request helper: always injects the API key. */
async function request(path, options = {}) {
  const headers = authHeaders({
    "Content-Type": "application/json",
    ...options.headers,
  });

  const resp = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

/**
 * Multipart/binary POST or PUT: sends FormData with auth header.
 * Returns parsed JSON on success.
 */
async function requestForm(path, method, formData) {
  const resp = await fetch(`${BASE}${path}`, {
    method,
    headers: authHeaders(),
    body: formData,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

/**
 * Fetch a binary resource with auth and return a Blob object URL.
 * The caller is responsible for revoking the URL when done.
 */
async function requestBlob(path) {
  const resp = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  return URL.createObjectURL(await resp.blob());
}

export const api = {
  setApiKey(key) {
    localStorage.setItem("cc_api_key", key);
  },

  // Health
  health: () => fetch(`${BASE}/health`).then((r) => r.json()),
  ttsHealth: () => request("/admin/health/tts"),
  personIdHealth: () => request("/admin/health/person-id"),
  trackingOrchestratorHealth: () => request("/admin/health/tracking-orchestrator"),
  sceneAnalysisHealth: () => request("/admin/health/scene-analysis"),
  semanticMemoryHealth: () => request("/admin/health/semantic-memory"),
  llmHealth: () => request("/admin/health/llm-models"),

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

  // Interactive Responses
  getInteractiveResponses: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/interactive-responses${qs ? "?" + qs : ""}`);
  },

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
  enrollPerson: (id, formData) => requestForm(`/persons/${id}/enroll`, "POST", formData),
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

  // Activity Timeline
  getTimeline: (personId, params = {}) => {
    const qs = new URLSearchParams({ person_id: personId, ...params }).toString();
    return request(`/activities/timeline?${qs}`);
  },

  // Activity Sessions
  openSession: (personId, data) =>
    request("/activities/sessions/open", {
      method: "POST",
      body: JSON.stringify({ person_id: personId, ...data }),
    }),
  closeSession: (sessionId, data = {}) =>
    request(`/activities/sessions/${sessionId}/close`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getOpenSessions: (personId) => {
    const qs = personId ? `?person_id=${personId}` : "";
    return request(`/activities/sessions/open${qs}`);
  },

  // Daily Reports
  getDailyReport: (personId, date, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/activities/reports/${personId}/${date}${qs ? "?" + qs : ""}`);
  },
  regenerateDailyReport: (personId, date, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/activities/reports/${personId}/${date}/regenerate?${qs}`, {
      method: "POST",
    });
  },

  // Image Templates
  getImageTemplates: () => request("/image/templates"),
  createImageTemplate: (formData) => requestForm("/image/templates", "POST", formData),
  updateImageTemplate: (id, data) =>
    request(`/image/templates/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  updateImageTemplateImage: (id, formData) =>
    requestForm(`/image/templates/${id}/image`, "PUT", formData),
  deleteImageTemplate: (id) => request(`/image/templates/${id}`, { method: "DELETE" }),
  getImageFonts: () => request("/image/fonts"),

  /**
   * Fetch the background image for a saved template as an authenticated
   * object URL. Revoke the returned URL when the component unmounts.
   */
  getImageTemplatePreview: (id) => requestBlob(`/image/templates/${id}/preview`),

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
    const resp = await fetch(`${BASE}/image/preview`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(data),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${resp.status}`);
    }
    return URL.createObjectURL(await resp.blob());
  },

  /**
   * Preview rendered image using FormData (supports new-template image upload
   * and live region/font overrides for existing templates).
   *
   * @param {FormData} formData  Fields: text, regions_json, font_filename,
   *                             template_id? (int), image? (File)
   * @returns {Promise<string>} Object URL of the preview PNG
   */
  previewImageForm: async (formData) => {
    const resp = await fetch(`${BASE}/image/preview-form`, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${resp.status}`);
    }
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
    }).then(async (r) => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
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
   * No API key required: used during app bootstrap to initialise timezone.
   *
   * @returns {Promise<{name: string, version: string, timezone: string}>}
   */
  getAppInfo: () => fetch(`${BASE}/admin/app-info`).then((r) => r.json()),
};
