<!-- Backend: backend/steps/builtin/region_presence.py -->
<template>
  <!-- Regions tab -->
  <div v-if="tab === 'regions'">
    <v-row class="mb-3">
      <v-col cols="6">
        <v-select
          v-model="sampleSource"
          :items="sampleSourceItems"
          item-title="title"
          item-value="value"
          label="Sample Source"
          density="compact"
          hide-details
        />
      </v-col>
      <v-col cols="6">
        <v-combobox
          v-model="sampleCameraId"
          :items="sampleCameraItems"
          label="Camera / Sensor"
          density="compact"
          hide-details
          :loading="sampleLoading"
        />
      </v-col>
    </v-row>

    <v-btn
      variant="tonal"
      color="primary"
      prepend-icon="mdi-image-refresh"
      block
      class="mb-4"
      :loading="sampleLoading"
      @click="loadSample"
    >
      Load Sample Image
    </v-btn>

    <div class="text-subtitle-2 mb-2">Rect regions</div>
    <ImageCropCanvas
      ref="canvasRef"
      :image-url="sampleImageUrl"
      :regions="rectRegions"
      :selected-index="selectedRegionIndex"
      @update:regions="onRectRegionsUpdate"
      @select-region="selectedRegionIndex = $event"
    />

    <div class="text-caption text-medium-emphasis mt-2">
      Drag on the image to draw a region. Drag a region to move it, or drag a corner handle to
      resize.
    </div>

    <div class="d-flex align-center mt-4 mb-2">
      <div class="text-subtitle-2">Regions</div>
      <v-spacer />
      <v-btn
        size="small"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-vector-rectangle"
        @click="addRegion"
      >
        Add Rect Region
      </v-btn>
    </div>

    <v-card
      v-for="(region, i) in rectRegions"
      :key="`rect-${i}`"
      :variant="i === selectedRegionIndex ? 'elevated' : 'outlined'"
      :color="i === selectedRegionIndex ? 'primary' : undefined"
      class="mb-3 pa-3"
      @click="selectedRegionIndex = i"
    >
      <div class="d-flex align-center mb-2">
        <div class="text-body-2 font-weight-bold">Region {{ i + 1 }}</div>
        <v-spacer />
        <v-btn
          icon="mdi-delete"
          size="x-small"
          variant="text"
          color="error"
          @click.stop="removeRectRegion(i)"
        />
      </div>

      <v-row dense>
        <v-col cols="6">
          <v-text-field
            :model-value="region.id"
            label="ID"
            density="compact"
            :rules="[(v) => isValidRegionId(v) || 'Lowercase letters, digits, underscores']"
            hint="Lowercase letters, digits, underscores"
            persistent-hint
            @update:model-value="updateRectRegionField(i, 'id', $event)"
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            :model-value="region.name"
            label="Name"
            density="compact"
            hide-details
            @update:model-value="updateRectRegionField(i, 'name', $event)"
          />
        </v-col>
      </v-row>
      <v-text-field
        :model-value="region.camera_id"
        label="Camera ID (optional)"
        density="compact"
        hide-details
        hint="Restrict this region to one camera, when detections carry camera attribution"
        class="mt-2"
        @update:model-value="updateRectRegionField(i, 'camera_id', $event || undefined)"
      />

      <div class="d-flex align-center mt-2 text-caption text-medium-emphasis">
        <v-icon size="14" class="mr-1">mdi-crop</v-icon>
        <span>{{ rectRegionSummary(region) }}</span>
      </div>
    </v-card>

    <div v-if="!rectRegions.length" class="text-center text-medium-emphasis py-4">
      <div class="text-body-2">No rect regions configured</div>
    </div>

    <v-divider class="my-4" />

    <div class="d-flex align-center mb-2">
      <div class="text-subtitle-2">Polygon regions</div>
      <v-spacer />
      <v-chip size="small" variant="tonal" color="secondary">TODO(DL-M10): canvas drawing</v-chip>
    </div>
    <div class="text-caption text-medium-emphasis mb-2">
      Polygon regions are edited as JSON: an array of
      <span class="cc-code">{ id, name, points, camera_id? }</span>, with
      <span class="cc-code">points</span> a list of at least 3 normalized [x, y] pairs. Drawing
      polygons on the canvas is not yet supported.
    </div>
    <v-textarea
      v-model="polygonJsonDraft"
      label="Polygon regions (JSON)"
      density="compact"
      rows="6"
      :error-messages="polygonJsonError"
      @blur="commitPolygonJson"
    />
  </div>

  <!-- Options tab -->
  <div v-else-if="tab === 'options'">
    <v-text-field
      :model-value="modelValue.detections_key"
      label="Detections Key"
      density="compact"
      hint="Dotted pipeline_data path to the detection list (default: scene_detections)"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, detections_key: $event })"
    />

    <v-select
      :model-value="modelValue.mode"
      :items="[
        { title: 'Anchor point', value: 'anchor' },
        { title: 'Overlap ratio', value: 'overlap' },
      ]"
      item-title="title"
      item-value="value"
      label="Mode"
      density="compact"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, mode: $event })"
    />

    <v-select
      :model-value="modelValue.anchor"
      :items="[
        { title: 'Bottom center (feet)', value: 'bottom_center' },
        { title: 'Center', value: 'center' },
      ]"
      item-title="title"
      item-value="value"
      label="Anchor"
      density="compact"
      class="mb-4"
      :disabled="modelValue.mode === 'overlap'"
      @update:model-value="emit('update:modelValue', { ...modelValue, anchor: $event })"
    />

    <div v-if="modelValue.mode === 'overlap'" class="mb-4">
      <div class="text-body-2 mb-1">Min overlap: {{ modelValue.min_overlap ?? 0.5 }}</div>
      <v-slider
        :model-value="modelValue.min_overlap ?? 0.5"
        :min="0"
        :max="1"
        :step="0.05"
        hide-details
        thumb-label
        @update:model-value="emit('update:modelValue', { ...modelValue, min_overlap: $event })"
      />
    </div>

    <v-combobox
      :model-value="modelValue.labels"
      :items="['person']"
      label="Labels"
      multiple
      chips
      closable-chips
      hint="Detection labels to consider (default: person)"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, labels: $event })"
    />

    <div class="mb-2">
      <div class="text-body-2 mb-1">Min confidence: {{ modelValue.min_confidence ?? 0.5 }}</div>
      <v-slider
        :model-value="modelValue.min_confidence ?? 0.5"
        :min="0"
        :max="1"
        :step="0.05"
        hide-details
        thumb-label
        @update:model-value="emit('update:modelValue', { ...modelValue, min_confidence: $event })"
      />
    </div>
  </div>
</template>

<script>
export const stepDefaults = {
  detections_key: "scene_detections",
  regions: [],
  mode: "anchor",
  anchor: "bottom_center",
  min_overlap: 0.5,
  labels: ["person"],
  min_confidence: 0.5,
};

export const stepTabs = [
  { key: "regions", label: "Regions", icon: "mdi-vector-polygon" },
  { key: "options", label: "Options", icon: "mdi-tune" },
];

export function chips(cfg, { chip }) {
  const out = [];
  const mode = cfg.mode || "anchor";
  out.push(chip(mode, "mdi-vector-polygon", "green"));
  const regionCount = cfg.regions?.length || 0;
  if (regionCount > 0)
    out.push(chip(`${regionCount} region${regionCount > 1 ? "s" : ""}`, "mdi-crop", "green"));
  const labels = cfg.labels?.length ? cfg.labels : ["person"];
  out.push(chip(labels.join(", "), "mdi-account-outline", "teal"));
  return out;
}
</script>

<script setup>
import { ref, computed, watch } from "vue";
import { api } from "../../../services/api.js";
import { useNotify } from "../../../composables/useNotify.js";
import ImageCropCanvas from "./_shared/ImageCropCanvas.vue";
import {
  addRectRegion,
  deleteRegion,
  isValidRegionId,
  rectRegionSummary,
  updateRegionField,
} from "./_shared/useRegionList.js";

const { notify } = useNotify();

const props = defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "regions" },
  cameraSensorItems: { type: Array, default: () => [] },
  ctsCameraItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue"]);

// Sample loading (mirrors ImageCropConfig.vue).
const sampleSource = ref("recamera");
const sampleCameraId = ref("");
const sampleLoading = ref(false);
const sampleImageUrl = ref("");
const selectedRegionIndex = ref(-1);
const canvasRef = ref(null);

const sampleSourceItems = [
  { title: "reCamera", value: "recamera" },
  { title: "CTS Camera", value: "cts" },
];

const sampleCameraItems = computed(() => {
  if (sampleSource.value === "recamera") {
    return props.cameraSensorItems || [];
  }
  return props.ctsCameraItems || [];
});

async function loadSample() {
  if (!sampleCameraId.value) return;
  sampleLoading.value = true;
  try {
    const params = { source_type: sampleSource.value };
    if (sampleSource.value === "recamera") {
      params.sensor_id = sampleCameraId.value;
    } else {
      params.camera_id = sampleCameraId.value;
    }

    const data = await api.getSampleImage(params);
    sampleImageUrl.value = data.image_url;
  } catch (e) {
    notify.error(`Could not load sample image: ${e.message || e}`);
  } finally {
    sampleLoading.value = false;
  }
}

// -- Rect / polygon split --------------------------------------------------
// ImageCropCanvas only understands rect regions (x/y/width/height); polygon
// regions (points) are edited as JSON below. Both shapes live in the same
// config.regions array, split here for editing and merged back on update.

const rectRegions = computed(() => (props.modelValue.regions || []).filter((r) => !r.points));
const polygonRegions = computed(() => (props.modelValue.regions || []).filter((r) => r.points));

function emitRegions(regions) {
  emit("update:modelValue", { ...props.modelValue, regions });
}

function onRectRegionsUpdate(nextRect) {
  emitRegions([...nextRect, ...polygonRegions.value]);
}

function addRegion() {
  const nextRect = addRectRegion(rectRegions.value);
  selectedRegionIndex.value = nextRect.length - 1;
  emitRegions([...nextRect, ...polygonRegions.value]);
}

function removeRectRegion(index) {
  const nextRect = deleteRegion(rectRegions.value, index);
  if (selectedRegionIndex.value >= nextRect.length) {
    selectedRegionIndex.value = nextRect.length - 1;
  }
  emitRegions([...nextRect, ...polygonRegions.value]);
}

function updateRectRegionField(index, field, value) {
  const nextRect = updateRegionField(rectRegions.value, index, field, value);
  emitRegions([...nextRect, ...polygonRegions.value]);
}

// -- Polygon JSON editor ---------------------------------------------------

const polygonJsonDraft = ref(JSON.stringify(polygonRegions.value, null, 2));
const polygonJsonError = ref("");

watch(polygonRegions, (next) => {
  polygonJsonDraft.value = JSON.stringify(next, null, 2);
});

function validatePolygonRegions(parsed) {
  if (!Array.isArray(parsed)) return "Must be a JSON array";
  for (const region of parsed) {
    if (!region || typeof region !== "object") return "Each entry must be an object";
    if (!isValidRegionId(region.id)) return `Invalid id: ${region.id}`;
    if (!region.name) return `Region ${region.id} is missing a name`;
    if (!Array.isArray(region.points) || region.points.length < 3) {
      return `Region ${region.id} needs at least 3 points`;
    }
    for (const point of region.points) {
      if (
        !Array.isArray(point) ||
        point.length !== 2 ||
        point.some((v) => typeof v !== "number" || v < 0 || v > 1)
      ) {
        return `Region ${region.id} has an invalid point (expected [x, y] in 0..1)`;
      }
    }
  }
  return "";
}

function commitPolygonJson() {
  let parsed;
  try {
    parsed = polygonJsonDraft.value.trim() ? JSON.parse(polygonJsonDraft.value) : [];
  } catch {
    polygonJsonError.value = "Invalid JSON";
    return;
  }
  const error = validatePolygonRegions(parsed);
  if (error) {
    polygonJsonError.value = error;
    return;
  }
  polygonJsonError.value = "";
  emitRegions([...rectRegions.value, ...parsed]);
}
</script>
