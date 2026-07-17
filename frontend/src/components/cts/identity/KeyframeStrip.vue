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
        :src="displaySrc(urlMap[kfKey(kf)] || '')"
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
import { ref, watch, onUnmounted } from "vue";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";
import { cts } from "@/services/cts.js";
import { useNotify } from "@/composables/useNotify";

const props = defineProps({ frames: { type: Array, default: () => [] } });
defineEmits(["click"]);

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);
const notify = useNotify();

const urlMap = ref({});

function kfKey(kf) {
  return kf.sample_id || kf.keyframe_id || "";
}

function hasImageUrl(kf) {
  return !!(kf.image_url || kf.minio_key);
}

async function loadFrameUrl(kf) {
  const key = kfKey(kf);
  if (!key) return;
  // If frame already has a direct image_url, use it.
  if (kf.image_url) {
    urlMap.value[key] = kf.image_url;
    return;
  }
  const minioKey = kf.minio_key;
  if (!minioKey) {
    urlMap.value[key] = "";
    return;
  }
  try {
    const url = await cts.getKeyframeBlob(minioKey);
    urlMap.value[key] = url;
  } catch (e) {
    notify.error(e.message || "Failed to load keyframe");
  }
}

// Load URLs when frames change.
watch(
  () => props.frames,
  (newFrames) => {
    const newMap = {};
    for (const kf of newFrames || []) {
      const key = kfKey(kf);
      if (!key) continue;
      // Reuse existing URLs for frames we've already loaded.
      if (urlMap.value[key]) {
        newMap[key] = urlMap.value[key];
      } else if (hasImageUrl(kf)) {
        loadFrameUrl(kf);
      }
    }
    // Revoke URLs for frames that are no longer present.
    for (const [k, url] of Object.entries(urlMap.value)) {
      if (!newMap[k] && url && url.startsWith("blob:")) {
        URL.revokeObjectURL(url);
      }
    }
    urlMap.value = newMap;
  },
  { immediate: true },
);

onUnmounted(() => {
  for (const url of Object.values(urlMap.value)) {
    if (typeof url === "string" && url.startsWith("blob:")) {
      URL.revokeObjectURL(url);
    }
  }
});
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
