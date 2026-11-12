<template>
  <!-- Reserve the frame's shape so the layout does not jump when the image arrives. -->
  <div
    ref="wrapEl"
    class="overlay-wrap"
    :style="frameW && frameH ? { aspectRatio: `${frameW} / ${frameH}` } : null"
  >
    <img
      v-if="!imageFailed"
      :src="displaySrc(imageUrl)"
      class="overlay-img"
      alt="Keyframe"
      @load="measure"
      @error="imageFailed = true"
    />
    <div v-else class="overlay-missing">
      <v-icon size="32" color="medium-emphasis">mdi-image-broken-variant</v-icon>
      <span class="text-caption text-medium-emphasis">Frame image unavailable</span>
    </div>
    <svg
      v-if="frameW && frameH"
      class="overlay-svg"
      :viewBox="`0 0 ${frameW} ${frameH}`"
      preserveAspectRatio="xMidYMid meet"
    >
      <g
        v-for="item in drawOrder"
        :key="item.key"
        :class="['bbox-group', { selectable, selected: item.selected }]"
        :tabindex="selectable ? 0 : -1"
        :role="selectable ? 'button' : null"
        :aria-label="ariaLabel(item.bbox)"
        :aria-pressed="selectable ? item.selected : null"
        @click="onSelect(item.bbox)"
        @keydown.enter.prevent="onSelect(item.bbox)"
        @keydown.space.prevent="onSelect(item.bbox)"
      >
        <!-- The whole box is the hit target: a transparent fill still receives pointer events. -->
        <rect
          class="bbox-rect"
          :x="item.rect.x"
          :y="item.rect.y"
          :width="item.rect.w"
          :height="item.rect.h"
          :style="{ stroke: item.color, fill: item.color }"
          :stroke-dasharray="item.dashed ? dashArray : null"
          :pointer-events="selectable ? 'all' : 'none'"
          vector-effect="non-scaling-stroke"
        />
        <!-- Label chip: text + symbol so colour is never the only signal -->
        <g :transform="`translate(${item.label.x}, ${item.label.y})`">
          <rect
            :width="item.label.w"
            :height="label.h"
            :rx="label.radius"
            :style="{ fill: item.color }"
          />
          <text
            :x="label.padX"
            :y="label.h / 2"
            dominant-baseline="central"
            fill="white"
            class="overlay-label"
            :font-size="label.fontSize"
            v-bind="HALO.attrs(label.halo)"
          >
            {{ item.text }}
          </text>
        </g>
      </g>
    </svg>
  </div>
</template>

<script setup>
/**
 * Identity bounding boxes drawn over a keyframe.
 *
 * Box coordinates live in the source frame's pixel space (the SVG viewBox), but labels and outlines
 * are sized in screen pixels: the overlay measures its rendered width and converts, so a label
 * stays readable whether a 1920px frame is shown at 600px or full width.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { identityColor } from "@/composables/useIdentityColor.js";
import { HALO } from "@/composables/useAnnotationStyle.js";
import { identityLabel } from "./identityEvidence.js";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode.js";

const props = defineProps({
  imageUrl: { type: String, default: "" },
  bboxes: { type: Array, default: () => [] },
  targets: { type: Array, default: () => [] },
  selectable: { type: Boolean, default: true },
  /** `bbox_id` (or `ph_id`) of the box to highlight as selected. */
  selectedId: { type: String, default: null },
  frameWidth: { type: Number, default: 0 },
  frameHeight: { type: Number, default: 0 },
});

const emit = defineEmits(["select"]);

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

// Screen-pixel targets for the label chip and outline dashes.
const LABEL_FONT_PX = 14;
const LABEL_HEIGHT_PX = 24;
const LABEL_PAD_PX = 8;
// Average glyph advance of the UI font at weight 500, as a fraction of the font size.
const GLYPH_WIDTH_EM = 0.6;
// Assumed render width before the first measurement (the inspector's image column).
const FALLBACK_RENDER_PX = 640;

const wrapEl = ref(null);
const renderedWidth = ref(0);
// The boxes stay useful without the picture (they can still be selected and corrected).
const imageFailed = ref(false);

watch(
  () => props.imageUrl,
  () => {
    imageFailed.value = false;
  },
);
let resizeObserver = null;

const frameW = computed(() => props.frameWidth || props.bboxes[0]?.frame_width || 0);
const frameH = computed(() => props.frameHeight || props.bboxes[0]?.frame_height || 0);

/** viewBox units per CSS pixel at the current render size. */
const unitsPerPx = computed(() => frameW.value / (renderedWidth.value || FALLBACK_RENDER_PX));

const label = computed(() => {
  const u = unitsPerPx.value;
  const fontSize = LABEL_FONT_PX * u;
  return {
    fontSize,
    h: LABEL_HEIGHT_PX * u,
    padX: LABEL_PAD_PX * u,
    radius: 4 * u,
    halo: Math.max(2 * u, fontSize * 0.15),
  };
});

// Non-scaling strokes take the dash pattern in screen pixels.
const dashArray = "8 5";

function measure() {
  renderedWidth.value = wrapEl.value?.clientWidth || 0;
}

onMounted(() => {
  measure();
  if (typeof ResizeObserver !== "undefined" && wrapEl.value) {
    resizeObserver = new ResizeObserver(measure);
    resizeObserver.observe(wrapEl.value);
  }
});

onBeforeUnmount(() => resizeObserver?.disconnect());

// Use any operator-overridden geometry when present.
function rx(b) {
  const x1 = b.override_x1 ?? b.x1;
  const y1 = b.override_y1 ?? b.y1;
  const x2 = b.override_x2 ?? b.x2;
  const y2 = b.override_y2 ?? b.y2;
  return { x: x1, y: y1, w: Math.max(1, x2 - x1), h: Math.max(1, y2 - y1) };
}

function colorFor(b) {
  if (b.conflict) return "var(--cc-error)"; // conflict always distinct
  if (!b.effective_identity_id) return "var(--cc-warning)"; // unknown
  return identityColor(b.effective_identity_id);
}

function labelText(b) {
  if (b.conflict) return "Conflict";
  const name = identityLabel(b.effective_identity_id, props.targets);
  if (b.authority === "operator") return `${name} ✓`;
  return name;
}

function boxKey(b, idx) {
  return b.bbox_id || `${b.ph_id}-${idx}`;
}

function isSelected(b) {
  if (!props.selectedId) return false;
  return (b.bbox_id || b.ph_id) === props.selectedId;
}

/** Label chip position: above the box when it fits, otherwise tucked inside its top edge. */
function labelBox(rect, text) {
  const { h, padX, fontSize } = label.value;
  const w = Math.min(frameW.value, text.length * fontSize * GLYPH_WIDTH_EM + padX * 2);
  const x = Math.min(Math.max(0, rect.x), Math.max(0, frameW.value - w));
  const y = rect.y >= h ? rect.y - h : rect.y;
  return { x, y, w };
}

// Larger boxes first so a smaller box nested inside another stays on top and clickable.
const drawOrder = computed(() =>
  props.bboxes
    .map((b, idx) => {
      const rect = rx(b);
      const text = labelText(b);
      return {
        key: boxKey(b, idx),
        bbox: b,
        rect,
        text,
        color: colorFor(b),
        dashed: !!b.conflict || !b.effective_identity_id,
        selected: isSelected(b),
        label: labelBox(rect, text),
      };
    })
    .sort((a, b) => b.rect.w * b.rect.h - a.rect.w * a.rect.h),
);

function ariaLabel(b) {
  return `${labelText(b)} bounding box. Activate to correct identity.`;
}

function onSelect(b) {
  if (props.selectable) emit("select", b);
}
</script>

<style scoped>
.overlay-wrap {
  position: relative;
  display: inline-block;
  width: 100%;
  line-height: 0;
}
.overlay-img {
  width: 100%;
  height: auto;
  display: block;
}
.overlay-missing {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  line-height: normal;
  background: var(--cc-surface-2);
}
.overlay-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.bbox-rect {
  stroke-width: 2.5px;
  fill-opacity: 0;
  transition: fill-opacity 0.12s ease;
}
.bbox-group.selectable {
  cursor: pointer;
}
.bbox-group.selectable:hover .bbox-rect {
  fill-opacity: 0.12;
}
.bbox-group.selected .bbox-rect {
  stroke-width: 4px;
  fill-opacity: 0.18;
}
.bbox-group.selectable:focus-visible {
  outline: none;
}
.bbox-group.selectable:focus-visible .bbox-rect {
  stroke-width: 4px;
  fill-opacity: 0.18;
}
/* White text over a dark halo: the camera-feed standard in useAnnotationStyle.js. */
.overlay-label {
  font-weight: 500;
  font-family: var(--cc-font, sans-serif);
}
@media (prefers-reduced-motion: reduce) {
  .bbox-rect {
    transition: none;
  }
}
</style>
