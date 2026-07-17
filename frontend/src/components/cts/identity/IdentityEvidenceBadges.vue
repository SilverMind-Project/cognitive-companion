<template>
  <div class="d-flex flex-wrap align-center ga-1">
    <!-- Source / authority badge (icon + text, never colour alone) -->
    <v-chip
      size="x-small"
      variant="tonal"
      :color="toneColor(badge.tone)"
      :prepend-icon="badge.icon"
    >
      {{ badge.label }}
    </v-chip>

    <!-- Calibrated confidence or 'Verified' -->
    <v-chip size="x-small" variant="text" class="font-weight-medium">
      {{ confidence }}
    </v-chip>

    <!-- Pending ReID review -->
    <v-chip
      v-if="bbox.pending_review"
      size="x-small"
      variant="tonal"
      color="info"
      prepend-icon="mdi-clock-outline"
    >
      Pending review
    </v-chip>

    <!-- Detail-only evidence panel -->
    <template v-if="detailed">
      <v-divider class="my-2 w-100" />
      <table class="evidence-table text-caption w-100">
        <tbody>
          <tr>
            <th>Effective</th>
            <td>{{ effectiveLabel }}</td>
          </tr>
          <tr v-if="inferredDiffers">
            <th>Inferred</th>
            <td>{{ inferredLabel }}</td>
          </tr>
          <tr v-if="bbox.conflict">
            <th>Conflict</th>
            <td class="text-error">{{ bbox.conflict_kind || "present" }}</td>
          </tr>
          <tr v-if="bbox.ph_id">
            <th>PH</th>
            <td>
              <span class="cc-code">{{ shortId(bbox.ph_id) }}</span>
            </td>
          </tr>
          <tr v-if="bbox.revision_id">
            <th>Revision</th>
            <td>
              <span class="cc-code">{{ shortId(bbox.revision_id) }}</span>
            </td>
          </tr>
          <tr v-if="rawSimilarity !== null">
            <!-- Raw ArcFace similarity is NEVER presented as confidence. -->
            <th>Raw similarity</th>
            <td>{{ rawSimilarity.toFixed(3) }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { sourceBadge, confidenceLabel, identityLabel } from "./identityEvidence.js";

const props = defineProps({
  bbox: { type: Object, required: true },
  targets: { type: Array, default: () => [] },
  detailed: { type: Boolean, default: false },
});

const badge = computed(() => sourceBadge(props.bbox));
const confidence = computed(() => confidenceLabel(props.bbox));

const effectiveLabel = computed(() =>
  identityLabel(props.bbox.effective_identity_id, props.targets),
);
const inferredLabel = computed(() => identityLabel(props.bbox.inferred_identity_id, props.targets));
const inferredDiffers = computed(
  () => props.bbox.inferred_identity_id !== props.bbox.effective_identity_id,
);

const rawSimilarity = computed(() => {
  const v = props.bbox.raw_similarity;
  return typeof v === "number" && Number.isFinite(v) ? v : null;
});

// Map the formatter's semantic tone to a DS Vuetify colour. A "neutral" tone
// drops the colour so the tonal chip falls back to the warm surface.
function toneColor(tone) {
  return tone === "neutral" ? undefined : tone;
}

function shortId(id) {
  return id ? String(id).slice(0, 8) : "";
}
</script>

<style scoped>
.evidence-table th {
  text-align: left;
  font-weight: 600;
  color: var(--cc-text-3);
  padding-right: 12px;
  white-space: nowrap;
  vertical-align: top;
}
.evidence-table td {
  color: var(--cc-text-1);
  width: 100%;
}
.w-100 {
  width: 100%;
}
</style>
