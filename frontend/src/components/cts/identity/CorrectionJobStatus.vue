<template>
  <v-card variant="tonal" class="pa-3" :data-status="job.status">
    <div class="d-flex align-center ga-2">
      <v-progress-circular
        v-if="isActive"
        indeterminate
        size="18"
        width="2"
        color="primary"
      />
      <v-icon v-else :color="statusColor" :icon="statusIcon" />
      <div class="flex-grow-1">
        <div class="text-body-2 font-weight-medium">{{ statusLabel }}</div>
        <div class="text-caption text-medium-emphasis">
          Revision <span class="cc-code">{{ shortId(job.revision_id) }}</span>
        </div>
      </div>
      <v-btn
        v-if="job.status === 'failed'"
        size="small"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-refresh"
        @click="$emit('retry')"
      >
        Retry
      </v-btn>
    </div>

    <!-- Projection acknowledgement counts -->
    <div v-if="projectionRows.length" class="mt-2 d-flex flex-wrap ga-1">
      <v-chip
        v-for="p in projectionRows"
        :key="p.name"
        size="x-small"
        variant="tonal"
        :color="p.acked ? 'success' : undefined"
        :prepend-icon="p.acked ? 'mdi-check' : 'mdi-clock-outline'"
      >
        {{ p.name }}<span v-if="p.count != null" class="ml-1">· {{ p.count }}</span>
      </v-chip>
    </div>

    <v-alert
      v-if="job.status === 'failed' && job.last_error"
      type="error"
      density="compact"
      variant="tonal"
      class="mt-2 text-caption"
    >
      {{ job.last_error }}
    </v-alert>
  </v-card>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  job: { type: Object, required: true },
});
defineEmits(["retry"]);

const isActive = computed(() =>
  props.job.status === "pending" || props.job.status === "applying"
);

const STATUS = {
  pending: { label: "Queued…", icon: "mdi-clock-outline", color: "info" },
  applying: { label: "Applying correction…", icon: "mdi-progress-clock", color: "info" },
  completed: { label: "Correction applied", icon: "mdi-check-circle", color: "success" },
  failed: { label: "Correction failed", icon: "mdi-alert-circle", color: "error" },
};

const statusLabel = computed(() => STATUS[props.job.status]?.label || props.job.status);
const statusIcon = computed(() => STATUS[props.job.status]?.icon || "mdi-help-circle");
const statusColor = computed(() => STATUS[props.job.status]?.color || undefined);

// Each required projection, marked acknowledged when a row count exists for it.
const projectionRows = computed(() => {
  const required = props.job.required_projections || [];
  const counts = props.job.row_counts || {};
  return required.map((name) => ({
    name,
    acked: name in counts,
    count: name in counts ? counts[name] : null,
  }));
});

function shortId(id) {
  return id ? String(id).slice(0, 8) : "";
}
</script>
