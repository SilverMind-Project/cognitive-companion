import { mount } from "@vue/test-utils";
import { describe, it, expect, vi } from "vitest";
import CoverageCameraMap from "@/components/cts/floor/CoverageCameraMap.vue";

const MOCK_PROPS = {
  loading: false,
  floorPlanUrl: "http://example.com/fp.png",
  imgReady: true,
  imgW: 1000,
  imgH: 500,
  cameras: [],
  uncalibrated: [],
  maraudersEnabled: false,
  toSvgPoints: vi.fn((poly) => poly.map(([x, y]) => `${x * 1000},${y * 500}`).join(" ")),
  centroid: vi.fn(() => [0, 0]),
  tokBrand: "red",
  tokBrandSoft: "pink",
  tokText3: "grey",
};

const STUBS = {
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-spacer": { template: "<div><slot /></div>" },
  "v-btn": { template: "<button><slot /></button>" },
  "v-divider": { template: "<hr />" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-alert": { template: "<div><slot /></div>" },
  MaraudersInkPolygon: { template: "<div />", props: ["points", "canvasW", "canvasH", "seedKey"] },
};

describe("CoverageCameraMap", () => {
  it("renders today's flat fill when camera has no anchor (characterization case)", () => {
    const wrapper = mount(CoverageCameraMap, {
      props: {
        ...MOCK_PROPS,
        cameras: [
          {
            camera_id: "cam-1",
            visibility_polygon: [
              [0, 0],
              [0.1, 0],
              [0.1, 0.1],
              [0, 0.1],
            ],
            // No marker or marker_estimate
          },
        ],
      },
      global: { stubs: STUBS },
    });

    const polygon = wrapper.find("polygon");
    expect(polygon.exists()).toBe(true);
    expect(polygon.attributes("fill")).toBe("pink");
    expect(wrapper.find("radialGradient").exists()).toBe(false);
  });

  it("renders a gradient-filled polygon when camera has a marker", () => {
    const wrapper = mount(CoverageCameraMap, {
      props: {
        ...MOCK_PROPS,
        cameras: [
          {
            camera_id: "cam-2",
            visibility_polygon: [
              [0, 0],
              [0.1, 0],
              [0.1, 0.1],
              [0, 0.1],
            ],
            marker: { x_norm: 0.05, y_norm: 0.05 },
          },
        ],
      },
      global: { stubs: STUBS },
    });

    const polygon = wrapper.find("polygon");
    expect(polygon.exists()).toBe(true);
    expect(polygon.attributes("fill")).toBe("url(#falloff-cam-2)");

    const gradient = wrapper.find("radialGradient#falloff-cam-2");
    expect(gradient.exists()).toBe(true);
    const stops = gradient.findAll("stop");
    expect(stops.length).toBe(2);
    expect(stops[0].attributes("offset")).toBe("40%");
    expect(stops[0].attributes("stop-opacity")).toBe("1");
    expect(stops[1].attributes("offset")).toBe("100%");
    expect(stops[1].attributes("stop-opacity")).toBe("0.15");
  });

  it("renders a gradient-filled polygon when camera has an estimate", () => {
    const wrapper = mount(CoverageCameraMap, {
      props: {
        ...MOCK_PROPS,
        cameras: [
          {
            camera_id: "cam-3",
            visibility_polygon: [
              [0, 0],
              [0.1, 0],
              [0.1, 0.1],
              [0, 0.1],
            ],
            marker_estimate: { x_norm: 0.05, y_norm: 0.05 },
          },
        ],
      },
      global: { stubs: STUBS },
    });

    const polygon = wrapper.find("polygon");
    expect(polygon.exists()).toBe(true);
    expect(polygon.attributes("fill")).toBe("url(#falloff-cam-3)");
    expect(wrapper.find("radialGradient#falloff-cam-3").exists()).toBe(true);
  });

  it("renders MaraudersInkPolygon with no gradient defs when marauders is enabled", () => {
    const wrapper = mount(CoverageCameraMap, {
      props: {
        ...MOCK_PROPS,
        maraudersEnabled: true,
        cameras: [
          {
            camera_id: "cam-4",
            visibility_polygon: [
              [0, 0],
              [0.1, 0],
              [0.1, 0.1],
              [0, 0.1],
            ],
            marker: { x_norm: 0.05, y_norm: 0.05 },
          },
        ],
      },
      global: { stubs: STUBS },
    });

    // Should not render polygon
    expect(wrapper.find("polygon").exists()).toBe(false);
    // Should not render radial gradient for marauders
    expect(wrapper.find("radialGradient").exists()).toBe(false);
  });
});
