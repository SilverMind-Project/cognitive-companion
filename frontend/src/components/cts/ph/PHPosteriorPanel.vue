<template>
  <div class="pa-3">
    <div class="text-caption font-weight-medium mb-2">Identity Evidence</div>

    <div v-if="!ph || (!ph.current_identity_id && !hasObservations)" class="text-caption text-medium-emphasis">
      No identity evidence recorded.
    </div>

    <template v-else>
      <!-- Identity bar -->
      <div v-if="ph.current_identity_id" class="mb-3">
        <div class="d-flex align-center ga-2 mb-2">
          <div
            class="posterior-dot"
            :style="{ background: identityColor(ph.current_identity_id) }"
          />
          <span class="text-body-2 font-weight-medium">
            {{ ph.identity_display_name || ph.current_identity_id }}
          </span>
        </div>
      </div>

      <!-- Observation count -->
      <div class="text-caption text-medium-emphasis">
        {{ observations.length }} observation{{ observations.length !== 1 ? 's' : '' }} recorded.
      </div>
    </template>
  </div>
</template>

<script>
import { computed } from "vue";
import { identityColor } from "@/composables/useIdentityColor";

export default {
  name: "PHPosteriorPanel",
  props: {
    ph: { type: Object, default: null },
    observations: { type: Array, default: () => [] },
  },
  setup(props) {
    const hasObservations = computed(() => props.observations.length > 0);
    return { identityColor, hasObservations };
  },
};
</script>

<style scoped>
.posterior-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
</style>
