<template>
  <v-card class="glass-card pa-3" :class="{ 'cc-selected': selected }">
    <div class="d-flex align-center ga-2 mb-2">
      <v-chip size="small" :color="statusColor || undefined" variant="tonal">{{
        statusLabel
      }}</v-chip>
      <v-spacer />
      <v-checkbox
        v-if="mergeMode"
        :model-value="selected"
        density="compact"
        hide-details
        @update:model-value="$emit('toggle-select', cluster.cluster_id)"
      />
    </div>

    <div class="d-flex ga-2 mb-3 flex-wrap">
      <template v-if="cluster.recent_crop_urls.length">
        <v-img
          v-for="(url, idx) in cluster.recent_crop_urls.slice(0, 4)"
          :key="idx"
          :src="url"
          width="64"
          height="64"
          rounded="lg"
          cover
          class="cc-crop-thumb"
        />
      </template>
      <div v-else class="text-body-2 text-medium-emphasis">No crops available.</div>
    </div>

    <div class="text-body-2 mb-1">
      <strong>{{ cluster.sighting_count }}</strong> sighting{{
        cluster.sighting_count === 1 ? "" : "s"
      }}
      on <strong>{{ cluster.distinct_days }}</strong> distinct day{{
        cluster.distinct_days === 1 ? "" : "s"
      }}
    </div>
    <div class="text-caption text-medium-emphasis mb-3">
      First seen {{ formatDateOnly(cluster.first_seen_at) }} &middot; last seen
      {{ formatRelative(cluster.last_seen_at) }}
    </div>

    <div class="d-flex ga-2">
      <v-btn
        size="small"
        color="primary"
        variant="flat"
        prepend-icon="mdi-account-plus-outline"
        :disabled="cluster.status === 'named'"
        @click="$emit('name', cluster)"
      >
        Name
      </v-btn>
      <v-btn
        size="small"
        variant="outlined"
        prepend-icon="mdi-close"
        :disabled="cluster.status === 'named' || cluster.status === 'dismissed'"
        @click="$emit('dismiss', cluster.cluster_id)"
      >
        Dismiss
      </v-btn>
    </div>
  </v-card>
</template>

<script setup>
import { computed } from "vue";
import { formatDateOnly } from "@/services/timezone.js";
import { formatRelative } from "@/composables/useFormatRelative.js";

const props = defineProps({
  cluster: { type: Object, required: true },
  mergeMode: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
});

defineEmits(["name", "dismiss", "toggle-select"]);

const _STATUS_COLORS = {
  candidate: "info",
  surfaced: "warning",
  named: "success",
  dismissed: "",
};

const statusColor = computed(() => _STATUS_COLORS[props.cluster.status] ?? "");
const statusLabel = computed(
  () => props.cluster.status.charAt(0).toUpperCase() + props.cluster.status.slice(1),
);
</script>

<style scoped>
.cc-crop-thumb {
  border: 1px solid var(--cc-divider);
}
.cc-selected {
  border: 2px solid var(--cc-brand);
}
</style>
