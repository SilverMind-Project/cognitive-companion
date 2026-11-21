<template>
  <AppDialog
    :model-value="modelValue"
    size="md"
    persistent
    icon="mdi-watch-variant"
    label="Wearable Binding"
    :title="device ? `${device.label} (${device.tag_id})` : 'Wearable binding'"
    :hide-footer="true"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="px-6 py-5">
      <div v-if="activeBinding" class="mb-5">
        <v-alert type="info" variant="tonal" class="mb-3" data-test="active-binding-banner">
          <div class="d-flex align-center justify-space-between flex-wrap ga-2">
            <div>
              Currently bound to
              <strong>{{ activeBinding.member_name || activeBinding.member_id }}</strong>
              since {{ formatDateTime(activeBinding.valid_from) }} (consent recorded by
              {{ activeBinding.consent_recorded_by }}).
            </div>
            <v-btn
              size="small"
              color="warning"
              variant="tonal"
              :loading="saving"
              data-test="unbind-btn"
              @click="$emit('unbind', device!.id)"
            >
              Unbind
            </v-btn>
          </div>
        </v-alert>
      </div>

      <div v-else class="mb-5">
        <div class="text-subtitle-2 font-weight-bold mb-3">Bind to a household member</div>
        <IdentityTargetPicker
          v-model="memberId"
          label="Household member"
          class="mb-3"
          data-test="bind-member-picker"
        />
        <v-text-field
          v-model="consentRecordedBy"
          label="Consent recorded by"
          hint="Full name of the caregiver or wearer who confirmed consent"
          persistent-hint
          class="mb-3"
          data-test="consent-recorded-by"
        />
        <v-checkbox
          v-model="consentConfirmed"
          label="I confirm that the wearer or authorized caregiver consented to wearing this tag for in-home identification."
          density="comfortable"
          hide-details
          class="mb-4"
          data-test="consent-checkbox"
        />
        <div class="d-flex justify-end ga-2">
          <v-btn variant="text" @click="$emit('update:modelValue', false)">Close</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :disabled="!canBind"
            :loading="saving"
            data-test="bind-submit-btn"
            @click="submitBind"
          >
            Bind device
          </v-btn>
        </div>
      </div>

      <v-divider class="mb-4" />

      <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-2">
        <div class="text-subtitle-2 font-weight-bold">Recent teaching periods</div>
        <v-chip
          v-if="associations?.teaching_held"
          size="small"
          color="warning"
          variant="tonal"
          prepend-icon="mdi-pause-circle-outline"
          data-test="teaching-held-chip"
        >
          Teaching paused
        </v-chip>
      </div>
      <v-alert
        v-if="associations?.teaching_held"
        type="warning"
        variant="tonal"
        density="compact"
        class="mb-3"
        data-test="teaching-held-banner"
      >
        <div class="d-flex align-center justify-space-between flex-wrap ga-2">
          <div>
            This wearable is held from teaching ({{ associations.open_hold?.reason || "revoked" }}).
            Review what it taught before resuming.
          </div>
          <v-btn
            size="small"
            color="warning"
            variant="flat"
            :loading="resumingTagId === device?.tag_id"
            data-test="resume-teaching-btn"
            @click="device && $emit('resumeTeaching', device.tag_id)"
          >
            Resume teaching
          </v-btn>
        </div>
      </v-alert>
      <div v-if="loadingAssociations" class="d-flex justify-center py-4">
        <v-progress-circular indeterminate size="24" color="primary" />
      </div>
      <v-alert
        v-else-if="associationsError"
        type="info"
        variant="tonal"
        density="compact"
        class="mb-3"
        data-test="associations-error"
      >
        {{ associationsError }}
      </v-alert>
      <div
        v-else-if="!(associations?.associations || []).length"
        class="text-body-2 text-medium-emphasis py-2 mb-3"
      >
        No wearable teaching periods recorded for this tag yet.
      </div>
      <v-table v-else density="compact" class="mb-4" data-test="associations-table">
        <thead>
          <tr>
            <th>Period</th>
            <th>Grade</th>
            <th>Taught</th>
            <th>Status</th>
            <th class="text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="seg in associations?.associations || []" :key="seg.segment_id">
            <td>
              <div>{{ formatDateTime(seg.started_at) }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ seg.ended_at ? formatDateTime(seg.ended_at) : "Active" }}
              </div>
            </td>
            <td>{{ seg.attestation_grade }}</td>
            <td>
              <div>{{ seg.gallery_rows_total }} body</div>
              <div class="text-caption text-medium-emphasis">
                {{ seg.attested_faces_total ?? 0 }} faces · {{ seg.inferred_ranges_total }} history
              </div>
            </td>
            <td>
              <v-chip
                v-if="seg.revoked_at"
                size="x-small"
                color="error"
                variant="tonal"
                data-test="segment-revoked-chip"
              >
                Revoked
              </v-chip>
              <v-chip v-else-if="seg.swap_suspected" size="x-small" color="warning" variant="tonal">
                Swap suspected
              </v-chip>
              <span v-else class="text-caption text-medium-emphasis">Active</span>
            </td>
            <td class="text-right">
              <v-btn
                v-if="seg.gallery_rows_total > 0"
                size="x-small"
                variant="text"
                :to="{
                  path: '/admin/cts/reid-review',
                  query: {
                    seed_association_id: seg.segment_id,
                    state: seg.revoked_at ? 'pending_review' : 'auto_verified',
                  },
                }"
                data-test="review-taught-link"
              >
                Review
              </v-btn>
              <v-btn
                v-if="!seg.revoked_at"
                size="x-small"
                variant="tonal"
                color="error"
                :loading="revokingSegmentId === seg.segment_id"
                :data-test="`revoke-segment-${seg.segment_id}`"
                @click="$emit('revokeAssociation', seg.segment_id)"
              >
                Revoke what this taught
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>

      <v-divider class="mb-4" />

      <div class="text-subtitle-2 font-weight-bold mb-2">Binding history</div>
      <div v-if="loadingHistory" class="d-flex justify-center py-4">
        <v-progress-circular indeterminate size="24" color="primary" />
      </div>
      <div v-else-if="!history.length" class="text-body-2 text-medium-emphasis py-2">
        No bindings recorded for this device yet.
      </div>
      <v-table v-else density="compact" data-test="binding-history-table">
        <thead>
          <tr>
            <th>Member</th>
            <th>From</th>
            <th>To</th>
            <th>Consent by</th>
            <th>Recorded by</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in history" :key="row.id">
            <td>{{ row.member_name || row.member_id || "Deleted member" }}</td>
            <td>{{ formatDateTime(row.valid_from) }}</td>
            <td>{{ row.valid_to ? formatDateTime(row.valid_to) : "Active" }}</td>
            <td>{{ row.consent_recorded_by }}</td>
            <td>{{ row.created_by }}</td>
          </tr>
        </tbody>
      </v-table>
    </div>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AppDialog from "@/components/common/AppDialog.vue";
import IdentityTargetPicker from "@/components/identity/IdentityTargetPicker.vue";
import { formatDateTime } from "@/services/timezone.js";
import type {
  WearableBindingCreate,
  WearableBindingOut,
  WearableDeviceAssociationsOut,
  WearableDeviceOut,
} from "@/services/modules/wearables";

const props = defineProps<{
  modelValue: boolean;
  device: WearableDeviceOut | null;
  history: WearableBindingOut[];
  loadingHistory: boolean;
  saving: boolean;
  associations?: WearableDeviceAssociationsOut | null;
  loadingAssociations?: boolean;
  associationsError?: string | null;
  revokingSegmentId?: string | null;
  resumingTagId?: string | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  bind: [deviceId: string, body: WearableBindingCreate];
  unbind: [deviceId: string];
  revokeAssociation: [segmentId: string];
  resumeTeaching: [tagId: string];
}>();

const memberId = ref<string | null>(null);
const consentRecordedBy = ref("");
const consentConfirmed = ref(false);

const activeBinding = computed(() => props.history.find((b) => b.valid_to === null) ?? null);

const canBind = computed(
  () =>
    Boolean(props.device) &&
    Boolean(memberId.value) &&
    consentConfirmed.value &&
    consentRecordedBy.value.trim().length > 0,
);

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      memberId.value = null;
      consentRecordedBy.value = "";
      consentConfirmed.value = false;
    }
  },
);

function submitBind() {
  if (!props.device || !memberId.value || !canBind.value) return;
  emit("bind", props.device.id, {
    member_id: memberId.value,
    consent_confirmed: consentConfirmed.value,
    consent_recorded_by: consentRecordedBy.value.trim(),
  });
}
</script>
