<template>
  <div class="pa-3">
    <div class="text-caption font-weight-medium mb-2">Identity Evidence</div>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-2" />
    <v-alert v-else-if="error" type="error" density="compact" variant="tonal" class="mb-2">
      {{ error }}
    </v-alert>

    <div v-else-if="!ph || (!topLabel && !hasObservations)" class="text-caption text-medium-emphasis">
      No identity evidence recorded.
    </div>

    <template v-else-if="ph">
      <div v-if="topLabel" class="mb-3">
        <div class="d-flex align-center ga-2 mb-2">
          <div
            class="posterior-dot"
            :style="{ background: identityColor(ph.current_identity_id || topLabel) }"
          />
          <span class="text-body-2 font-weight-medium">
            {{ ph.identity_display_name || topLabel }}
          </span>
          <v-spacer />
          <span v-if="confidencePercent !== null" class="text-caption text-medium-emphasis">
            {{ confidencePercent.toFixed(0) }}%
          </span>
        </div>
        <v-progress-linear
          v-if="confidencePercent !== null"
          :model-value="confidencePercent"
          color="primary"
          height="8"
          rounded
        />
        <div v-if="confidencePercent !== null" class="posterior-gauge mt-3">
          <CcGaugeChart
            :value="confidencePercent"
            label="Confidence"
            unit="%"
          />
        </div>
      </div>

      <div class="text-caption text-medium-emphasis">
        {{ observations.length }} observation{{ observations.length !== 1 ? 's' : '' }} recorded.
      </div>
    </template>
  </div>
</template>

<script>
import { computed } from "vue";
import { identityColor } from "@/composables/useIdentityColor";
import CcGaugeChart from "@/components/charts/CcGaugeChart.vue";

export default {
  name: "PHPosteriorPanel",
  components: { CcGaugeChart },
  props: {
    ph: { type: Object, default: null },
    observations: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    error: { type: String, default: "" },
  },
  setup(props) {
    const hasObservations = computed(() => props.observations.length > 0);
    const topLabel = computed(() =>
      props.ph?.posterior_top_label || props.ph?.current_identity_id || null
    );
    const confidencePercent = computed(() => {
      const prob = props.ph?.posterior_top_prob;
      if (prob === null || prob === undefined) return null;
      return Math.max(0, Math.min(100, Number(prob) * 100));
    });

    return { identityColor, hasObservations, topLabel, confidencePercent };
  },
};
</script>

<style scoped>
.posterior-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.posterior-gauge {
  height: 150px;
}
</style>
