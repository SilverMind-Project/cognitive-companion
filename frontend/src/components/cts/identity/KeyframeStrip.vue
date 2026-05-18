<template>
  <div class="mb-4">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon size="16" color="medium-emphasis">mdi-image-multiple</v-icon>
      <span class="text-caption font-weight-medium text-uppercase">Keyframes</span>
    </div>
    <div v-if="frames.length" class="d-flex ga-2">
      <v-img
        v-for="kf in frames"
        :key="kf.sample_id || kf.keyframe_id"
        :src="displaySrc(frameUrl(kf.minio_key))"
        width="100"
        height="75"
        cover
        rounded="lg"
        class="keyframe-thumb"
        @click="$emit('click', kf)"
      />
    </div>
    <span v-else class="text-caption text-medium-emphasis">No keyframes available</span>
  </div>
</template>

<script setup>
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";

defineProps({ frames: { type: Array, default: () => [] } });
defineEmits(["click"]);

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

function frameUrl(minioKey) {
  if (!minioKey) return "";
  const encodedKey = minioKey.split("/").map(encodeURIComponent).join("/");
  const apiKey = encodeURIComponent(localStorage.getItem("cc_api_key") || "");
  return `/api/v1/cts/frames/${encodedKey}?api_key=${apiKey}`;
}
</script>

<style scoped>
.keyframe-thumb {
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.15s;
}
.keyframe-thumb:hover {
  border-color: rgb(var(--v-theme-primary));
}
</style>
