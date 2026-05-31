<template>
  <div class="pa-3">
    <div class="text-caption font-weight-medium mb-2">Keyframes</div>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-2" />
    <v-alert v-else-if="error" type="error" density="compact" variant="tonal" class="mb-2">
      {{ error }}
    </v-alert>
    <div v-else-if="!keyframes.length" class="text-caption text-medium-emphasis">
      No keyframes available.
    </div>
    <div v-else class="keyframe-strip">
      <v-img
        v-for="frame in keyframes"
        :key="frame.observation_id || frame.minio_key"
        :src="displaySrc(frameSrc(frame))"
        width="104"
        height="78"
        cover
        class="keyframe-thumb"
      >
        <template #placeholder>
          <div class="d-flex align-center justify-center fill-height">
            <v-progress-circular indeterminate size="20" color="primary" />
          </div>
        </template>
      </v-img>
    </div>
  </div>
</template>

<script>
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";

export default {
  name: "PHKeyframeStrip",
  props: {
    keyframes: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    error: { type: String, default: "" },
  },
  setup() {
    const { blurMode } = useBlurMode();
    const { displaySrc } = useDisplaySrc(blurMode);

    function frameSrc(frame) {
      if (blurMode.value && frame.blurred_image_url) return frame.blurred_image_url;
      return frame.image_url || frame.latest_keyframe_image_url || "";
    }

    return { displaySrc, frameSrc };
  },
};
</script>

<style scoped>
.keyframe-strip {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.keyframe-thumb {
  flex: 0 0 auto;
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-sm);
}
</style>
