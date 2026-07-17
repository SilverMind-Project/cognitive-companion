import { describe, expect, it } from "vitest";
import {
  calculateContentRect,
  convertShapeFromSpace,
  convertShapeToSpace,
  useSpatialCanvas,
} from "@/composables/useSpatialCanvas.js";

describe("useSpatialCanvas", () => {
  it("computes landscape letterbox content rect", () => {
    expect(
      calculateContentRect({
        naturalWidth: 1600,
        naturalHeight: 800,
        boxWidth: 400,
        boxHeight: 400,
      }),
    ).toEqual({
      naturalWidth: 1600,
      naturalHeight: 800,
      width: 400,
      height: 200,
      offsetX: 0,
      offsetY: 100,
    });
  });

  it("computes portrait letterbox content rect", () => {
    expect(
      calculateContentRect({
        naturalWidth: 800,
        naturalHeight: 1600,
        boxWidth: 400,
        boxHeight: 400,
      }),
    ).toEqual({
      naturalWidth: 800,
      naturalHeight: 1600,
      width: 200,
      height: 400,
      offsetX: 100,
      offsetY: 0,
    });
  });

  it("round-trips natural, ratio, and metres spaces", () => {
    const shape = {
      type: "polygon",
      points: [
        [0.25, 0.5],
        [0.75, 0.25],
      ],
    };
    const options = { naturalWidth: 2000, naturalHeight: 1000, mpp: 0.02 };

    for (const space of ["natural", "ratio", "metres"]) {
      const emitted = convertShapeToSpace(shape, space, options);
      expect(convertShapeFromSpace(emitted, space, options)).toEqual(shape);
    }
  });

  it("maps clicks through zoom and pan before normalizing", () => {
    const spatial = useSpatialCanvas({ naturalWidth: 1000, naturalHeight: 500 });
    spatial.actions.setViewport({ width: 500, height: 500 });
    spatial.zoom.state.zoom = 2;
    spatial.zoom.state.panX = 20;
    spatial.zoom.state.panY = 10;

    expect(spatial.toNormalized({ x: 270, y: 385 })).toEqual([0.25, 0.25]);
  });

  it("fails closed for metres conversion without mpp", () => {
    expect(() =>
      convertShapeToSpace({ type: "point", point: [0.5, 0.5] }, "metres", {
        naturalWidth: 100,
        naturalHeight: 100,
      }),
    ).toThrow("positive mpp");
  });
});
