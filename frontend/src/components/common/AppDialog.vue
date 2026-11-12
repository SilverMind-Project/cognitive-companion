<template>
  <v-dialog
    :model-value="modelValue"
    :width="resolvedWidth"
    max-width="98vw"
    :persistent="persistent"
    :fullscreen="$vuetify.display.smAndDown"
    scrollable
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <v-card
      class="cc-glass app-dialog-card d-flex flex-column"
      :class="{ 'app-dialog-card--fixed': isWorkspaceLayout }"
    >
      <DialogHeader :icon="icon" :label="label" :title="title" @close="close" />

      <!-- Sectioned layout: section nav on the left, one section shown at a time. -->
      <AppDialogSections
        v-if="sections.length"
        :sections="sections"
        :model-value="activeSection"
        :compact="$vuetify.display.smAndDown"
        @update:model-value="selectSection"
      >
        <template v-for="entry in sections" #[`section-${entry.key}`]>
          <slot :name="`section-${entry.key}`" />
        </template>
      </AppDialogSections>

      <!-- Split layout: a narrow form column beside a visual workspace. -->
      <div
        v-else-if="$slots.aside"
        class="app-dialog-split d-flex flex-grow-1"
        :class="$vuetify.display.smAndDown ? 'flex-column overflow-y-auto' : 'flex-row'"
      >
        <div class="app-dialog-aside flex-shrink-0 px-6 py-5">
          <slot name="aside" />
        </div>
        <v-divider :vertical="!$vuetify.display.smAndDown" />
        <div class="app-dialog-main flex-grow-1 px-6 py-5">
          <slot />
        </div>
      </div>

      <div v-else class="app-dialog-body flex-grow-1 overflow-auto">
        <slot />
      </div>

      <DialogFooter
        v-if="!hideFooter"
        :hint="hint"
        :confirm-label="confirmLabel"
        :confirm-color="confirmColor"
        :cancel-label="cancelLabel"
        :confirm-loading="confirmLoading"
        :confirm-disabled="confirmDisabled"
        @cancel="close"
        @confirm="$emit('confirm')"
      >
        <template v-if="$slots.footerActions" #actions>
          <slot name="footerActions" />
        </template>
        <template v-if="$slots.hint" #hint>
          <slot name="hint" />
        </template>
      </DialogFooter>
      <slot name="footer" />
    </v-card>
  </v-dialog>
</template>

<script setup>
/**
 * The shared modal shell. Pick `size` by content, then a body layout:
 *
 * - `sm` / `md`: the default slot, a single form column (`md` pairs short fields in two columns).
 * - `lg` + `sections`: a left section nav with one `#section-<key>` slot per section, for forms
 *   with several distinct concerns. The body height is fixed so switching sections never resizes
 *   the dialog. Bind `v-model:section` to jump to a section (for example, one that failed
 *   validation); each section may set `error: true` to flag itself in the nav.
 * - `lg` + `#aside`: a split body, a narrow form column (`#aside`) beside a visual workspace
 *   (default slot) such as a snapshot, map, or drawing canvas.
 * - `xl`: workbench and inspector bodies that lay out their own panes in the default slot.
 *
 * Create and edit forms pass `persistent` so a stray backdrop click cannot discard input.
 */
import { computed, ref, watch } from "vue";
import DialogHeader from "./DialogHeader.vue";
import DialogFooter from "./DialogFooter.vue";
import AppDialogSections from "./AppDialogSections.vue";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  icon: { type: String, required: true },
  label: { type: String, required: true },
  title: { type: String, required: true },
  size: {
    type: String,
    default: "md",
    validator: (val) => ["sm", "md", "lg", "xl"].includes(val),
  },
  width: { type: [Number, String], default: null },
  persistent: { type: Boolean, default: false },
  /** Section nav entries: `{ key, label, icon, description?, error? }`. */
  sections: { type: Array, default: () => [] },
  /** Active section key; leave unbound to let the dialog manage it. */
  section: { type: String, default: null },
  hint: { type: String, default: "" },
  confirmLabel: { type: String, default: "Save" },
  confirmColor: { type: String, default: "primary" },
  cancelLabel: { type: String, default: "Cancel" },
  confirmLoading: { type: Boolean, default: false },
  confirmDisabled: { type: Boolean, default: false },
  hideFooter: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "update:section", "confirm", "cancel", "close"]);

const slots = defineSlots();

const sizeMap = {
  sm: 480,
  md: 720,
  lg: 1080,
  xl: 1440,
};

const resolvedWidth = computed(() => {
  if (props.width) return props.width;
  return sizeMap[props.size] || sizeMap.md;
});

const isWorkspaceLayout = computed(() => props.sections.length > 0 || !!slots.aside);

const internalSection = ref(null);

const activeSection = computed(
  () => props.section ?? internalSection.value ?? props.sections[0]?.key ?? null,
);

function selectSection(key) {
  internalSection.value = key;
  emit("update:section", key);
}

// Reopening an unbound sectioned dialog starts again at its first section.
watch(
  () => props.modelValue,
  (open) => {
    if (open) internalSection.value = null;
  },
);

function close() {
  emit("update:modelValue", false);
  emit("cancel");
  emit("close");
}
</script>

<style scoped>
/* Vuetify sizes a dialog card with `flex: 1 1 var(--v-card-height, 100%)` from a more specific
   selector, and that basis overrides `height`; pin the basis so the body keeps one height while
   sections switch. */
.app-dialog-card--fixed {
  flex: 0 0 auto !important;
  height: 82vh;
  max-height: 760px;
}

.app-dialog-split {
  min-height: 0;
}

.app-dialog-split.flex-row .app-dialog-aside {
  width: 340px;
  overflow-y: auto;
}

.app-dialog-split.flex-row .app-dialog-main {
  min-width: 0;
  overflow-y: auto;
}
</style>
