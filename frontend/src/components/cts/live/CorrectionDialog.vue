<template>
  <v-dialog v-model="open" max-width="520" persistent>
    <v-card>
      <DialogHeader
        icon="mdi-account-convert"
        label="Correct"
        title="Identity"
        @close="open = false"
      />
      <v-card-text>
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
      </v-card-text>
      <DialogFooter
        hint="Correct misidentified persons to improve tracking accuracy."
        confirm-label="Apply override"
        :confirm-loading="saving"
        @cancel="open = false"
        @confirm="$emit('confirm')"
      />
    </v-card>
  </v-dialog>
</template>

<script setup>
import DialogHeader from "@/components/common/DialogHeader.vue";
import DialogFooter from "@/components/common/DialogFooter.vue";

defineProps({
  saving: { type: Boolean, default: false },
});
defineEmits(["confirm"]);

const open = defineModel({ type: Boolean, required: true });
const correction = defineModel("correction", { type: Object, required: true });
</script>
