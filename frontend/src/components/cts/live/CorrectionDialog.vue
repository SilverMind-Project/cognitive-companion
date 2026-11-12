<template>
  <!-- Medium dialog hosting the shared correction workflow (its own actions, so no footer). -->
  <AppDialog
    v-model="open"
    size="md"
    persistent
    icon="mdi-account-convert"
    label="Correct Identity"
    :title="cameraId ? `Track on ${cameraId}` : 'Track'"
    hide-footer
  >
    <div class="px-6 py-5">
      <div class="text-body-2 text-medium-emphasis mb-4">
        Currently shown as
        <strong>{{ currentIdentityId || "Unknown" }}</strong>
        <span class="mx-1">·</span>
        <span class="cc-code">{{ shortPhId }}</span>
      </div>
      <IdentityCorrectionWorkflow
        v-if="open && phId"
        :key="`${phId}-${frameCapturedAt}`"
        :ph-id="phId"
        :frame-captured-at="frameCapturedAt"
        source-view="live_view"
        default-scope="segment"
        @applied="onApplied"
        @close="open = false"
      />
    </div>
  </AppDialog>
</template>

<script setup>
/**
 * Live-view identity correction. Clicking a tracked person opens the same governed workflow the
 * Keyframes page and the PH inspector use: the household selector, an explicit Set to Unknown,
 * structured reasons, the proposed track segment around the clicked frame, and the async job
 * status. The view supplies the track and the frame time; it never collects a typed identity id.
 */
import { computed } from "vue";
import AppDialog from "@/components/common/AppDialog.vue";
import IdentityCorrectionWorkflow from "@/components/cts/identity/IdentityCorrectionWorkflow.vue";

const props = defineProps({
  phId: { type: String, default: "" },
  cameraId: { type: String, default: "" },
  currentIdentityId: { type: String, default: "" },
  /** ISO time of the live frame that was clicked; anchors the proposed segment. */
  frameCapturedAt: { type: String, default: "" },
});

const emit = defineEmits(["applied"]);

const open = defineModel({ type: Boolean, required: true });

const shortPhId = computed(() => (props.phId.length > 10 ? props.phId.slice(0, 8) : props.phId));

function onApplied(result) {
  open.value = false;
  emit("applied", result);
}
</script>
