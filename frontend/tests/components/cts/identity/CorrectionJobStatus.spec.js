import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import CorrectionJobStatus from "@/components/cts/identity/CorrectionJobStatus.vue";

const stubs = {
  "v-card": { template: "<div class='v-card' :data-status='$attrs[\"data-status\"]'><slot /></div>" },
  "v-progress-circular": { template: "<div class='spinner' />" },
  "v-icon": { template: "<i :data-icon='icon' />", props: ["icon", "color"] },
  "v-btn": { template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-chip": { template: "<span class='chip'><slot /></span>", props: ["color"] },
  "v-alert": { template: "<div class='alert'><slot /></div>", props: ["type"] },
  "v-spacer": { template: "<span />" },
};

function job(over = {}) {
  return {
    revision_id: "rev-123456789",
    status: "applying",
    required_projections: ["cc"],
    row_counts: {},
    attempts: 0,
    last_error: null,
    ...over,
  };
}

function mountStatus(j) {
  return mount(CorrectionJobStatus, { props: { job: j }, global: { stubs } });
}

describe("CorrectionJobStatus", () => {
  it("shows a spinner while applying", () => {
    const w = mountStatus(job({ status: "applying" }));
    expect(w.find(".spinner").exists()).toBe(true);
    expect(w.text()).toContain("Applying");
  });

  it("shows completed with acknowledged projection counts", () => {
    const w = mountStatus(job({ status: "completed", row_counts: { cc: 4 } }));
    expect(w.text()).toContain("Correction applied");
    expect(w.text()).toContain("cc");
    expect(w.text()).toContain("4");
  });

  it("shows a retry button and error on failure", async () => {
    const w = mountStatus(job({ status: "failed", last_error: "projection timeout" }));
    expect(w.text()).toContain("Correction failed");
    expect(w.text()).toContain("projection timeout");
    await w.find("button").trigger("click");
    expect(w.emitted("retry")).toBeTruthy();
  });
});
