import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { h, nextTick } from "vue";
import CcSpatialEditor from "@/components/common/CcSpatialEditor.vue";

const stubs = {
  CcZoomControls: { template: "<div />" },
  "v-icon": { template: "<i />" },
  "v-spacer": { template: "<span />" },
  "v-btn": {
    emits: ["click"],
    template: "<button @click=\"$emit('click')\"><slot /></button>",
  },
};

async function mountEditor(props = {}, slots = {}) {
  const wrapper = mount(CcSpatialEditor, {
    props: {
      modelValue: [],
      imageUrl: "/sample.jpg",
      mode: "polygon",
      showZoom: false,
      showFooter: false,
      ...props,
    },
    slots,
    global: { stubs },
  });
  const container = wrapper.find(".cc-spatial-editor").element;
  container.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500 });

  const img = wrapper.find("img").element;
  Object.defineProperty(img, "naturalWidth", { configurable: true, value: 1000 });
  Object.defineProperty(img, "naturalHeight", { configurable: true, value: 500 });
  Object.defineProperty(img, "offsetWidth", { configurable: true, value: 1000 });
  Object.defineProperty(img, "offsetHeight", { configurable: true, value: 500 });
  Object.defineProperty(img, "offsetLeft", { configurable: true, value: 0 });
  Object.defineProperty(img, "offsetTop", { configurable: true, value: 0 });
  await wrapper.find("img").trigger("load");
  await nextTick();
  return wrapper;
}

function latestUpdate(wrapper) {
  const events = wrapper.emitted("update:modelValue");
  return events[events.length - 1][0];
}

describe("CcSpatialEditor", () => {
  it("creates polygon vertices in normalized coordinates", async () => {
    const wrapper = await mountEditor();
    const svg = wrapper.find("svg");

    await svg.trigger("click", { clientX: 250, clientY: 125, detail: 1 });

    expect(latestUpdate(wrapper)).toEqual([
      { id: expect.any(String), type: "polygon", points: [[0.25, 0.25]] },
    ]);
  });

  it("creates point shapes", async () => {
    const wrapper = await mountEditor({ mode: "point" });

    await wrapper.find("svg").trigger("click", { clientX: 500, clientY: 250, detail: 1 });

    expect(latestUpdate(wrapper)[0]).toEqual({
      id: expect.any(String),
      type: "point",
      point: [0.5, 0.5],
    });
  });

  it("creates line shapes with two clicks", async () => {
    const wrapper = await mountEditor({ mode: "line" });
    const svg = wrapper.find("svg");

    await svg.trigger("click", { clientX: 100, clientY: 100, detail: 1 });
    await wrapper.setProps({ modelValue: latestUpdate(wrapper) });
    await svg.trigger("click", { clientX: 300, clientY: 200, detail: 1 });

    expect(latestUpdate(wrapper)[0]).toEqual({
      id: expect.any(String),
      type: "line",
      points: [[0.1, 0.2], [0.3, 0.4]],
    });
  });

  it("creates rectangles by dragging", async () => {
    const wrapper = await mountEditor({ mode: "rect" });
    const svg = wrapper.find("svg");

    await svg.trigger("mousedown", { button: 0, clientX: 100, clientY: 100 });
    window.dispatchEvent(new MouseEvent("mousemove", { clientX: 300, clientY: 200 }));
    window.dispatchEvent(new MouseEvent("mouseup"));

    expect(latestUpdate(wrapper)[0]).toEqual({
      id: expect.any(String),
      type: "rect",
      x: 0.1,
      y: 0.2,
      w: 0.2,
      h: 0.2,
    });
  });

  it("drags polygon vertices", async () => {
    const wrapper = await mountEditor({
      modelValue: [{ id: "poly", type: "polygon", points: [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]] }],
    });
    const handle = wrapper.find(".cc-spatial-editor__handle-hit");

    await handle.trigger("mousedown", { button: 0, clientX: 100, clientY: 100 });
    window.dispatchEvent(new MouseEvent("mousemove", { clientX: 200, clientY: 150 }));
    window.dispatchEvent(new MouseEvent("mouseup"));

    expect(latestUpdate(wrapper)[0].points[0]).toEqual([0.2, 0.3]);
  });

  it("hides internal polygon geometry while retaining vertex handles", async () => {
    const wrapper = await mountEditor({
      hideInternalPolygon: true,
      modelValue: [{ id: "poly", type: "polygon", points: [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]] }],
    });

    expect(wrapper.find(".cc-spatial-editor__shape polygon").exists()).toBe(false);
    expect(wrapper.findAll(".cc-spatial-editor__handle-hit")).toHaveLength(3);
  });

  it("exposes false isDragging to overlay slots at rest", async () => {
    const wrapper = await mountEditor(
      {},
      {
        overlay: ({ isDragging }) => h(
          "text",
          { "data-testid": "drag-state" },
          String(isDragging),
        ),
      },
    );

    expect(wrapper.find("[data-testid='drag-state']").text()).toBe("false");
  });

  it("shows straight polygon geometry while a vertex is actively dragged", async () => {
    const wrapper = await mountEditor({
      hideInternalPolygon: true,
      modelValue: [{ id: "poly", type: "polygon", points: [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]] }],
    });

    await wrapper.find(".cc-spatial-editor__handle-hit").trigger("mousedown", {
      button: 0,
      clientX: 100,
      clientY: 100,
    });

    expect(wrapper.find(".cc-spatial-editor__shape polygon").exists()).toBe(true);
    window.dispatchEvent(new MouseEvent("mouseup"));
    await nextTick();
    expect(wrapper.find(".cc-spatial-editor__shape polygon").exists()).toBe(false);
  });

  it("does not edit in readonly mode", async () => {
    const wrapper = await mountEditor({ readonly: true });

    await wrapper.find("svg").trigger("click", { clientX: 250, clientY: 125, detail: 1 });

    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
  });

  it("applies an optional class only to the background image", async () => {
    const wrapper = await mountEditor({ imageClass: "cc-floor-plan-background-image" });

    expect(wrapper.find("img").classes()).toContain("cc-floor-plan-background-image");
    expect(wrapper.find(".cc-spatial-editor").classes()).not.toContain(
      "cc-floor-plan-background-image",
    );
  });
});
