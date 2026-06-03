/**
 * Unit tests for LLM health status cards in DashboardView.vue
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 3.1
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

// Mock the api module before importing the component
vi.mock("@/services/api.js", () => ({
  api: {
    // Stats calls
    getRooms: vi.fn().mockResolvedValue([]),
    getSensors: vi.fn().mockResolvedValue([]),
    getRules: vi.fn().mockResolvedValue([]),
    getSignalsFeed: vi.fn().mockResolvedValue([]),
    getOccupancy: vi.fn().mockResolvedValue({ occupancy: {} }),
    getPersonLocations: vi.fn().mockResolvedValue([]),
    // Health checks (called before llmHealth)
    health: vi.fn().mockResolvedValue({ status: "ok", version: "1.0" }),
    personIdHealth: vi.fn().mockResolvedValue({ configured: false }),
    ttsHealth: vi.fn().mockResolvedValue({ configured: false }),
    trackingOrchestratorHealth: vi.fn().mockResolvedValue({ configured: false }),
    sceneAnalysisHealth: vi.fn().mockResolvedValue({ configured: false }),
    semanticMemoryHealth: vi.fn().mockResolvedValue({ configured: false }),
    tritonHealth: vi.fn().mockResolvedValue({ configured: false }),
    // LLM health — overridden per test
    llmHealth: vi.fn().mockResolvedValue([]),
  },
}));

// Mock timezone service to avoid localStorage dependency
vi.mock("@/services/timezone.js", () => ({
  formatDateTimeShort: vi.fn((v) => v || ""),
}));

// Stub Vuetify components to avoid full Vuetify setup
const stubComponents = {
  "v-btn": { template: "<button><slot /></button>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-avatar": { template: "<span><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": { template: "<li><slot /></li>" },
  "v-chip": { template: "<span><slot /></span>" },
  "v-alert": { template: "<div><slot /></div>" },
};

import { api } from "@/services/api.js";
import DashboardView from "@/views/admin/DashboardView.vue";

/**
 * Mount DashboardView with all Vuetify components stubbed.
 * Returns the wrapper after all promises have settled.
 */
async function mountDashboard() {
  const wrapper = mount(DashboardView, {
    global: { stubs: stubComponents },
  });
  await flushPromises();
  return wrapper;
}

/**
 * Count how many entries in healthServices are LLM cards.
 * LLM cards are those NOT named one of the fixed service names.
 */
const FIXED_SERVICE_NAMES = new Set([
  "Backend",
  "Person-ID Service",
  "TTS Service",
  "Tracking Orchestrator",
  "Scene Analysis",
  "Semantic Memory",
  "Triton Inference Server",
  "LLM Models", // error fallback card
]);

function getLlmCards(healthServices) {
  return healthServices.filter((s) => !FIXED_SERVICE_NAMES.has(s.name));
}

// ---------------------------------------------------------------------------
// Helper: get healthServices from the component instance
// ---------------------------------------------------------------------------
function getHealthServices(wrapper) {
  // Access the exposed reactive ref via the component's internal state
  return wrapper.vm.healthServices ?? wrapper.vm.$.setupState.healthServices;
}

describe("DashboardView — LLM health cards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset all mocks to their default resolved values
    api.getRooms.mockResolvedValue([]);
    api.getSensors.mockResolvedValue([]);
    api.getRules.mockResolvedValue([]);
    api.getSignalsFeed.mockResolvedValue([]);
    api.getOccupancy.mockResolvedValue({ occupancy: {} });
    api.getPersonLocations.mockResolvedValue([]);
    api.health.mockResolvedValue({ status: "ok", version: "1.0" });
    api.personIdHealth.mockResolvedValue({ configured: false });
    api.ttsHealth.mockResolvedValue({ configured: false });
    api.trackingOrchestratorHealth.mockResolvedValue({ configured: false });
    api.sceneAnalysisHealth.mockResolvedValue({ configured: false });
    api.semanticMemoryHealth.mockResolvedValue({ configured: false });
    api.tritonHealth.mockResolvedValue({ configured: false });
    api.llmHealth.mockResolvedValue([]);
  });

  // -------------------------------------------------------------------------
  // Test 1: Card count — N items → N LLM cards
  // -------------------------------------------------------------------------
  it("adds exactly N LLM cards when api.llmHealth returns N items", async () => {
    const items = [
      { name: "Model A", status: "success", configured_model: "model-a", detail: null },
      { name: "Model B", status: "error", configured_model: "model-b", detail: "Unreachable" },
      { name: "Model C", status: "warning", configured_model: "model-c", detail: "configured: model-c, available: [other]" },
    ];
    api.llmHealth.mockResolvedValue(items);

    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const llmCards = getLlmCards(hs.value ?? hs);

    expect(llmCards).toHaveLength(3);
  });

  // -------------------------------------------------------------------------
  // Test 2: Status mapping — success
  // -------------------------------------------------------------------------
  it("maps status=success to ok:true with detail=configured_model", async () => {
    api.llmHealth.mockResolvedValue([
      { name: "Vision LLM", status: "success", configured_model: "nvidia/Cosmos-8B", detail: null },
    ]);

    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const llmCards = getLlmCards(hs.value ?? hs);

    expect(llmCards).toHaveLength(1);
    expect(llmCards[0].ok).toBe(true);
    expect(llmCards[0].detail).toBe("nvidia/Cosmos-8B");
  });

  // -------------------------------------------------------------------------
  // Test 3: Status mapping — warning
  // -------------------------------------------------------------------------
  it("maps status=warning to ok:false, color:warning, and detail from response", async () => {
    const warningDetail = "configured: nvidia/Cosmos-8B, available: [other-model]";
    api.llmHealth.mockResolvedValue([
      { name: "Vision LLM", status: "warning", configured_model: "nvidia/Cosmos-8B", detail: warningDetail },
    ]);

    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const llmCards = getLlmCards(hs.value ?? hs);

    expect(llmCards).toHaveLength(1);
    expect(llmCards[0].ok).toBe(false);
    expect(llmCards[0].color).toBe("warning");
    expect(llmCards[0].detail).toBe(warningDetail);
  });

  // -------------------------------------------------------------------------
  // Test 4: Status mapping — error
  // -------------------------------------------------------------------------
  it("maps status=error to ok:false with no color override", async () => {
    api.llmHealth.mockResolvedValue([
      { name: "Vision LLM", status: "error", configured_model: "nvidia/Cosmos-8B", detail: "Connection refused" },
    ]);

    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const llmCards = getLlmCards(hs.value ?? hs);

    expect(llmCards).toHaveLength(1);
    expect(llmCards[0].ok).toBe(false);
    expect(llmCards[0].color).toBeUndefined();
  });

  // -------------------------------------------------------------------------
  // Test 5: Endpoint error → single "LLM Models" error card
  // -------------------------------------------------------------------------
  it("pushes a single LLM Models error card when api.llmHealth throws", async () => {
    api.llmHealth.mockRejectedValue(new Error("Network error"));

    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const services = hs.value ?? hs;

    const errorCard = services.find((s) => s.name === "LLM Models");
    expect(errorCard).toBeDefined();
    expect(errorCard.ok).toBe(false);
    expect(errorCard.detail).toBe("Health check failed");

    // Should be exactly one "LLM Models" card
    const llmErrorCards = services.filter((s) => s.name === "LLM Models");
    expect(llmErrorCards).toHaveLength(1);
  });

  // -------------------------------------------------------------------------
  // Test 6: Empty array → no LLM cards added
  // -------------------------------------------------------------------------
  it("adds no LLM cards when api.llmHealth returns an empty array", async () => {
    api.llmHealth.mockResolvedValue([]);

    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const llmCards = getLlmCards(hs.value ?? hs);

    expect(llmCards).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // Test 7: api.js method — llmHealth calls request("/admin/health/llm-models")
  // -------------------------------------------------------------------------
  it("api.llmHealth calls request('/admin/health/llm-models')", async () => {
    // Test the real api.js module (not the mock) by importing it directly
    // and verifying the implementation calls request with the correct path.
    // We do this by checking the mock was called (it wraps request internally).
    api.llmHealth.mockResolvedValue([]);

    const wrapper = await mountDashboard();

    // Verify llmHealth was called during loadData
    expect(api.llmHealth).toHaveBeenCalledTimes(1);

    // Verify the real implementation uses the correct path by inspecting api.js source
    // The api.js module exports: llmHealth: () => request("/admin/health/llm-models")
    // We verify this by importing the real module in a separate check below.
  });
});

// ---------------------------------------------------------------------------
// Describe block: verify Tracking Orchestrator health statuses
// ---------------------------------------------------------------------------
describe("DashboardView — Tracking Orchestrator health", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getRooms.mockResolvedValue([]);
    api.getSensors.mockResolvedValue([]);
    api.getRules.mockResolvedValue([]);
    api.getSignalsFeed.mockResolvedValue([]);
    api.getOccupancy.mockResolvedValue({ occupancy: {} });
    api.getPersonLocations.mockResolvedValue([]);
    api.health.mockResolvedValue({ status: "ok", version: "1.0" });
    api.personIdHealth.mockResolvedValue({ configured: false });
    api.ttsHealth.mockResolvedValue({ configured: false });
    api.sceneAnalysisHealth.mockResolvedValue({ configured: false });
    api.semanticMemoryHealth.mockResolvedValue({ configured: false });
    api.tritonHealth.mockResolvedValue({ configured: false });
    api.llmHealth.mockResolvedValue([]);
  });

  it("marks Tracking Orchestrator as ok:false when status is 'running' (must be 'healthy')", async () => {
    api.trackingOrchestratorHealth.mockResolvedValue({ configured: true, status: "running", version: "0.1.0" });
    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const services = hs.value ?? hs;
    const toCard = services.find((s) => s.name === "Tracking Orchestrator");
    expect(toCard).toBeDefined();
    expect(toCard.ok).toBe(false);
    expect(toCard.detail).toBe("running · v0.1.0");
  });

  it("marks Tracking Orchestrator as ok:true when status is 'healthy'", async () => {
    api.trackingOrchestratorHealth.mockResolvedValue({ configured: true, status: "healthy", version: "0.1.0" });
    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const services = hs.value ?? hs;
    const toCard = services.find((s) => s.name === "Tracking Orchestrator");
    expect(toCard).toBeDefined();
    expect(toCard.ok).toBe(true);
    expect(toCard.detail).toBe("healthy · v0.1.0");
  });

  it("marks Tracking Orchestrator as ok:false when status is 'unreachable'", async () => {
    api.trackingOrchestratorHealth.mockResolvedValue({ configured: true, status: "unreachable" });
    const wrapper = await mountDashboard();
    const hs = getHealthServices(wrapper);
    const services = hs.value ?? hs;
    const toCard = services.find((s) => s.name === "Tracking Orchestrator");
    expect(toCard).toBeDefined();
    expect(toCard.ok).toBe(false);
    expect(toCard.detail).toBe("Unreachable");
  });
});

// ---------------------------------------------------------------------------
// Separate describe block: verify the real api.js implementation
// ---------------------------------------------------------------------------
describe("api.js — llmHealth method", () => {
  it("calls request with /admin/health/llm-models", async () => {
    // Import the real api module (not the mock) by resetting the mock for this test
    // We verify the source-level contract: api.llmHealth is defined and calls the right path.
    // Since we can't easily un-mock in the same file, we verify via the mock call args
    // by checking what the real implementation does through a fresh import.

    // The real api.js has: llmHealth: () => request("/admin/health/llm-models")
    // We verify this by mocking fetch and calling the real function.
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal("fetch", mockFetch);

    // Dynamically import the real module (bypassing the vi.mock at the top)
    const { api: realApi } = await vi.importActual("@/services/api.js");
    await realApi.llmHealth();

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/admin/health/llm-models",
      expect.objectContaining({ headers: expect.any(Object) })
    );

    vi.unstubAllGlobals();
  });
});
