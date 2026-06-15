/**
 * API client for the Cognitive Companion backend.
 *
 * @module api
 *
 * ## Response shape contracts
 *
 * Every endpoint's return shape is registered in {@link contracts.js}.
 * Pass `{ contract: "name" }` in the options to `request()` and the
 * response will be validated against that shape in dev mode.  Mismatches
 * are logged as console warnings so wiring bugs surface immediately
 * rather than silently producing empty tables.
 *
 *   @example
 *   // With contract validation
 *   request("/quizzes", { contract: "quizzes.list" })
 *
 *   // Contract names follow the pattern "<resource>.<action>":
 *   //   quizzes.list   info-cards.list   knowledge.documents.list
 *   //   quizzes.single  info-cards.single  knowledge.documents.single
 *   //   knowledge.layouts.list         knowledge.layouts.single
 *   //   knowledge.interactions.queries  knowledge.interactions.sessions
 *   //   knowledge.interactions.session  knowledge.interactions.deliveries
 */

import { validateContract } from "./contracts.js";

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
  const { contract, ...fetchOpts } = options;

  const headers = authHeaders({
    "Content-Type": "application/json",
    ...fetchOpts.headers,
  });

  const resp = await fetch(`${BASE}${path}`, { ...fetchOpts, headers });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return null;
  const data = await resp.json();
  if (contract) validateContract(contract, data);
  return data;
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
  tritonHealth: () => request("/admin/health/triton"),
  llmHealth: () => request("/admin/health/llm-models"),

  // Rooms
  getRooms: () => request("/rooms", { contract: "rooms.list" }),
  createRoom: (data) => request("/rooms", { method: "POST", body: JSON.stringify(data) }),
  updateRoom: (id, data) => request(`/rooms/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteRoom: (id) => request(`/rooms/${id}`, { method: "DELETE" }),

  // Sensors
  getSensors: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/sensors${qs ? "?" + qs : ""}`, { contract: "sensors.list" });
  },
  createSensor: (data) => request("/sensors", { method: "POST", body: JSON.stringify(data) }),
  updateSensor: (id, data) => request(`/sensors/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteSensor: (id) => request(`/sensors/${id}`, { method: "DELETE" }),

  // Rules
  getRules: () => request("/rules", { contract: "rules.list" }),
  createRule: (data) => request("/rules", { method: "POST", body: JSON.stringify(data) }),
  getRule: (id) => request(`/rules/${id}`, { contract: "rules.single" }),
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

  // Cron triggers (separate from rules; linked via cron_trigger_ids in RuleUpdate)
  getCronTriggers: () => request("/rules/cron-triggers"),
  createCronTrigger: (data) =>
    request("/rules/cron-triggers", { method: "POST", body: JSON.stringify(data) }),
  updateCronTrigger: (id, data) =>
    request(`/rules/cron-triggers/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteCronTrigger: (id) =>
    request(`/rules/cron-triggers/${id}`, { method: "DELETE" }),

  // Rule import/export
  exportRule: (id) => request(`/rules/${id}/export`, { contract: "rules.export" }),
  importRulePreview: (bundle) =>
    request("/rules/import/preview", { method: "POST", body: JSON.stringify(bundle) }),
  importRule: (bundle) =>
    request("/rules/import", { method: "POST", body: JSON.stringify(bundle) }),
  validateRule: (id) => request(`/rules/${id}/validate`, { method: "POST" }),

  // Unified signals feed (CTS dementia signals + pipeline-rule notifications)
  getSignalsFeed: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/signals/feed${qs ? "?" + qs : ""}`, { contract: "signals.feed" });
  },

  // Interactive Responses
  getInteractiveResponses: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/interactive-responses${qs ? "?" + qs : ""}`, { contract: "interactive.responses.list" });
  },

  // Events
  getEvents: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/events${qs ? "?" + qs : ""}`, { contract: "events.list" });
  },

  // Occupancy
  getOccupancy: (roomName) => {
    const qs = roomName ? `?room_name=${roomName}` : "";
    return request(`/occupancy${qs}`, { contract: "occupancy" });
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
  getPersons: () => request("/persons", { contract: "persons.list" }),
  createPerson: (data) => request("/persons", { method: "POST", body: JSON.stringify(data) }),
  getPerson: (id) => request(`/persons/${id}`, { contract: "persons.single" }),
  updatePerson: (id, data) =>
    request(`/persons/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deletePerson: (id) => request(`/persons/${id}`, { method: "DELETE" }),
  getPersonLocations: () => request("/persons/locations", { contract: "persons.locations" }),
  getHeatmap: (params = {}) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v != null))
    ).toString();
    return request(`/cts/analytics/heatmap${qs ? "?" + qs : ""}`, { contract: "cts.heatmap" });
  },
  getPersonLocation: (id) => request(`/persons/${id}/location`, { contract: "persons.location" }),
  getPersonHistory: (id, hours = 24) => request(`/persons/${id}/history?hours=${hours}`, { contract: "persons.history" }),
  getPersonSightings: (id, limit = 20) => request(`/persons/${id}/sightings?limit=${limit}`, { contract: "persons.sightings" }),

  // Face Enrollment (person-ID service proxy)
  getEnrolledPersons: () => request("/persons/enrolled", { contract: "persons.enrolled" }),
  getEnrollmentStatus: (id) => request(`/persons/${id}/enrollment`),
  enrollPerson: (id, formData) => requestForm(`/persons/${id}/enroll`, "POST", formData),
  deleteEnrollment: (id) => request(`/persons/${id}/enrollment`, { method: "DELETE" }),

  // Pipeline Steps
  getRuleSteps: (ruleId) => request(`/rules/${ruleId}/steps`),
  getRuleEdges: (ruleId) => request(`/rules/${ruleId}/edges`, { contract: "rule.edges.list" }),
  replaceRuleEdges: (ruleId, edges) =>
    request(`/rules/${ruleId}/edges`, {
      method: "PUT",
      body: JSON.stringify({ edges }),
      contract: "rule.edges.replace",
    }),
  addRuleStep: (ruleId, data) =>
    request(`/rules/${ruleId}/steps`, { method: "POST", body: JSON.stringify(data) }),
  updateRuleStep: (ruleId, stepId, data) =>
    request(`/rules/${ruleId}/steps/${stepId}`, { method: "PUT", body: JSON.stringify(data) }),
  updateRuleStepPosition: (ruleId, stepId, { position_x, position_y }) =>
    request(`/rules/${ruleId}/steps/${stepId}`, {
      method: "PUT",
      body: JSON.stringify({ position_x, position_y }),
    }),
  batchUpdateStepPositions: (ruleId, positions) =>
    request(`/rules/${ruleId}/steps/positions`, {
      method: "PUT",
      body: JSON.stringify({ positions }),
      contract: "rule.steps.positions.update",
    }),
  deleteRuleStep: (ruleId, stepId) =>
    request(`/rules/${ruleId}/steps/${stepId}`, { method: "DELETE" }),
  executeRule: (ruleId) =>
    request(`/rules/${ruleId}/execute`, { method: "POST" }),

  // Workflows
  getWorkflows: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/workflows${qs ? "?" + qs : ""}`, { contract: "workflows.list" });
  },
  getWorkflow: (id) => request(`/workflows/${id}`, { contract: "workflows.single" }),
  cancelWorkflow: (id) => request(`/workflows/${id}/cancel`, { method: "POST" }),
  getWorkflowDetail: (id) => request(`/workflows/${id}/detail`, { contract: "workflows.detail" }),
  rerunWorkflow: (id) => request(`/workflows/${id}/rerun`, { method: "POST", body: JSON.stringify({}) }),

  // Activities
  getActivities: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/activities${qs ? "?" + qs : ""}`, { contract: "activities.list" });
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
  getImageTemplates: () => request("/image/templates", { contract: "image.templates.list" }),
  createImageTemplate: (formData) => requestForm("/image/templates", "POST", formData),
  updateImageTemplate: (id, data) =>
    request(`/image/templates/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  updateImageTemplateImage: (id, formData) =>
    requestForm(`/image/templates/${id}/image`, "PUT", formData),
  deleteImageTemplate: (id) => request(`/image/templates/${id}`, { method: "DELETE" }),
  getImageFonts: () => request("/image/fonts", { contract: "image.fonts" }),

  /**
   * Fetch the background image for a saved template as an authenticated
   * object URL. Revoke the returned URL when the component unmounts.
   */
  getImageTemplatePreview: (id) => requestBlob(`/image/templates/${id}/preview`),

  // E-Ink Display State
  getImageStates: () => request("/image/states", { contract: "image.states" }),
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

  // Pipeline runs
  getPipelineRuns: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/pipeline/runs${qs ? "?" + qs : ""}`, { contract: "pipeline.runs.list" });
  },
  getPipelineRun: (executionId) =>
    request(`/pipeline/runs/${executionId}`, { contract: "pipeline.runs.single" }),
  getIngestActivity: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/pipeline/ingest/activity${qs ? "?" + qs : ""}`, { contract: "pipeline.ingest.activity" });
  },

  // Pipeline metadata (step types, channels, filters, LLM models)
  getStepTypes: () => request("/pipeline/step-types"),
  getChannelTypes: () => request("/pipeline/channel-types"),
  getFilterTypes: () => request("/pipeline/filter-types"),
  getLLMModels: () => request("/pipeline/llm-models"),
  getDataKeys: () => request("/pipeline/data-keys"),
  getCronPreview: (data) =>
    request("/pipeline/cron/preview", { method: "POST", body: JSON.stringify(data) }),

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
    return request(`/media/buffer${qs ? "?" + qs : ""}`, { contract: "media.buffer" });
  },
  getAggregatorState: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/media/aggregators${qs ? "?" + qs : ""}`, {
      contract: "media.aggregators",
    });
  },

  // Pipeline image sources
  getSampleImage: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/pipeline/image-sources/sample${qs ? "?" + qs : ""}`);
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

  // -- Knowledge Documents -------------------------------------------------

  getKnowledgeDocuments: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/knowledge/documents${qs ? "?" + qs : ""}`, { contract: "knowledge.documents.list" });
  },
  getKnowledgeDocument: (id) =>
    request(`/knowledge/documents/${id}`, { contract: "knowledge.documents.single" }),
  createKnowledgeDocument: (formData) =>
    requestForm("/knowledge/documents", "POST", formData),
  updateKnowledgeDocument: (id, data) =>
    request(`/knowledge/documents/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteKnowledgeDocument: (id) =>
    request(`/knowledge/documents/${id}`, { method: "DELETE" }),
  approveKnowledgeDocument: (id) =>
    request(`/knowledge/documents/${id}/approve`, { method: "POST" }),
  archiveKnowledgeDocument: (id) =>
    request(`/knowledge/documents/${id}/archive`, { method: "POST" }),
  restoreKnowledgeDocument: (id) =>
    request(`/knowledge/documents/${id}/restore`, { method: "POST" }),
  reembedKnowledgeDocument: (id) =>
    request(`/knowledge/documents/${id}/reembed`, { method: "POST" }),
  addKnowledgeDocumentImage: (docId, formData) =>
    requestForm(`/knowledge/documents/${docId}/images`, "POST", formData),
  updateKnowledgeDocumentImage: (docId, imgId, data) =>
    request(`/knowledge/documents/${docId}/images/${imgId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteKnowledgeDocumentImage: (docId, imgId) =>
    request(`/knowledge/documents/${docId}/images/${imgId}`, { method: "DELETE" }),

  // -- Info Cards ----------------------------------------------------------

  getInfoCards: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/info-cards${qs ? "?" + qs : ""}`, { contract: "info-cards.list" });
  },
  getInfoCard: (id) => request(`/info-cards/${id}`, { contract: "info-cards.single" }),
  createInfoCard: (data) =>
    request("/info-cards", { method: "POST", body: JSON.stringify(data) }),
  updateInfoCard: (id, data) =>
    request(`/info-cards/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteInfoCard: (id) => request(`/info-cards/${id}`, { method: "DELETE" }),
  approveInfoCard: (id) =>
    request(`/info-cards/${id}/approve`, { method: "POST" }),
  archiveInfoCard: (id) =>
    request(`/info-cards/${id}/archive`, { method: "POST" }),
  restoreInfoCard: (id) =>
    request(`/info-cards/${id}/restore`, { method: "POST" }),
  setInfoCardSlot: (cardId, slotIndex, formData) =>
    requestForm(`/info-cards/${cardId}/slots/${slotIndex}`, "PUT", formData),
  patchInfoCardSlot: (cardId, slotIndex, data) =>
    request(`/info-cards/${cardId}/slots/${slotIndex}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteInfoCardSlot: (cardId, slotIndex) =>
    request(`/info-cards/${cardId}/slots/${slotIndex}`, { method: "DELETE" }),
  suggestInfoCard: (documentId, modelId) => {
    const params = new URLSearchParams({ document_id: documentId });
    if (modelId) params.set("model_id", modelId);
    return request(`/info-cards/suggest?${params}`, { method: "POST" });
  },

  // -- Quizzes -------------------------------------------------------------

  getQuizzes: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/quizzes${qs ? "?" + qs : ""}`, { contract: "quizzes.list" });
  },
  getQuiz: (id) => request(`/quizzes/${id}`, { contract: "quizzes.single" }),
  createQuiz: (data) =>
    request("/quizzes", { method: "POST", body: JSON.stringify(data) }),
  updateQuiz: (id, data) =>
    request(`/quizzes/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteQuiz: (id) => request(`/quizzes/${id}`, { method: "DELETE" }),
  approveQuiz: (id) =>
    request(`/quizzes/${id}/approve`, { method: "POST" }),
  archiveQuiz: (id) =>
    request(`/quizzes/${id}/archive`, { method: "POST" }),
  restoreQuiz: (id) =>
    request(`/quizzes/${id}/restore`, { method: "POST" }),
  createQuizQuestion: (quizId, data) =>
    request(`/quizzes/${quizId}/questions`, { method: "POST", body: JSON.stringify(data) }),
  updateQuizQuestion: (quizId, qid, data) =>
    request(`/quizzes/${quizId}/questions/${qid}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteQuizQuestion: (quizId, qid) =>
    request(`/quizzes/${quizId}/questions/${qid}`, { method: "DELETE" }),
  reorderQuizQuestions: (quizId, items) =>
    request(`/quizzes/${quizId}/questions/reorder`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  setQuizQuestionImage: (quizId, qid, formData) =>
    requestForm(`/quizzes/${quizId}/questions/${qid}/image`, "PUT", formData),
  deleteQuizQuestionImage: (quizId, qid) =>
    request(`/quizzes/${quizId}/questions/${qid}/image`, { method: "DELETE" }),
  suggestQuiz: (documentId, numQuestions, mix, modelId) => {
    const params = new URLSearchParams({ document_id: documentId });
    if (numQuestions) params.set("num_questions", numQuestions);
    if (mix) params.set("mix", mix);
    if (modelId) params.set("model_id", modelId);
    return request(`/quizzes/suggest?${params}`, { method: "POST" });
  },
  suggestQuizVoiceInstruction: (documentId, resourceType, modelId) => {
    const params = new URLSearchParams({ document_id: documentId });
    if (resourceType) params.set("resource_type", resourceType);
    if (modelId) params.set("model_id", modelId);
    return request(`/quizzes/voice-instruction-suggest?${params}`, { method: "POST" });
  },
  regenerateQuizQuestion: (quizId, qid, modelId) => {
    const params = modelId ? `?model_id=${encodeURIComponent(modelId)}` : "";
    return request(`/quizzes/${quizId}/questions/${qid}/regenerate${params}`, { method: "POST" });
  },

  // -- Layouts -------------------------------------------------------------

  getKnowledgeLayouts: (appliesTo) => {
    const qs = appliesTo ? `?applies_to=${appliesTo}` : "";
    return request(`/knowledge/layouts${qs}`, { contract: "knowledge.layouts.list" });
  },
  getKnowledgeLayout: (id) =>
    request(`/knowledge/layouts/${id}`, { contract: "knowledge.layouts.single" }),

  // -- Interactions --------------------------------------------------------

  getSeniorKnowledgeQueries: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/knowledge-interactions/queries${qs ? "?" + qs : ""}`, { contract: "knowledge.interactions.queries" });
  },
  getQuizSessions: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/knowledge-interactions/quiz-sessions${qs ? "?" + qs : ""}`, { contract: "knowledge.interactions.sessions" });
  },
  getQuizSession: (id) =>
    request(`/knowledge-interactions/quiz-sessions/${id}`, { contract: "knowledge.interactions.session" }),
  getInfoCardDeliveries: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/knowledge-interactions/info-card-deliveries${qs ? "?" + qs : ""}`, { contract: "knowledge.interactions.deliveries" });
  },
};

/**
 * Open a WebSocket connection to /ws/pipeline for live pipeline events.
 * Follows the same auth pattern as cts.openLiveSocket: API key via
 * Sec-WebSocket-Protocol header to avoid query-param logging.
 *
 * @param {function} onMessage  Called with the parsed event object.
 * @returns {WebSocket}
 */
export function openPipelineSocket(onMessage) {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const key = getApiKey();
  const ws = new WebSocket(
    `${proto}//${window.location.host}/ws/pipeline`,
    key ? [key] : undefined,
  );
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      onMessage(data);
    } catch {
      // ignore malformed messages
    }
  };
  return ws;
}
