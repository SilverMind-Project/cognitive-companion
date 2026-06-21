<template>
  <div>
    <!-- Scope: frame-only vs proposed segment -->
    <div v-if="allowFrameOnly" class="mb-3">
      <CcSegmentedToggle
        :model-value="scopeMode"
        :options="scopeOptions"
        @update:model-value="$emit('update:scopeMode', $event)"
      />
    </div>

    <template v-if="scopeMode === 'segment'">
      <div v-if="!proposal" class="text-caption text-medium-emphasis">
        No segment proposed.
      </div>
      <template v-else>
        <div class="text-caption text-medium-emphasis mb-2">
          Adjust the start and end to observations within the proposed segment. To
          extend past a boundary, start a new proposal from that observation.
        </div>

        <div class="d-flex ga-3 flex-wrap">
          <!-- Start boundary -->
          <div class="boundary-col flex-grow-1">
            <div class="d-flex align-center ga-1 mb-1">
              <span class="text-caption font-weight-medium">Start</span>
              <v-icon
                v-if="isHardBoundary(proposal.start.reason)"
                size="14"
                color="var(--cc-text-3)"
                icon="mdi-lock"
              >
                <v-tooltip activator="parent" location="top">
                  Hard boundary: {{ boundaryReason(proposal.start.reason) }}
                </v-tooltip>
              </v-icon>
            </div>
            <v-select
              :model-value="startId"
              :items="startItems"
              item-title="title"
              item-value="value"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="$emit('update:startId', $event)"
            />
            <v-img
              v-if="thumbFor(startId)"
              :src="displaySrc(thumbFor(startId))"
              height="72"
              cover
              class="mt-1 rounded"
            />
          </div>

          <!-- End boundary -->
          <div class="boundary-col flex-grow-1">
            <div class="d-flex align-center ga-1 mb-1">
              <span class="text-caption font-weight-medium">End</span>
              <v-icon
                v-if="isHardBoundary(proposal.end.reason)"
                size="14"
                color="var(--cc-text-3)"
                icon="mdi-lock"
              >
                <v-tooltip activator="parent" location="top">
                  Hard boundary: {{ boundaryReason(proposal.end.reason) }}
                </v-tooltip>
              </v-icon>
            </div>
            <v-select
              :model-value="endId"
              :items="endItems"
              item-title="title"
              item-value="value"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="$emit('update:endId', $event)"
            />
            <v-img
              v-if="thumbFor(endId)"
              :src="displaySrc(thumbFor(endId))"
              height="72"
              cover
              class="mt-1 rounded"
            />
          </div>
        </div>

        <div class="text-caption text-medium-emphasis mt-2">
          {{ selectedCount }} observation(s) selected.
        </div>
      </template>
    </template>

    <div v-else class="text-caption text-medium-emphasis">
      Applies to this single frame only.
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";
import { formatDateTime } from "@/services/timezone.js";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode.js";

const props = defineProps({
  proposal: { type: Object, default: null },
  // Observations keyed for labels/thumbnails (observation_id, captured_at, camera_id, image_url).
  observations: { type: Array, default: () => [] },
  scopeMode: { type: String, default: "segment" }, // 'frame_only' | 'segment'
  allowFrameOnly: { type: Boolean, default: false },
  startId: { type: String, default: "" },
  endId: { type: String, default: "" },
});

defineEmits(["update:scopeMode", "update:startId", "update:endId"]);

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

// Reasons that mark a structural stop the operator may not select past.
const HARD_REASONS = new Set(["split", "merge", "operator_revision"]);

const scopeOptions = [
  { value: "frame_only", label: "This frame" },
  { value: "segment", label: "Segment" },
];

const obsById = computed(() => {
  const map = new Map();
  for (const o of props.observations) {
    if (o.observation_id) map.set(o.observation_id, o);
  }
  return map;
});

// Ordered observation rows for the proposed segment, with display labels.
const orderedItems = computed(() => {
  const ids = props.proposal?.observation_ids || [];
  return ids.map((id) => {
    const o = obsById.value.get(id);
    const when = o?.captured_at || boundaryTime(id);
    const cam = o?.camera_id ? ` · ${o.camera_id}` : "";
    return {
      value: id,
      title: `${formatDateTime(when) || id}${cam}`,
      captured_at: when,
    };
  });
});

const startIndex = computed(() =>
  orderedItems.value.findIndex((i) => i.value === props.startId)
);
const endIndex = computed(() =>
  orderedItems.value.findIndex((i) => i.value === props.endId)
);

// Start may not move past the chosen end, and vice versa (no inverted range).
const startItems = computed(() => {
  const end = endIndex.value < 0 ? orderedItems.value.length - 1 : endIndex.value;
  return orderedItems.value.filter((_i, idx) => idx <= end);
});
const endItems = computed(() => {
  const start = startIndex.value < 0 ? 0 : startIndex.value;
  return orderedItems.value.filter((_i, idx) => idx >= start);
});

const selectedCount = computed(() => {
  if (startIndex.value < 0 || endIndex.value < 0) return 0;
  return endIndex.value - startIndex.value + 1;
});

function boundaryTime(id) {
  if (props.proposal?.start?.observation_id === id) return props.proposal.start.captured_at;
  if (props.proposal?.end?.observation_id === id) return props.proposal.end.captured_at;
  return null;
}

function thumbFor(id) {
  return obsById.value.get(id)?.image_url || "";
}

function isHardBoundary(reason) {
  return HARD_REASONS.has(reason);
}

function boundaryReason(reason) {
  return (reason || "").replace(/_/g, " ");
}
</script>

<style scoped>
.boundary-col {
  min-width: 180px;
}
</style>
