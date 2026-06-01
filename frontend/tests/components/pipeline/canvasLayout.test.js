import { describe, expect, it } from "vitest";
import { applyDagreLayout } from "../../../src/components/pipeline/canvasLayout.js";

describe("applyDagreLayout", () => {
  it("assigns positions to all nodes", () => {
    const nodes = [
      { id: "1", position: { x: 0, y: 0 } },
      { id: "2", position: { x: 0, y: 0 } },
    ];
    const edges = [{ source: "1", target: "2" }];

    const laidOut = applyDagreLayout(nodes, edges);

    expect(laidOut).toHaveLength(2);
    expect(laidOut[0].position).toEqual({
      x: expect.any(Number),
      y: expect.any(Number),
    });
    expect(laidOut[1].position).toEqual({
      x: expect.any(Number),
      y: expect.any(Number),
    });
  });

  it("positions earlier nodes to the left of later nodes in LR direction", () => {
    const laidOut = applyDagreLayout(
      [
        { id: "start", position: { x: 0, y: 0 } },
        { id: "finish", position: { x: 0, y: 0 } },
      ],
      [{ source: "start", target: "finish" }],
    );

    const start = laidOut.find((node) => node.id === "start");
    const finish = laidOut.find((node) => node.id === "finish");
    expect(start.position.x).toBeLessThan(finish.position.x);
  });

  it("handles an empty node array gracefully", () => {
    expect(applyDagreLayout([], [])).toEqual([]);
  });
});
