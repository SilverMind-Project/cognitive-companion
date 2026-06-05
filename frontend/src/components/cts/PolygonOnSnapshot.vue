<template>
  <CcSpatialEditor
    :model-value="shapes"
    :image-url="imageUrl"
    :image-class="imageClass"
    mode="polygon"
    coord-space="normalized"
    :readonly="readonly"
    :min-points="minPoints"
    :max-points="maxPoints"
    :max-shapes="1"
    :show-zoom="true"
    :hide-internal-polygon="maraudersState.enabled"
    @update:model-value="onUpdate"
    @closed="onClosed"
    @clear="emit('clear')"
  >
    <template #overlay="{ contentRect, isDragging }">
      <MaraudersInkPolygon
        v-if="maraudersState.enabled && !isDragging && localPolygon.length >= 3"
        :points="localPolygon"
        :canvas-w="contentRect.width"
        :canvas-h="contentRect.height"
        :seed-key="`polygon-on-snapshot-${imageUrl}`"
      />
    </template>
  </CcSpatialEditor>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import CcSpatialEditor from "@/components/common/CcSpatialEditor.vue";
import MaraudersInkPolygon from "@/components/marauders/MaraudersInkPolygon.vue";
import { useMaraudersMode } from "@/composables/useMaraudersMode.js";

const props = defineProps({
  imageUrl: { type: String, default: null },
  imageClass: { type: String, default: "" },
  modelValue: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
  minPoints: { type: Number, default: 3 },
  maxPoints: { type: Number, default: null },
});

const emit = defineEmits(["update:modelValue", "closed", "clear"]);
const { state: maraudersState } = useMaraudersMode();
const localPolygon = ref(props.modelValue);

const shapes = computed(() => {
  if (!localPolygon.value.length) return [];
  return [{ id: "polygon", type: "polygon", points: localPolygon.value }];
});

watch(
  () => props.modelValue,
  (value) => {
    localPolygon.value = value;
  },
);

function firstPolygonPoints(value) {
  return value[0]?.points ?? [];
}

function onUpdate(value) {
  localPolygon.value = firstPolygonPoints(value);
  emit("update:modelValue", localPolygon.value);
}

function onClosed(shape) {
  emit("closed", shape?.points ?? localPolygon.value);
}
</script>
