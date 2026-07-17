<!--
  Pipeline edge with an inline delete affordance.

  Renders the standard smoothstep path plus a small "x" button at the edge
  midpoint that appears on hover or when the edge is selected. Clicking it
  calls VueFlow's removeEdges, which emits an `edges-change` (type "remove")
  that PipelineCanvas persists via useCanvasPipeline.removeEdge. This lets a
  user detach two steps without deleting either node.
-->
<template>
  <BaseEdge
    :id="id"
    :path="path[0]"
    :marker-end="markerEnd"
    :style="style"
    :label="label"
    :label-x="path[1]"
    :label-y="path[2]"
    :label-style="labelStyle"
    :label-bg-style="labelBgStyle"
    :label-bg-padding="[4, 2]"
    :label-bg-border-radius="4"
  />

  <EdgeLabelRenderer>
    <button
      type="button"
      class="cc-edge-delete"
      :class="{ 'cc-edge-delete--active': selected }"
      :style="deleteButtonStyle"
      title="Delete connection"
      aria-label="Delete connection"
      @click.stop="onDelete"
      @mousedown.stop
    >
      <v-icon size="12">mdi-close</v-icon>
    </button>
  </EdgeLabelRenderer>
</template>

<script setup>
import { computed } from "vue";
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, useVueFlow } from "@vue-flow/core";

const props = defineProps({
  id: { type: String, required: true },
  sourceX: { type: Number, required: true },
  sourceY: { type: Number, required: true },
  targetX: { type: Number, required: true },
  targetY: { type: Number, required: true },
  sourcePosition: { type: String, default: undefined },
  targetPosition: { type: String, default: undefined },
  markerEnd: { type: String, default: undefined },
  style: { type: Object, default: () => ({}) },
  label: { type: String, default: "" },
  labelStyle: { type: Object, default: () => ({}) },
  labelBgStyle: { type: Object, default: () => ({}) },
  selected: { type: Boolean, default: false },
  data: { type: Object, default: () => ({}) },
});

const { removeEdges } = useVueFlow();

const path = computed(() =>
  getSmoothStepPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  }),
);

const deleteButtonStyle = computed(() => ({
  transform: `translate(-50%, -50%) translate(${path.value[1]}px, ${path.value[2]}px)`,
}));

function onDelete() {
  if (props.data?.readonly) return;
  // Emits edges-change (type "remove"); PipelineCanvas persists the removal.
  removeEdges([props.id]);
}
</script>

<style scoped>
/*
  EdgeLabelRenderer teleports this button into a flat overlay layer, so it is
  not a DOM descendant of `.vue-flow__edge` and cannot react to edge hover via
  a CSS descendant selector. We instead keep it subtly visible on every edge
  (directly answering "how do I delete a connection?") and make it prominent on
  its own hover or when the edge is selected.
*/
.cc-edge-delete {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 1px solid var(--cc-divider-strong);
  border-radius: var(--cc-radius-pill);
  background: var(--cc-bg-elevated);
  color: var(--cc-text-3);
  box-shadow: var(--cc-shadow-xs);
  cursor: pointer;
  opacity: 0.5;
  pointer-events: all;
  transition:
    opacity 0.12s ease,
    color 0.12s ease,
    border-color 0.12s ease;
}

.cc-edge-delete:hover,
.cc-edge-delete--active {
  opacity: 1;
  border-color: var(--cc-error);
  color: var(--cc-error);
}
</style>
