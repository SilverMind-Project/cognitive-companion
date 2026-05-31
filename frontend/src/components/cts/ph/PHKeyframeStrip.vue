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
      <button
        v-for="frame in keyframes"
        :key="frame.observation_id || frame.minio_key"
        class="keyframe-btn"
        :title="frame.camera_id ? `Camera ${frame.camera_id}` : 'View frame'"
        @click="$emit('select', frame)"
      >
        <v-img
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
        <div class="keyframe-overlay">
          <v-icon size="18" color="white">mdi-magnify-plus-outline</v-icon>
        </div>
      </button>
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
  emits: ["select"],
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

.keyframe-btn {
  position: relative;
  flex: 0 0 auto;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  border-radius: var(--cc-radius-sm);
  overflow: hidden;
}

.keyframe-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.keyframe-thumb {
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-sm);
  display: block;
}

.keyframe-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0);
  transition: background 0.15s ease;
  border-radius: var(--cc-radius-sm);
}

.keyframe-btn:hover .keyframe-overlay {
  background: rgba(0, 0, 0, 0.45);
}
</style>
