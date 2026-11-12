<template>
  <div class="app-dialog-sections d-flex flex-grow-1" :class="compact ? 'flex-column' : 'flex-row'">
    <v-tabs
      :model-value="modelValue"
      :direction="compact ? 'horizontal' : 'vertical'"
      color="primary"
      show-arrows
      class="app-dialog-nav flex-shrink-0"
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <v-tab
        v-for="entry in sections"
        :key="entry.key"
        :value="entry.key"
        :prepend-icon="entry.icon"
      >
        {{ entry.label }}
        <v-icon
          v-if="entry.error"
          size="16"
          color="error"
          class="ml-2"
          aria-label="Needs attention"
        >
          mdi-alert-circle
        </v-icon>
      </v-tab>
    </v-tabs>
    <v-divider :vertical="!compact" />
    <div class="app-dialog-section-body flex-grow-1 overflow-y-auto">
      <v-window :model-value="modelValue">
        <v-window-item v-for="entry in sections" :key="entry.key" :value="entry.key">
          <div class="px-6 py-5">
            <div v-if="entry.description" class="text-body-2 text-medium-emphasis mb-5">
              {{ entry.description }}
            </div>
            <slot :name="`section-${entry.key}`" />
          </div>
        </v-window-item>
      </v-window>
    </div>
    <template v-if="$slots.trailing && !compact">
      <v-divider vertical />
      <div class="app-dialog-trailing flex-shrink-0 px-4 py-5 d-flex flex-column">
        <slot name="trailing" />
      </div>
    </template>
  </div>
</template>

<script setup>
/**
 * The sectioned body of `AppDialog`: a section nav (vertical beside the content, horizontal above
 * it when `compact`) and one `#section-<key>` slot per section, one shown at a time. An optional
 * `#trailing` slot is a reference panel to the right of the sections on wide screens. Kept apart
 * from `AppDialog` so only sectioned dialogs pull in the tab and window components.
 */
defineProps({
  /** `{ key, label, icon, description?, error? }` entries, in nav order. */
  sections: { type: Array, required: true },
  /** Active section key. */
  modelValue: { type: String, default: null },
  /** Stack the nav above the content (small screens). */
  compact: { type: Boolean, default: false },
});

defineEmits(["update:modelValue"]);
</script>

<style scoped>
.app-dialog-sections {
  min-height: 0;
}

.app-dialog-nav {
  background-color: var(--cc-bg-elevated);
}

.app-dialog-sections.flex-row .app-dialog-nav {
  width: 200px;
  padding-top: 12px;
}

.app-dialog-sections.flex-row .app-dialog-nav :deep(.v-tab) {
  justify-content: flex-start !important;
  padding-inline: 20px !important;
  border-radius: 0;
  font-weight: 500;
  height: 44px;
}

.app-dialog-section-body {
  min-width: 0;
  min-height: 0;
}

.app-dialog-trailing {
  width: 360px;
  min-height: 0;
  background-color: var(--cc-bg-elevated);
}

.app-dialog-section-body :deep(.v-window),
.app-dialog-section-body :deep(.v-window__container) {
  overflow: visible;
}
</style>
