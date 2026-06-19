<template>
  <v-dialog
    :model-value="modelValue"
    :width="resolvedWidth"
    max-width="98vw"
    :fullscreen="$vuetify.display.smAndDown"
    scrollable
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <v-card class="cc-glass app-dialog-card d-flex flex-column">
      <DialogHeader :icon="icon" :label="label" :title="title" @close="close" />
      <div class="app-dialog-body flex-grow-1 overflow-auto">
        <slot />
      </div>
      <DialogFooter
        v-if="!hideFooter"
        :hint="hint"
        :confirm-label="confirmLabel"
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
import { computed } from "vue";
import DialogHeader from "./DialogHeader.vue";
import DialogFooter from "./DialogFooter.vue";

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
  hint: { type: String, default: "" },
  confirmLabel: { type: String, default: "Save" },
  cancelLabel: { type: String, default: "Cancel" },
  confirmLoading: { type: Boolean, default: false },
  confirmDisabled: { type: Boolean, default: false },
  hideFooter: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "confirm", "cancel", "close"]);

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

function close() {
  emit("update:modelValue", false);
  emit("cancel");
  emit("close");
}
</script>
