<template>
  <AppDialog
    v-model="open"
    size="sm"
    persistent
    icon="mdi-account-convert"
    label="Correct"
    title="Identity"
    hint="Correct misidentified persons to improve tracking accuracy."
    confirm-label="Apply override"
    :confirm-loading="saving"
    @confirm="$emit('confirm')"
  >
    <div class="px-6 py-5">
      <div class="text-body-2 mb-2">
        PH: <strong>{{ correction.ph_id }}</strong>
      </div>
      <div class="text-body-2 mb-2">Camera: {{ correction.camera_id }}</div>
      <div class="text-body-2 mb-4">
        Current identity: {{ correction.previous_identity_id || "unknown" }}
      </div>
      <v-text-field
        v-model="correction.new_identity_id"
        label="New identity id"
        variant="outlined"
        placeholder="Leave blank to mark as UNKNOWN"
      />
      <v-text-field v-model="correction.reason" label="Reason" variant="outlined" />
    </div>
  </AppDialog>
</template>

<script setup>
import AppDialog from "@/components/common/AppDialog.vue";

defineProps({
  saving: { type: Boolean, default: false },
});
defineEmits(["confirm"]);

const open = defineModel({ type: Boolean, required: true });
const correction = defineModel("correction", { type: Object, required: true });
</script>
