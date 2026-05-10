<template>
  <div>
    <div class="dialog-header px-6 py-4 d-flex align-center">
      <v-avatar size="40" class="dialog-header-icon mr-3">
        <v-icon color="white">{{ icon }}</v-icon>
      </v-avatar>
      <div class="flex-grow-1">
        <div class="text-overline text-medium-emphasis">{{ label }}</div>
        <div class="text-h6 font-weight-bold tracking-tight">{{ title }}</div>
      </div>
      <slot name="actions" />
      <v-btn
        v-if="closable"
        icon="mdi-close"
        variant="text"
        @click="$emit('close')"
      />
    </div>
    <v-divider />
  </div>
</template>

<script setup>
defineProps({
  icon: { type: String, required: true },
  label: { type: String, required: true },
  title: { type: String, required: true },
  closable: { type: Boolean, default: true },
});

defineEmits(["close"]);
</script>
