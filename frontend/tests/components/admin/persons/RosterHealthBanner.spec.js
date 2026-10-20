import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const { getRosterHealth } = vi.hoisted(() => ({ getRosterHealth: vi.fn() }));

vi.mock("@/services/modules/persons", () => ({ getRosterHealth }));

import RosterHealthBanner from "@/components/admin/persons/RosterHealthBanner.vue";

const stubs = {
  "v-alert": {
    template: "<div class='v-alert' :data-type='type'><slot /></div>",
    props: ["type", "variant", "density"],
  },
  "router-link": { template: "<a :href='to'><slot /></a>", props: ["to"] },
};

function envelope(overrides = {}) {
  return {
    members_without_face_enrollment: [
      { member_id: "amma", name: "Amma", embedding_count: 3 },
      { member_id: "uncle", name: "Uncle", embedding_count: 0 },
    ],
    min_face_embeddings: 5,
    visitor_clustering_enabled: true,
    surfaced_unnamed_visitor_clusters: 2,
    is_complete: false,
    checked_at: "2026-10-20T09:00:00Z",
    ...overrides,
  };
}

async function mountBanner() {
  const wrapper = mount(RosterHealthBanner, { global: { stubs } });
  await flushPromises();
  return wrapper;
}

describe("RosterHealthBanner", () => {
  beforeEach(() => {
    getRosterHealth.mockReset();
  });

  it("names members lacking enrollment with their photo counts", async () => {
    getRosterHealth.mockResolvedValue(envelope());
    const wrapper = await mountBanner();

    const missing = wrapper.get("[data-testid='roster-missing']").text();
    expect(missing).toContain("at least 5 enrollment photos");
    expect(missing).toContain("Amma (3), Uncle (0)");
  });

  it("counts recurring visitors and links to visitor review", async () => {
    getRosterHealth.mockResolvedValue(envelope());
    const wrapper = await mountBanner();

    const visitors = wrapper.get("[data-testid='roster-visitors']");
    expect(visitors.text()).toContain("2 recurring visitors are waiting");
    expect(visitors.get("a").attributes("href")).toBe("/admin/visitors");
  });

  it("omits the visitor line when none are waiting", async () => {
    getRosterHealth.mockResolvedValue(envelope({ surfaced_unnamed_visitor_clusters: 0 }));
    const wrapper = await mountBanner();

    expect(wrapper.find("[data-testid='roster-visitors']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='roster-missing']").exists()).toBe(true);
  });

  it("renders nothing when the roster is complete", async () => {
    getRosterHealth.mockResolvedValue(
      envelope({
        members_without_face_enrollment: [],
        surfaced_unnamed_visitor_clusters: 0,
        is_complete: true,
      }),
    );
    const wrapper = await mountBanner();

    expect(wrapper.find("[data-testid='roster-health-banner']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='roster-health-error']").exists()).toBe(false);
  });

  it("states the check is unavailable instead of claiming a complete roster", async () => {
    getRosterHealth.mockRejectedValue(new Error("Person identification service is unreachable"));
    const wrapper = await mountBanner();

    expect(wrapper.find("[data-testid='roster-health-banner']").exists()).toBe(false);
    expect(wrapper.get("[data-testid='roster-health-error']").text()).toContain(
      "Person identification service is unreachable",
    );
  });

  it("refresh re-fetches and replaces the result", async () => {
    getRosterHealth.mockResolvedValueOnce(envelope());
    const wrapper = await mountBanner();
    getRosterHealth.mockResolvedValueOnce(
      envelope({
        members_without_face_enrollment: [],
        surfaced_unnamed_visitor_clusters: 0,
        is_complete: true,
      }),
    );

    await wrapper.vm.refresh();
    await flushPromises();

    expect(getRosterHealth).toHaveBeenCalledTimes(2);
    expect(wrapper.find("[data-testid='roster-health-banner']").exists()).toBe(false);
  });
});
