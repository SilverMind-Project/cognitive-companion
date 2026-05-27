<template>
  <div class="inferred-badge d-flex align-center ga-1" :data-testid="`inferred-badge-${roomName}`">
    <v-icon size="12" color="warning">mdi-timer-sand</v-icon>
    <span class="text-caption font-weight-medium">{{ displayName }}, ~{{ duration }}</span>
    <v-btn
      icon="mdi-close"
      variant="text"
      size="x-small"
      density="compact"
      @click="$emit('dismiss')"
    />
  </div>
</template>

<script>
import { computed } from "vue";

export default {
  name: "InferredPresenceBadge",
  props: {
    roomName: { type: String, default: "" },
    personName: { type: String, default: "Someone" },
    since: { type: String, default: null },
  },
  emits: ["dismiss"],

  setup(props) {
    const displayName = computed(() => props.personName || "Someone");
    const duration = computed(() => {
      if (!props.since) return "? min";
      const secs = Math.round((Date.now() - new Date(props.since).getTime()) / 1000);
      if (secs < 60) return `${secs}s`;
      return `~${Math.round(secs / 60)} min`;
    });

    return { displayName, duration };
  },
};
</script>

<style scoped>
.inferred-badge {
  padding: 2px 8px;
  background: rgba(var(--v-theme-warning), 0.12);
  border-radius: 12px;
  display: inline-flex;
}
</style>
