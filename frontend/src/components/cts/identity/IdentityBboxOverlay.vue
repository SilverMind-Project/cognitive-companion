<template>
  <div class="overlay-wrap">
    <img :src="displaySrc(imageUrl)" class="overlay-img" alt="Keyframe" />
    <svg
      v-if="frameW && frameH"
      class="overlay-svg"
      :viewBox="`0 0 ${frameW} ${frameH}`"
      preserveAspectRatio="xMidYMid meet"
    >
      <g
        v-for="(b, idx) in bboxes"
        :key="b.bbox_id || `${b.ph_id}-${idx}`"
        :class="['bbox-group', { selectable }]"
        :tabindex="selectable ? 0 : -1"
        :role="selectable ? 'button' : null"
        :aria-label="ariaLabel(b)"
        @click="onSelect(b)"
        @keydown.enter.prevent="onSelect(b)"
        @keydown.space.prevent="onSelect(b)"
      >
        <rect
          :x="rx(b).x"
          :y="rx(b).y"
          :width="rx(b).w"
          :height="rx(b).h"
          :stroke="strokeFor(b)"
          :stroke-dasharray="b.conflict || !b.effective_identity_id ? '12 8' : null"
          stroke-width="3"
          fill="none"
        />
        <!-- Label chip: text + symbol so colour is never the only signal -->
        <g :transform="`translate(${rx(b).x}, ${Math.max(0, rx(b).y - labelH)})`">
          <rect :width="labelWidth(b)" :height="labelH" :fill="strokeFor(b)" rx="3" />
          <text :x="6" :y="labelH * 0.72" class="overlay-label">
            {{ labelText(b) }}
          </text>
        </g>
      </g>
    </svg>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { identityColor } from "@/composables/useIdentityColor.js";
import { identityLabel } from "./identityEvidence.js";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode.js";

const props = defineProps({
  imageUrl: { type: String, default: "" },
  bboxes: { type: Array, default: () => [] },
  targets: { type: Array, default: () => [] },
  selectable: { type: Boolean, default: true },
  frameWidth: { type: Number, default: 0 },
  frameHeight: { type: Number, default: 0 },
});

const emit = defineEmits(["select"]);

const { blurMode } = useBlurMode();
const { displaySrc } = useDisplaySrc(blurMode);

const labelH = 26;

const frameW = computed(() => props.frameWidth || props.bboxes[0]?.frame_width || 0);
const frameH = computed(() => props.frameHeight || props.bboxes[0]?.frame_height || 0);

// Use any operator-overridden geometry when present.
function rx(b) {
  const x1 = b.override_x1 ?? b.x1;
  const y1 = b.override_y1 ?? b.y1;
  const x2 = b.override_x2 ?? b.x2;
  const y2 = b.override_y2 ?? b.y2;
  return { x: x1, y: y1, w: Math.max(1, x2 - x1), h: Math.max(1, y2 - y1) };
}

function strokeFor(b) {
  if (b.conflict) return "#BC5740"; // brick-alert: conflict always distinct
  if (!b.effective_identity_id) return "#C98A2E"; // gold-notice: unknown
  return identityColor(b.effective_identity_id);
}

function labelText(b) {
  if (b.conflict) return "Conflict";
  const name = identityLabel(b.effective_identity_id, props.targets);
  if (b.authority === "operator") return `${name} ✓`;
  return name;
}

function labelWidth(b) {
  return Math.min(frameW.value, 9 * labelText(b).length + 16);
}

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
.overlay-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.bbox-group.selectable {
  cursor: pointer;
}
.bbox-group.selectable:focus-visible rect {
  stroke-width: 5;
  outline: none;
}
.overlay-label {
  fill: #fff;
  font-size: 16px;
  font-weight: 600;
  font-family: var(--cc-font, sans-serif);
}
</style>
