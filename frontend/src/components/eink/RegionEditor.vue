<template>
  <v-card variant="outlined" rounded="lg" class="pa-3">
    <!-- Header -->
    <div class="d-flex align-center mb-3">
      <v-icon size="16" class="mr-1 text-medium-emphasis">mdi-vector-rectangle</v-icon>
      <span class="text-subtitle-2 font-weight-medium">Region Properties</span>
      <v-spacer />
      <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="$emit('delete')" />
    </div>

    <!-- Name -->
    <v-text-field
      :model-value="region.name"
      label="Name"
      variant="outlined"
      density="compact"
      class="mb-2"
      @update:model-value="update('name', $event)"
    />

    <!-- Position & Size -->
    <v-row dense class="mb-2">
      <v-col cols="3">
        <v-text-field
          :model-value="region.x" label="X" type="number"
          variant="outlined" density="compact"
          @update:model-value="update('x', Number($event))"
        />
      </v-col>
      <v-col cols="3">
        <v-text-field
          :model-value="region.y" label="Y" type="number"
          variant="outlined" density="compact"
          @update:model-value="update('y', Number($event))"
        />
      </v-col>
      <v-col cols="3">
        <v-text-field
          :model-value="region.width" label="W" type="number"
          variant="outlined" density="compact"
          @update:model-value="update('width', Number($event))"
        />
      </v-col>
      <v-col cols="3">
        <v-text-field
          :model-value="region.height" label="H" type="number"
          variant="outlined" density="compact"
          @update:model-value="update('height', Number($event))"
        />
      </v-col>
    </v-row>

    <!-- Text Alignment -->
    <v-btn-toggle
      :model-value="region.align || 'center'"
      density="compact"
      variant="outlined"
      class="mb-3 w-100"
      mandatory
      @update:model-value="update('align', $event)"
    >
      <v-btn value="left" size="small" class="flex-grow-1">
        <v-icon size="16">mdi-format-align-left</v-icon>
      </v-btn>
      <v-btn value="center" size="small" class="flex-grow-1">
        <v-icon size="16">mdi-format-align-center</v-icon>
      </v-btn>
      <v-btn value="right" size="small" class="flex-grow-1">
        <v-icon size="16">mdi-format-align-right</v-icon>
      </v-btn>
    </v-btn-toggle>

    <!-- Font Size Range -->
    <div class="text-caption text-medium-emphasis mb-1">Font Size (auto-fit)</div>
    <v-row dense class="mb-2">
      <v-col cols="6">
        <v-slider
          :model-value="region.font_size_max"
          label="Max"
          :min="12" :max="96" :step="2"
          thumb-label density="compact"
          @update:model-value="update('font_size_max', $event)"
        />
      </v-col>
      <v-col cols="6">
        <v-slider
          :model-value="region.font_size_min"
          label="Min"
          :min="8" :max="48" :step="2"
          thumb-label density="compact"
          @update:model-value="update('font_size_min', $event)"
        />
      </v-col>
    </v-row>

    <!-- Multi-line -->
    <v-checkbox
      :model-value="region.multiline !== false"
      label="Multi-line (respect line breaks)"
      density="compact"
      hide-details
      class="mb-3"
      @update:model-value="update('multiline', $event)"
    />

    <v-divider class="mb-3" />

    <!-- Text Color -->
    <div class="color-field mb-3">
      <div class="text-caption text-medium-emphasis mb-1">Text Color</div>
      <div class="d-flex align-center gap-2">
        <div class="color-swatch" :style="{ background: textColorCss }" />
        <input
          type="color"
          :value="textColorHex"
          class="color-input"
          @input="onTextColorHex($event.target.value)"
        />
        <v-slider
          :model-value="textAlpha"
          :min="0" :max="255" :step="1"
          density="compact"
          hide-details
          thumb-label
          class="flex-grow-1"
          @update:model-value="onTextAlpha"
        />
        <span class="text-caption text-medium-emphasis opacity-label">
          {{ Math.round((textAlpha / 255) * 100) }}%
        </span>
      </div>
    </div>

    <!-- Background Color -->
    <div class="color-field">
      <div class="d-flex align-center mb-1">
        <span class="text-caption text-medium-emphasis">Background</span>
        <v-spacer />
        <v-switch
          :model-value="bgTransparent"
          label="None"
          density="compact"
          hide-details
          inset
          color="primary"
          @update:model-value="onBgTransparent"
        />
      </div>
      <div v-if="!bgTransparent" class="d-flex align-center gap-2">
        <div class="color-swatch" :style="{ background: bgColorCss }" />
        <input
          type="color"
          :value="bgColorHex"
          class="color-input"
          @input="onBgColorHex($event.target.value)"
        />
        <v-slider
          :model-value="bgAlpha"
          :min="1" :max="255" :step="1"
          density="compact"
          hide-details
          thumb-label
          class="flex-grow-1"
          @update:model-value="onBgAlpha"
        />
        <span class="text-caption text-medium-emphasis opacity-label">
          {{ Math.round((bgAlpha / 255) * 100) }}%
        </span>
      </div>
    </div>
  </v-card>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  region: { type: Object, required: true },
});
const emit = defineEmits(["update:region", "delete"]);

function update(key, value) {
  emit("update:region", { ...props.region, [key]: value });
}

// ── Color helpers ────────────────────────────────────────────────────────────

/** [r, g, b, …] → '#rrggbb' */
function toHex(arr) {
  if (!arr || arr.length < 3) return "#000000";
  return (
    "#" +
    arr
      .slice(0, 3)
      .map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0"))
      .join("")
  );
}

/** '#rrggbb' → [r, g, b] */
function fromHex(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

/** [r, g, b, a] → 'rgba(r,g,b,a/255)' */
function toCss(arr) {
  if (!arr || arr.length < 3) return "rgba(0,0,0,1)";
  const a = arr.length >= 4 ? arr[3] / 255 : 1;
  return `rgba(${arr[0]},${arr[1]},${arr[2]},${a.toFixed(3)})`;
}

// ── Computed colour state ────────────────────────────────────────────────────

const textColor = computed(() => props.region.text_color || [255, 255, 255, 255]);
const textColorHex = computed(() => toHex(textColor.value));
const textAlpha = computed(() => textColor.value[3] ?? 255);
const textColorCss = computed(() => toCss(textColor.value));

const bgColor = computed(() => props.region.bg_color || [0, 0, 0, 160]);
const bgColorHex = computed(() => toHex(bgColor.value));
const bgAlpha = computed(() => bgColor.value[3] ?? 160);
const bgColorCss = computed(() => toCss(bgColor.value));
const bgTransparent = computed(() => bgAlpha.value === 0);

// ── Event handlers ───────────────────────────────────────────────────────────

function onTextColorHex(hex) {
  update("text_color", [...fromHex(hex), textAlpha.value]);
}

function onTextAlpha(val) {
  update("text_color", [...textColor.value.slice(0, 3), Math.round(val)]);
}

function onBgColorHex(hex) {
  update("bg_color", [...fromHex(hex), bgAlpha.value]);
}

function onBgAlpha(val) {
  update("bg_color", [...bgColor.value.slice(0, 3), Math.round(val)]);
}

function onBgTransparent(transparent) {
  // When turning transparent off, restore a sensible default opacity
  const alpha = transparent ? 0 : bgAlpha.value > 0 ? bgAlpha.value : 160;
  update("bg_color", [...bgColor.value.slice(0, 3), alpha]);
}
</script>

<style scoped>
.color-field {
  font-size: 13px;
}

.color-swatch {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid rgba(128, 128, 128, 0.25);
  flex-shrink: 0;
  background-image:
    linear-gradient(45deg, #bbb 25%, transparent 25%),
    linear-gradient(-45deg, #bbb 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #bbb 75%),
    linear-gradient(-45deg, transparent 75%, #bbb 75%);
  background-size: 8px 8px;
  background-position: 0 0, 0 4px, 4px -4px, -4px 0;
  background-color: #fff;
  position: relative;
  overflow: hidden;
}

/* The actual color overlaid on the checkerboard */
.color-swatch::after {
  content: "";
  position: absolute;
  inset: 0;
  background: inherit;
  border-radius: inherit;
}

.color-input {
  width: 32px;
  height: 28px;
  padding: 2px;
  border: 1px solid rgba(128, 128, 128, 0.25);
  border-radius: 4px;
  cursor: pointer;
  flex-shrink: 0;
  background: none;
}

.color-input::-webkit-color-swatch-wrapper {
  padding: 0;
}
.color-input::-webkit-color-swatch {
  border: none;
  border-radius: 2px;
}

.opacity-label {
  min-width: 34px;
  text-align: right;
}
</style>
