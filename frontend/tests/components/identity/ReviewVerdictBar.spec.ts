import { describe, it, expect, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("@/services/modules/identity_targets", async () =>
  (await import("../../support/reviewVocabulary")).identityTargetsModuleMock(),
);

import ReviewVerdictBar from "@/components/identity/ReviewVerdictBar.vue";
import type { IdentityTarget } from "@/services/modules/identity_targets";

const stubs = {
  "v-btn": {
    template:
      "<button :disabled='disabled' :title='title' :data-variant='variant' @click=\"$emit('click')\"><slot /></button>",
    props: ["disabled", "title", "variant"],
    emits: ["click"],
  },
  "v-alert": { template: "<div><slot /></div>" },
};

function member(id: string, faceEnrolled: boolean | null = true): IdentityTarget {
  return {
    identity_id: id,
    display_name: id.toUpperCase(),
    is_active: true,
    is_guest: false,
    face_enrolled: faceEnrolled,
  };
}

type BarProps = InstanceType<typeof ReviewVerdictBar>["$props"];

async function mountBar(props: BarProps) {
  const wrapper = mount(ReviewVerdictBar, { props, global: { stubs } });
  await flushPromises();
  return wrapper;
}

describe("ReviewVerdictBar", () => {
  it("numbers the members, then lists the surface's other verdicts with keys and effects", async () => {
    const wrapper = await mountBar({
      surface: "face_calibration",
      members: [member("amma"), member("appa")],
    });

    expect(wrapper.get("[data-test='member-amma']").text()).toBe("1AMMA");
    expect(wrapper.get("[data-test='member-appa']").text()).toBe("2APPA");
    expect(wrapper.get("[data-test='verdict-not_enrolled']").text()).toBe("nNot in the household");
    expect(wrapper.get("[data-test='verdict-not_usable']").attributes("title")).toBe(
      "Server: left out of the fit.",
    );
    // "Someone new" needs a name, so it is never a one-key decision.
    expect(wrapper.find("[data-test='verdict-new_person']").exists()).toBe(false);
    expect(wrapper.get("[data-test='verdict-keys']").text()).toContain(
      "number for a member, n for not in the household, x for not usable, arrows to move",
    );
  });

  it("disables members without enrolled faces when the decision needs one", async () => {
    const wrapper = await mountBar({
      surface: "visitors",
      members: [member("amma"), member("guest", false)],
    });

    expect(wrapper.get("[data-test='member-amma']").attributes("disabled")).toBeUndefined();
    expect(wrapper.get("[data-test='member-guest']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-test='member-guest']").attributes("title")).toContain(
      "no enrolled face photos",
    );
  });

  it("highlights the proposal, explains disabled members, and emits intents", async () => {
    const wrapper = await mountBar({
      surface: "reid_review",
      members: [member("amma"), member("appa")],
      proposedId: "appa",
      membersDisabled: true,
      membersDisabledReason: "Not eligible.",
      navigable: false,
    });

    expect(wrapper.get("[data-test='member-appa']").attributes("data-variant")).toBe("flat");
    expect(wrapper.get("[data-test='member-amma']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-test='members-disabled-reason']").text()).toBe("Not eligible.");
    expect(wrapper.get("[data-test='verdict-keys']").text()).not.toContain("arrows");

    await wrapper.get("[data-test='verdict-not_usable']").trigger("click");
    expect(wrapper.emitted("verdict")?.[0]).toEqual(["not_usable"]);
  });
});
