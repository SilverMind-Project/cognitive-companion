<!-- Backend: backend/steps/builtin/image_crop.py -->
<template>
  <!-- Source tab -->
  <div v-if="tab === 'source'">
    <ImageSourceSelector
      :model-value="modelValue"
      :camera-sensor-items="cameraSensorItems"
      :available-rooms="availableRooms"
      show-max-images
      show-trigger-card
      show-time-filter
      max-images-hint="Hard cap on total images processed"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>

  <!-- Regions tab -->
  <div v-else-if="tab === 'regions'">
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

    <ImageCropCanvas
      ref="canvasRef"
      :image-url="sampleImageUrl"
      :regions="modelValue.regions || []"
      :selected-index="selectedRegionIndex"
      @update:regions="emit('update:modelValue', { ...modelValue, regions: $event })"
      @select-region="selectedRegionIndex = $event"
    />

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
        Add Region
      </v-btn>
    </div>

    <v-card
      v-for="(region, i) in (modelValue.regions || [])"
      :key="i"
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
          @click.stop="deleteRegion(i)"
        />
      </div>

      <v-row dense>
        <v-col cols="6">
          <v-text-field
            :model-value="region.id"
            label="ID"
            density="compact"
            hide-details
            hint="Lowercase letters, digits, underscores"
            persistent-hint
            @update:model-value="updateRegionField(i, 'id', $event)"
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            :model-value="region.name"
            label="Name"
            density="compact"
            hide-details
            @update:model-value="updateRegionField(i, 'name', $event)"
          />
        </v-col>
      </v-row>

      <v-row dense class="mt-1">
        <v-col cols="3">
          <v-text-field
            :model-value="toPercent(region.x)"
            label="X %"
            type="number"
            :min="0"
            :max="100"
            density="compact"
            hide-details
            @update:model-value="updateRegionField(i, 'x', toRatio($event))"
          />
        </v-col>
        <v-col cols="3">
          <v-text-field
            :model-value="toPercent(region.y)"
            label="Y %"
            type="number"
            :min="0"
            :max="100"
            density="compact"
            hide-details
            @update:model-value="updateRegionField(i, 'y', toRatio($event))"
          />
        </v-col>
        <v-col cols="3">
          <v-text-field
            :model-value="toPercent(region.width)"
            label="Width %"
            type="number"
            :min="0"
            :max="100"
            density="compact"
            hide-details
            @update:model-value="updateRegionField(i, 'width', toRatio($event))"
          />
        </v-col>
        <v-col cols="3">
          <v-text-field
            :model-value="toPercent(region.height)"
            label="Height %"
            type="number"
            :min="0"
            :max="100"
            density="compact"
            hide-details
            @update:model-value="updateRegionField(i, 'height', toRatio($event))"
          />
        </v-col>
      </v-row>
    </v-card>

    <div
      v-if="!(modelValue.regions || []).length"
      class="text-center text-medium-emphasis py-6"
    >
      <div class="text-body-1">No regions configured</div>
      <div class="text-caption">Click "Add Region" or draw on the canvas above</div>
    </div>
  </div>

  <!-- Output tab -->
  <div v-else-if="tab === 'output'">
    <div class="mb-4">
      <div class="text-body-2 mb-1">JPEG Quality: {{ modelValue.jpeg_quality ?? 90 }}</div>
      <v-slider
        :model-value="modelValue.jpeg_quality ?? 90"
        :min="1"
        :max="100"
        :step="1"
        hide-details
        thumb-label
        @update:model-value="emit('update:modelValue', { ...modelValue, jpeg_quality: $event })"
      />
    </div>

    <v-text-field
      :model-value="modelValue.retention_minutes"
      label="Retention (minutes)"
      type="number"
      :min="5"
      :max="1440"
      hint="How long to keep cropped images before cleanup"
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, retention_minutes: Number($event) || 60 })"
    />

    <v-select
      :model-value="modelValue.output_format"
      :items="[{ title: 'JPEG', value: 'jpeg' }]"
      item-title="title"
      item-value="value"
      label="Output Format"
      hide-details
      @update:model-value="emit('update:modelValue', { ...modelValue, output_format: $event })"
    />
  </div>
</template>

<script>
import ImageSourceSelector from "./_shared/ImageSourceSelector.vue";
import ImageCropCanvas from "./_shared/ImageCropCanvas.vue";

export const stepDefaults = {
  image_source: "trigger",
  pipeline_image_path: "",
  cts_frames_path: "steps.cts_window_poll_1.outputs.frames",
  max_images: 1,
  trigger_images_count: 0,
  additional_sensor_ids: [],
  additional_room_names: [],
  images_per_sensor: 1,
  sensor_frame_limits: {},
  image_time_filter: {},
  regions: [],
  output_format: "jpeg",
  jpeg_quality: 90,
  retention_minutes: 60,
};

export const stepTabs = [
  { key: "source", label: "Source", icon: "mdi-camera-outline" },
  { key: "regions", label: "Regions", icon: "mdi-crop" },
  { key: "output", label: "Output", icon: "mdi-tune" },
];
</script>

<script setup>
import { ref, computed } from "vue";
import { api } from "../../../services/api.js";
import { cts } from "../../../services/cts.js";

const props = defineProps({
  modelValue: { type: Object, required: true },
  tab: { type: String, default: "source" },
  cameraSensorItems: { type: Array, default: () => [] },
  ctsCameraItems: { type: Array, default: () => [] },
  availableRooms: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:modelValue"]);

// Sample loading
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
    const sourceType = sampleSource.value;
    const params = { source_type: sourceType };
    if (sourceType === "recamera") {
      params.sensor_id = sampleCameraId.value;
    } else {
      params.camera_id = sampleCameraId.value;
    }

    try {
      const data = await api.getSampleImage(params);
      sampleImageUrl.value = data.image_url;
    } catch {
      // Fallback: use existing APIs.
      if (sourceType === "recamera") {
        const buf = await api.getMediaBuffer({ sensor_id: sampleCameraId.value, limit: 1 });
        if (buf?.images?.length) {
          sampleImageUrl.value = buf.images[0].url;
        }
      } else {
        sampleImageUrl.value = await cts.getSnapshot(sampleCameraId.value);
      }
    }
  } finally {
    sampleLoading.value = false;
  }
}

// Region helpers
function toPercent(ratio) {
  if (ratio == null) return 0;
  return Math.round(ratio * 100);
}

function toRatio(percent) {
  const n = Number(percent);
  if (isNaN(n)) return 0;
  return Math.max(0, Math.min(1, n / 100));
}

function updateRegionField(index, field, value) {
  const regions = [...(props.modelValue.regions || [])];
  regions[index] = { ...regions[index], [field]: value };
  emit("update:modelValue", { ...props.modelValue, regions });
}

function addRegion() {
  const regions = [...(props.modelValue.regions || [])];
  const idx = regions.length + 1;
  regions.push({
    id: `region_${idx}`,
    name: `Region ${idx}`,
    x: 0.1,
    y: 0.1,
    width: 0.3,
    height: 0.3,
  });
  selectedRegionIndex.value = regions.length - 1;
  emit("update:modelValue", { ...props.modelValue, regions });
}

function deleteRegion(index) {
  const regions = [...(props.modelValue.regions || [])];
  regions.splice(index, 1);
  if (selectedRegionIndex.value >= regions.length) {
    selectedRegionIndex.value = regions.length - 1;
  }
  emit("update:modelValue", { ...props.modelValue, regions });
}
</script>
