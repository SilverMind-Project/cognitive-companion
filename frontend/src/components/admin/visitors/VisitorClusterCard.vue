<template>
  <v-card class="glass-card pa-3" :class="{ 'cc-selected': selected }">
    <div class="d-flex align-center ga-2 mb-2">
      <v-chip size="small" :color="statusColor || undefined" variant="tonal">{{
        statusLabel
      }}</v-chip>
      <v-spacer />
      <v-checkbox
        v-if="selectMode"
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

    <div v-if="cluster.status === 'attributed'" class="text-body-2 mb-1" data-test="attributed-to">
      Faces of <strong>{{ targets.nameOf(cluster.attributed_person_id) }}</strong>
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

    <div class="d-flex flex-wrap ga-2">
      <v-btn
        size="small"
        color="primary"
        variant="flat"
        prepend-icon="mdi-account-check-outline"
        :disabled="reviewDisabled"
        data-test="attribute"
        @click="$emit('attribute', cluster.cluster_id)"
      >
        {{ VERDICT_LABELS.is_member }}
      </v-btn>
      <v-btn
        size="small"
        variant="outlined"
        prepend-icon="mdi-account-plus-outline"
        :disabled="reviewDisabled"
        data-test="name"
        @click="$emit('name', cluster)"
      >
        {{ VERDICT_LABELS.new_person }}
      </v-btn>
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-close"
        :disabled="reviewDisabled || cluster.status === 'dismissed'"
        data-test="dismiss"
        @click="$emit('dismiss', cluster.cluster_id)"
      >
        {{ VISITOR_DISMISS_LABEL }}
      </v-btn>
    </div>
  </v-card>
</template>

<script setup>
import { computed } from "vue";
import { formatDateOnly } from "@/services/timezone.js";
import { formatRelative } from "@/composables/useFormatRelative.js";
import { VERDICT_LABELS, VISITOR_DISMISS_LABEL } from "@/constants/identityReview";
import { useIdentityTargetsStore } from "@/stores/identityTargets";

const props = defineProps({
  cluster: { type: Object, required: true },
  selectMode: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
});

defineEmits(["name", "attribute", "dismiss", "toggle-select"]);

const targets = useIdentityTargetsStore();
// A named cluster became a member and is final; every other state can be reviewed (again).
const reviewDisabled = computed(() => props.cluster.status === "named");

const _STATUS_COLORS = {
  candidate: "info",
  surfaced: "warning",
  named: "success",
  dismissed: "",
  attributed: "success",
};
const _STATUS_LABELS = { attributed: "Marked as member" };

const statusColor = computed(() => _STATUS_COLORS[props.cluster.status] ?? "");
const statusLabel = computed(
  () =>
    _STATUS_LABELS[props.cluster.status] ??
    props.cluster.status.charAt(0).toUpperCase() + props.cluster.status.slice(1),
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
