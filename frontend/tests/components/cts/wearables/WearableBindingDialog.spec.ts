import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import WearableBindingDialog from "@/components/cts/wearables/WearableBindingDialog.vue";
import type { WearableDeviceAssociationsOut } from "@/services/modules/wearables";

vi.mock("@/services/timezone.js", () => ({
  formatDateTime: (iso: string) => iso,
}));

const baseDevice = {
  id: "11111111-1111-1111-1111-111111111111",
  tag_id: "grandma-band-1",
  device_kind: "uwb_tag" as const,
  label: "Grandma's band",
  adapter_id: "uwb-home",
  hardware_key: "00:01",
  is_active: true,
  last_heard_at: null,
  last_battery_fraction: 0.9,
  active_binding: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const baseAssociations: WearableDeviceAssociationsOut = {
  device_id: baseDevice.id,
  tag_id: baseDevice.tag_id,
  teaching_held: true,
  open_hold: {
    hold_id: "hold-1",
    tag_id: baseDevice.tag_id,
    reason: "swap_suspected",
    held_at: "2026-06-10T10:00:00Z",
    cleared_at: null,
    cleared_by: null,
  },
  associations: [
    {
      segment_id: "seg-active",
      ph_id: "ph-1",
      tag_id: baseDevice.tag_id,
      identity_id: "grandma",
      started_at: "2026-06-10T09:00:00Z",
      ended_at: "2026-06-10T09:30:00Z",
      attestation_grade: "trajectory",
      swap_suspected: false,
      close_reason: null,
      revoked_at: null,
      revoked_by: null,
      revoke_reason: null,
      gallery_rows_by_state: { auto_verified: 3 },
      gallery_rows_total: 3,
      attested_faces_total: 2,
      attested_faces_active: 2,
      attested_faces_revoked: 0,
      attested_faces_promoted: 0,
      inferred_ranges_live: 1,
      inferred_ranges_total: 1,
    },
    {
      segment_id: "seg-revoked",
      ph_id: "ph-2",
      tag_id: baseDevice.tag_id,
      identity_id: "grandma",
      started_at: "2026-06-10T08:00:00Z",
      ended_at: "2026-06-10T08:30:00Z",
      attestation_grade: "trajectory",
      swap_suspected: true,
      close_reason: "wearable_face_conflict",
      revoked_at: "2026-06-10T08:35:00Z",
      revoked_by: "system:swap_guard",
      revoke_reason: "swap_suspected",
      gallery_rows_by_state: { pending_review: 2 },
      gallery_rows_total: 2,
      attested_faces_total: 1,
      attested_faces_active: 0,
      attested_faces_revoked: 1,
      attested_faces_promoted: 0,
      inferred_ranges_live: 0,
      inferred_ranges_total: 1,
    },
  ],
};

describe("WearableBindingDialog teaching revocation UI", () => {
  it("renders teaching hold banner, taught counts, and emits revoke and resume events", async () => {
    const wrapper = mount(WearableBindingDialog, {
      props: {
        modelValue: true,
        device: baseDevice,
        history: [],
        loadingHistory: false,
        saving: false,
        associations: baseAssociations,
        loadingAssociations: false,
        associationsError: null,
      },
      global: {
        stubs: {
          AppDialog: { template: "<div><slot /></div>" },
          IdentityTargetPicker: true,
          "v-alert": { template: "<div class='v-alert'><slot /></div>" },
          "v-btn": {
            props: ["to", "loading", "disabled"],
            template: "<button><slot /></button>",
          },
          "v-chip": { template: "<span class='v-chip'><slot /></span>" },
          "v-divider": true,
          "v-table": { template: "<table><slot /></table>" },
          "v-text-field": true,
          "v-checkbox": true,
          "v-progress-circular": true,
        },
      },
    });

    expect(wrapper.find("[data-test='teaching-held-chip']").exists()).toBe(true);
    expect(wrapper.find("[data-test='teaching-held-banner']").exists()).toBe(true);
    expect(wrapper.find("[data-test='associations-table']").text()).toContain("3 body");
    expect(wrapper.find("[data-test='segment-revoked-chip']").exists()).toBe(true);

    // Revoke button only appears on unrevoked segments
    expect(wrapper.find("[data-test='revoke-segment-seg-revoked']").exists()).toBe(false);
    const revokeBtn = wrapper.find("[data-test='revoke-segment-seg-active']");
    expect(revokeBtn.exists()).toBe(true);
    await revokeBtn.trigger("click");
    expect(wrapper.emitted("revokeAssociation")).toEqual([["seg-active"]]);

    // Resume teaching emits tag_id
    const resumeBtn = wrapper.find("[data-test='resume-teaching-btn']");
    await resumeBtn.trigger("click");
    expect(wrapper.emitted("resumeTeaching")).toEqual([["grandma-band-1"]]);
  });
});
