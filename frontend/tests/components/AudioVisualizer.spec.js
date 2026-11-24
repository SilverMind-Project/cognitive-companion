import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { flushPromises } from "@vue/test-utils";
import AudioVisualizer from "@/components/AudioVisualizer.vue";

// The microphone is opened only while `recording` is true: never on mount, and its
// tracks are stopped as soon as recording ends.
describe("AudioVisualizer capture", () => {
  let contexts;
  let track;
  let getUserMedia;

  beforeEach(() => {
    contexts = [];
    track = { stop: vi.fn() };
    getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track] });
    const node = () => ({ connect: vi.fn(), disconnect: vi.fn() });
    class FakeAudioContext {
      constructor() {
        this.state = "suspended";
        this.destination = {};
        this.resume = vi.fn(async () => {
          this.state = "running";
        });
        this.close = vi.fn();
        contexts.push(this);
      }
      createMediaStreamSource = vi.fn(node);
      createBiquadFilter = vi.fn(() => ({ ...node(), frequency: {}, Q: {} }));
      createAnalyser = vi.fn(() => ({ ...node(), frequencyBinCount: 8 }));
      createScriptProcessor = vi.fn(() => node());
    }
    vi.stubGlobal("AudioContext", FakeAudioContext);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    vi.stubGlobal("requestAnimationFrame", vi.fn());
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    HTMLCanvasElement.prototype.getContext = vi.fn(() => null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not open the microphone until recording starts", async () => {
    const wrapper = mount(AudioVisualizer, { props: { recording: false } });
    await flushPromises();
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(contexts).toHaveLength(0);

    await wrapper.setProps({ recording: true });
    await flushPromises();

    expect(getUserMedia).toHaveBeenCalledOnce();
    // Created outside a tap, the context would stay suspended unless resumed.
    expect(contexts[0].state).toBe("running");
    wrapper.unmount();
  });

  it("stops the microphone tracks when recording ends", async () => {
    const wrapper = mount(AudioVisualizer, { props: { recording: true } });
    await flushPromises();

    await wrapper.setProps({ recording: false });
    await flushPromises();

    expect(track.stop).toHaveBeenCalled();
    expect(contexts[0].close).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("reports the microphone live only once it is really open, and closed again after", async () => {
    const wrapper = mount(AudioVisualizer, { props: { recording: true } });
    await flushPromises();
    await wrapper.setProps({ recording: false });
    await flushPromises();

    expect(wrapper.emitted("capture-change")).toEqual([
      [{ live: true, error: null }],
      [{ live: false, error: null }],
    ]);
    wrapper.unmount();
  });

  it("reports a microphone that could not be opened instead of claiming to listen", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    getUserMedia.mockRejectedValueOnce(
      Object.assign(new Error("denied"), { name: "NotAllowedError" }),
    );
    const wrapper = mount(AudioVisualizer, { props: { recording: true } });
    await flushPromises();

    expect(wrapper.emitted("capture-change")).toEqual([
      [{ live: false, error: "NotAllowedError" }],
    ]);
    // The half-built pipeline is torn down so the next recording starts afresh.
    expect(contexts[0].close).toHaveBeenCalled();
    wrapper.unmount();
  });
});
