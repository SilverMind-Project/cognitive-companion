<template>
  <v-dialog :model-value="modelValue" max-width="900" persistent @update:model-value="onCancel">
    <v-card v-if="keyframeId">
      <DialogHeader
        icon="mdi-vector-square"
        label="Keyframe"
        title="Annotation Editor"
        @close="onCancel"
      />
      <v-divider />
      <v-card-text>
        <div v-if="loading" class="d-flex justify-center pa-8">
          <v-progress-circular indeterminate />
        </div>
        <template v-else>
          <v-row dense align="center" class="px-4 pb-2">
            <v-col cols="12" sm="6">
              <v-slider
                v-model="minConfidence"
                :min="0"
                :max="1"
                :step="0.05"
                label="Min confidence"
                thumb-label
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="6" class="text-body-2 text-medium-emphasis">
              Showing {{ filteredBboxes.length }} of {{ bboxes.length }} detections
            </v-col>
          </v-row>
          <BboxCanvas
            :key="bboxKey"
            :image-url="imageUrl"
            :keyframe-id="keyframeId"
            :initial-bboxes="filteredBboxes"
            :identities="identities"
            @bbox-tagged="onBboxTagged"
            @bbox-overridden="onBboxOverridden"
            @bbox-created="onBboxCreated"
            @bbox-deleted="onBboxDeleted"
          />
        </template>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-4">
        <span class="text-caption text-medium-emphasis">{{ pendingSummary }}</span>
        <v-spacer />
        <v-btn variant="text" @click="onCancel">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="pendingCount === 0"
          :loading="saving"
          @click="onSave"
        >
          Save Changes
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import { cts } from "@/services/cts";
import BboxCanvas from "./BboxCanvas.vue";
import DialogHeader from "@/components/common/DialogHeader.vue";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  imageUrl: { type: String, required: true },
  keyframeId: { type: String, required: true },
  identities: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:model-value", "saved", "error"]);

const bboxes = ref([]);
const loading = ref(false);
const saving = ref(false);
const bboxKey = ref(0);
const minConfidence = ref(0.5);

const filteredBboxes = computed(() =>
  bboxes.value.filter((b) => b.detection_confidence >= minConfidence.value)
);

// Pending changes accumulated from BboxCanvas events
const pendingTags = ref([]);
const pendingOverrides = ref([]);
const pendingDeletes = ref([]);
const pendingCreates = ref([]);

const pendingCount = computed(
  () =>
    pendingTags.value.length +
    pendingOverrides.value.length +
    pendingDeletes.value.length +
    pendingCreates.value.length
);

const pendingSummary = computed(() => {
  if (pendingCount.value === 0) return "No changes";
  const parts = [];
  if (pendingTags.value.length) parts.push(`${pendingTags.value.length} tag(s)`);
  if (pendingOverrides.value.length) parts.push(`${pendingOverrides.value.length} resize(s)`);
  if (pendingDeletes.value.length) parts.push(`${pendingDeletes.value.length} remove(s)`);
  if (pendingCreates.value.length) parts.push(`${pendingCreates.value.length} new`);
  return parts.join(", ") + " pending";
});

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return;
    bboxKey.value++;
    await loadBboxes();
  }
);

async function loadBboxes() {
  loading.value = true;
  try {
    const data = await cts.getKeyframeBboxes(props.keyframeId);
    bboxes.value = data || [];
  } catch (err) {
    bboxes.value = [];
    emit("error", err.message || String(err));
  } finally {
    loading.value = false;
    pendingTags.value = [];
    pendingOverrides.value = [];
    pendingDeletes.value = [];
    pendingCreates.value = [];
  }
}

function onBboxTagged({ annotationId, identityId, reason }) {
  if (!annotationId) {
    pendingCreates.value.push({ identityId, reason: reason || "" });
    return;
  }
  const idx = pendingTags.value.findIndex((t) => t.annotationId === annotationId);
  if (idx >= 0) {
    pendingTags.value[idx] = { annotationId, identityId, reason: reason || "" };
  } else {
    pendingTags.value.push({ annotationId, identityId, reason: reason || "" });
  }
}

function onBboxOverridden({ annotationId, x1, y1, x2, y2 }) {
  if (!annotationId) return;
  const idx = pendingOverrides.value.findIndex((o) => o.annotationId === annotationId);
  if (idx >= 0) {
    pendingOverrides.value[idx] = { annotationId, x1, y1, x2, y2 };
  } else {
    pendingOverrides.value.push({ annotationId, x1, y1, x2, y2 });
  }
}

function onBboxCreated({ x1, y1, x2, y2 }) {
  pendingCreates.value.push({ x1, y1, x2, y2, identityId: null, reason: "" });
}

function onBboxDeleted({ annotationId }) {
  if (!annotationId) return;
  pendingTags.value = pendingTags.value.filter((t) => t.annotationId !== annotationId);
  pendingOverrides.value = pendingOverrides.value.filter((o) => o.annotationId !== annotationId);
  pendingDeletes.value.push({ annotationId });
}

async function onSave() {
  saving.value = true;
  try {
    for (const ov of pendingOverrides.value) {
      await cts.overrideBbox(ov.annotationId, {
        x1: ov.x1,
        y1: ov.y1,
        x2: ov.x2,
        y2: ov.y2,
      });
    }
    for (const tag of pendingTags.value) {
      await cts.applyBboxCorrection(tag.annotationId, tag.identityId, tag.reason);
    }
    for (const del of pendingDeletes.value) {
      if (del.annotationId) {
        try {
          await cts.deleteBbox(del.annotationId);
        } catch (err) {
          const msg = String(err.message || err || "");
          if (err && (err.status === 404 || msg.includes("404"))) continue;
          throw err;
        }
      }
    }
    pendingTags.value = [];
    pendingOverrides.value = [];
    pendingDeletes.value = [];
    pendingCreates.value = [];
    emit("saved");
    await loadBboxes();
  } catch (err) {
    emit("error", err.message || String(err));
  } finally {
    saving.value = false;
  }
}

function onCancel() {
  emit("update:model-value", false);
}
</script>
