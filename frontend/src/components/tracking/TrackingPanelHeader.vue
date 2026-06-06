<template>
  <div class="d-flex align-start flex-wrap ga-3 mb-4">
    <div class="tracking-panel-header__copy">
      <h2 class="text-h5 font-weight-bold tracking-tight">{{ title }}</h2>
      <div v-if="description" class="text-body-2 text-medium-emphasis mt-1">
        {{ description }}
      </div>
    </div>
    <div
      v-if="$slots.actions"
      class="tracking-panel-header__actions d-flex align-center flex-wrap ga-2"
    >
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: "" },
});
</script>

<style scoped>
.tracking-panel-header__copy {
  min-width: 0;
  max-width: 760px;
}

.tracking-panel-header__actions {
  margin-left: auto;
}
</style>
