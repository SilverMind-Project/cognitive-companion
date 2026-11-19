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
  WearableDeviceOut,
} from "@/services/modules/wearables";

const props = defineProps<{
  modelValue: boolean;
  device: WearableDeviceOut | null;
  history: WearableBindingOut[];
  loadingHistory: boolean;
  saving: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  bind: [deviceId: string, body: WearableBindingCreate];
  unbind: [deviceId: string];
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
