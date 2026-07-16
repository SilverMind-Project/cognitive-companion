<template>
  <div
    class="step-node"
    :class="nodeClasses"
  >
    <Handle
      id="main"
      type="target"
      :position="Position.Left"
      :connectable="!isReadonly"
      class="step-node__handle step-node__handle--input"
    />

    <div class="step-node__header">
      <v-icon :color="dotColor" size="16" class="mr-2">{{ icon }}</v-icon>
      <span class="step-node__title">{{ displayName }}</span>
    </div>

    <div v-if="data.step.label" class="step-node__label">{{ data.step.label }}</div>

    <div v-if="detailChips.length" class="step-node__chips">
      <v-chip
        v-for="chip in detailChips"
        :key="chip.key"
        size="x-small"
        :color="chip.color || undefined"
        :variant="chip.color ? 'tonal' : 'outlined'"
        :prepend-icon="chip.icon"
        class="step-node__chip"
      >
        {{ chip.label }}
      </v-chip>
    </div>

    <div v-if="textPreview" class="step-node__preview">{{ textPreview }}</div>

    <Handle
      v-for="(port, index) in outputPorts"
      :id="port"
      :key="port"
      type="source"
      :position="Position.Right"
      :connectable="!isReadonly"
      :style="portStyle(port, index, outputPorts.length)"
      :class="['step-node__handle', 'step-node__handle--output', `step-node__handle--${port}`]"
    />

    <div
      v-for="(port, index) in visiblePortLabels"
      :key="port"
      class="step-node__port-label"
      :class="`step-node__port-label--${port}`"
      :style="portLabelStyle(port, index)"
    >
      {{ port }}
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { Handle, Position } from "@vue-flow/core";
import { buildStepDetailChips } from "../steps/index.js";
import {
  buildTextPreview,
  humanize,
  stepDotColor,
  stepIcon,
} from "../steps/stepMeta.js";

const props = defineProps({
  data: { type: Object, required: true },
});

const isReadonly = computed(() => Boolean(props.data.readonly));
const outputPorts = computed(() => props.data.outputPorts?.length ? props.data.outputPorts : ["main"]);
const displayName = computed(() => humanize(props.data.step.step_type));
const icon = computed(() => stepIcon(props.data.step.step_type));
const dotColor = computed(() => stepDotColor(props.data.step.step_type));
const detailChips = computed(() => buildStepDetailChips(props.data.step).slice(0, 3));
const textPreview = computed(() => buildTextPreview(props.data.step, 90));
const status = computed(() => props.data.step.status || "pending");
const visiblePortLabels = computed(() => outputPorts.value.filter((port) => port !== "main"));
const nodeClasses = computed(() => ({
  "step-node--disabled": !isReadonly.value && !props.data.step.enabled,
  "step-node--readonly": isReadonly.value,
  [`step-node--status-${status.value}`]: isReadonly.value,
}));

function portTop(index, count) {
  if (count <= 1) return 50;
  return ((index + 1) / (count + 1)) * 100;
}

function portColor(port) {
  if (port === "true") return "rgb(var(--v-theme-success))";
  if (port === "false") return "rgb(var(--v-theme-error))";
  return "rgb(var(--v-theme-primary))";
}

function portStyle(port, index, count) {
  return {
    top: `${portTop(index, count)}%`,
    background: portColor(port),
  };
}

function portLabelStyle(port, visibleIndex) {
  const actualIndex = outputPorts.value.indexOf(port);
  return {
    top: `${portTop(actualIndex, outputPorts.value.length)}%`,
    color: portColor(port),
  };
}
</script>

<style scoped>
.step-node {
  position: relative;
  width: 280px;
  padding: 12px 14px;
  border: 1px solid var(--cc-glass-border);
  border-radius: var(--cc-radius-lg);
  background: var(--cc-bg-elevated);
  color: var(--cc-text-1);
  box-shadow: var(--cc-shadow-sm);
  cursor: grab;
}

.step-node--disabled {
  opacity: 0.5;
}

.step-node--readonly {
  cursor: default;
}

.step-node--status-running {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.18), var(--cc-shadow-md);
}

.step-node--status-succeeded {
  border-color: rgb(var(--v-theme-success));
}

.step-node--status-failed {
  border-color: rgb(var(--v-theme-error));
  box-shadow: 0 0 0 2px rgba(var(--v-theme-error), 0.16), var(--cc-shadow-md);
}

.step-node--status-skipped {
  opacity: 0.62;
}

.step-node__header {
  display: flex;
  align-items: center;
  min-width: 0;
}

.step-node__title {
  overflow: hidden;
  color: var(--cc-text-1);
  font-size: 0.9rem;
  font-weight: 700;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-node__label {
  margin-top: 4px;
  overflow: hidden;
  color: var(--cc-text-2);
  font-size: 0.76rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-node__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 9px;
}

.step-node__chip {
  max-width: 120px;
}

.step-node__chip :deep(.v-chip__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-node__preview {
  display: -webkit-box;
  margin-top: 9px;
  overflow: hidden;
  color: var(--cc-text-2);
  font-size: 0.75rem;
  font-style: italic;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.step-node__handle {
  width: 12px;
  height: 12px;
  border: 2px solid var(--cc-bg-elevated);
}

.step-node__handle--input {
  background: var(--cc-text-3);
}

.step-node__handle--output {
  right: -6px;
}

.step-node__port-label {
  position: absolute;
  right: 14px;
  transform: translateY(-50%);
  font-family: var(--cc-font-mono);
  font-size: 0.68rem;
  font-weight: 700;
  pointer-events: none;
  text-transform: uppercase;
}
</style>
