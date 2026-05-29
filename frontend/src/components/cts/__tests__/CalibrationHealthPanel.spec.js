import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, beforeEach } from "vitest";
import CalibrationHealthPanel from "../CalibrationHealthPanel.vue";

const mockGetCalibrationHealth = vi.fn();

vi.mock("@/services/cts.js", () => ({
  cts: { getCalibrationHealth: (...args) => mockGetCalibrationHealth(...args) },
}));

const notifyError = vi.fn();
vi.mock("@/composables/useNotify", () => ({
  useNotify: () => ({ notify: Object.assign(vi.fn(), { error: notifyError, success: vi.fn() }) }),
}));

vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

describe("CalibrationHealthPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls cts.getCalibrationHealth on mount (not global fetch or localStorage)", async () => {
    mockGetCalibrationHealth.mockResolvedValue([
      { camera_id: "cam-1", severity: "ok", code: null, residual_m: 0.012 },
    ]);
    const localStorageSpy = vi.spyOn(Storage.prototype, "getItem");
    const globalFetchSpy = vi.spyOn(globalThis, "fetch");

    mount(CalibrationHealthPanel, { global: { stubs: { "v-card": true, "v-img": true } } });
    await flushPromises();

    expect(mockGetCalibrationHealth).toHaveBeenCalledOnce();
    expect(localStorageSpy).not.toHaveBeenCalledWith("cc_api_key");
    expect(globalFetchSpy).not.toHaveBeenCalled();
  });

  it("renders camera health dots when data loads", async () => {
    mockGetCalibrationHealth.mockResolvedValue([
      { camera_id: "cam-1", severity: "ok", code: null, residual_m: null },
      { camera_id: "cam-2", severity: "warning", code: "low_coverage", residual_m: 0.05 },
    ]);
    const wrapper = mount(CalibrationHealthPanel);
    await flushPromises();

    expect(wrapper.find("[data-testid='calibration-dot-cam-1']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='calibration-dot-cam-2']").exists()).toBe(true);
  });

  it("calls notify.error when service throws", async () => {
    mockGetCalibrationHealth.mockRejectedValue(new Error("upstream down"));
    mount(CalibrationHealthPanel);
    await flushPromises();

    expect(notifyError).toHaveBeenCalledWith("upstream down");
  });
});
