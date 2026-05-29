import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, beforeEach } from "vitest";
import KeyframeStrip from "../KeyframeStrip.vue";

const mockGetKeyframeBlob = vi.fn();

vi.mock("@/services/cts.js", () => ({
  cts: { getKeyframeBlob: (...args) => mockGetKeyframeBlob(...args) },
}));

const notifyError = vi.fn();
vi.mock("@/composables/useNotify", () => ({
  useNotify: () => Object.assign(vi.fn(), { error: notifyError, success: vi.fn() }),
}));

vi.mock("@/composables/useBlurMode", () => ({
  useBlurMode: () => ({ blurMode: { value: false } }),
  useDisplaySrc: () => ({ displaySrc: (src) => src }),
}));

const stubs = {
  "v-icon": { template: "<i><slot /></i>" },
  "v-img": {
    template: '<img :src="src" @click="$emit(\'click\', $event)" />',
    props: ["src"],
  },
};

function mountStrip(frames) {
  return mount(KeyframeStrip, {
    props: { frames },
    global: { stubs },
  });
}

describe("KeyframeStrip", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:test-url"),
      revokeObjectURL: vi.fn(),
    });
  });

  it("never reads localStorage for auth", async () => {
    mockGetKeyframeBlob.mockResolvedValue("blob:test-url");
    const localStorageSpy = vi.spyOn(Storage.prototype, "getItem");

    const frames = [{ sample_id: "s1", minio_key: "keyframes/s1.jpg" }];
    mountStrip(frames);
    await flushPromises();

    expect(localStorageSpy).not.toHaveBeenCalledWith("cc_api_key");
  });

  it("fetches image via cts.getKeyframeBlob not global fetch", async () => {
    const globalFetchSpy = vi.spyOn(globalThis, "fetch");
    mockGetKeyframeBlob.mockResolvedValue("blob:test-url");

    const frames = [{ sample_id: "s1", minio_key: "keyframes/s1.jpg" }];
    mountStrip(frames);
    await flushPromises();

    expect(mockGetKeyframeBlob).toHaveBeenCalledWith("keyframes/s1.jpg");
    expect(globalFetchSpy).not.toHaveBeenCalled();
  });

  it("revokes blob URLs on unmount", async () => {
    mockGetKeyframeBlob.mockResolvedValue("blob:test-url");
    const revokeSpy = URL.revokeObjectURL;

    const frames = [{ sample_id: "s1", minio_key: "keyframes/s1.jpg" }];
    const wrapper = mountStrip(frames);
    await flushPromises();

    wrapper.unmount();
    expect(revokeSpy).toHaveBeenCalledWith("blob:test-url");
  });

  it("calls notify.error when blob fetch fails", async () => {
    mockGetKeyframeBlob.mockRejectedValue(new Error("storage unavailable"));

    const frames = [{ sample_id: "s1", minio_key: "keyframes/s1.jpg" }];
    mountStrip(frames);
    await flushPromises();

    expect(notifyError).toHaveBeenCalledWith("storage unavailable");
  });
});
