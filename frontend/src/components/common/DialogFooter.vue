<template>
  <div>
    <v-divider />
    <v-card-actions class="px-6 py-3">
      <slot name="actions" />
      <template v-if="hint || $slots.hint">
        <v-icon size="small" color="medium-emphasis" class="mr-1">mdi-information-outline</v-icon>
        <span v-if="hint" class="text-caption text-medium-emphasis">{{ hint }}</span>
        <slot v-else name="hint" />
      </template>
      <v-spacer />
      <v-btn variant="text" @click="$emit('cancel')">{{ cancelLabel }}</v-btn>
      <v-btn
        color="primary"
        variant="flat"
        :loading="confirmLoading"
        :disabled="confirmDisabled"
        @click="$emit('confirm')"
      >
        {{ confirmLabel }}
      </v-btn>
    </v-card-actions>
  </div>
</template>

<script setup>
defineProps({
  hint: { type: String, default: "" },
  cancelLabel: { type: String, default: "Cancel" },
  confirmLabel: { type: String, default: "Save" },
  confirmLoading: { type: Boolean, default: false },
  confirmDisabled: { type: Boolean, default: false },
});

defineEmits(["cancel", "confirm"]);
</script>
