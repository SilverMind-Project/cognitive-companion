<template>
  <v-card
    v-if="visible"
    class="canvas-context-menu"
    :style="{ top: `${y}px`, left: `${x}px` }"
    elevation="8"
  >
    <v-list density="compact">
      <v-list-item prepend-icon="mdi-pencil" title="Edit" @click="emit('edit', stepId)" />
      <v-list-item
        :prepend-icon="enabled ? 'mdi-eye-off' : 'mdi-eye'"
        :title="enabled ? 'Disable' : 'Enable'"
        @click="emit('toggle', stepId)"
      />
      <v-divider />
      <v-list-item
        prepend-icon="mdi-delete"
        title="Delete"
        color="error"
        @click="emit('delete', stepId)"
      />
    </v-list>
  </v-card>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
  stepId: { type: [Number, String], default: null },
  enabled: { type: Boolean, default: true },
});

const emit = defineEmits(["edit", "toggle", "delete"]);
</script>

<style scoped>
.canvas-context-menu {
  position: fixed;
  z-index: 30;
  min-width: 180px;
  border: 1px solid var(--cc-glass-border);
  background: var(--cc-bg-elevated);
}

.canvas-context-menu :deep(.v-list-item-title) {
  font-size: 0.8125rem;
  line-height: 1.25rem;
}
</style>
