<template>
  <v-card variant="outlined" rounded="lg" class="pa-3">
    <div class="d-flex align-center mb-2">
      <span class="text-subtitle-2 font-weight-medium">Region Properties</span>
      <v-spacer />
      <v-btn
        icon="mdi-delete"
        size="x-small"
        variant="text"
        color="error"
        @click="$emit('delete')"
      />
    </div>

    <v-text-field
      :model-value="region.name"
      label="Name"
      variant="outlined"
      density="compact"
      class="mb-2"
      @update:model-value="update('name', $event)"
    />

    <v-row dense class="mb-2">
      <v-col cols="3">
        <v-text-field
          :model-value="region.x"
          label="X"
          type="number"
          variant="outlined"
          density="compact"
          @update:model-value="update('x', Number($event))"
        />
      </v-col>
      <v-col cols="3">
        <v-text-field
          :model-value="region.y"
          label="Y"
          type="number"
          variant="outlined"
          density="compact"
          @update:model-value="update('y', Number($event))"
        />
      </v-col>
      <v-col cols="3">
        <v-text-field
          :model-value="region.width"
          label="W"
          type="number"
          variant="outlined"
          density="compact"
          @update:model-value="update('width', Number($event))"
        />
      </v-col>
      <v-col cols="3">
        <v-text-field
          :model-value="region.height"
          label="H"
          type="number"
          variant="outlined"
          density="compact"
          @update:model-value="update('height', Number($event))"
        />
      </v-col>
    </v-row>

    <v-select
      :model-value="region.align"
      :items="['left', 'center', 'right']"
      label="Text Align"
      variant="outlined"
      density="compact"
      class="mb-2"
      @update:model-value="update('align', $event)"
    />

    <v-slider
      :model-value="region.font_size_max"
      label="Max Font"
      :min="12"
      :max="96"
      :step="2"
      thumb-label
      density="compact"
      class="mb-1"
      @update:model-value="update('font_size_max', $event)"
    />

    <v-slider
      :model-value="region.font_size_min"
      label="Min Font"
      :min="8"
      :max="48"
      :step="2"
      thumb-label
      density="compact"
      @update:model-value="update('font_size_min', $event)"
    />
  </v-card>
</template>

<script setup>
const props = defineProps({
  region: { type: Object, required: true },
});

const emit = defineEmits(["update:region", "delete"]);

function update(key, value) {
  emit("update:region", { ...props.region, [key]: value });
}
</script>
