<template>
  <AppDialog
    :model-value="modelValue"
    size="xl"
    icon="mdi-eye-outline"
    label="Vision Confirm"
    title="Edit Vision Logic"
    confirm-label="Apply"
    @update:model-value="$emit('update:modelValue', $event)"
    @confirm="confirm"
  >
    <div class="pa-4 text-center text-medium-emphasis">
      Vision logic canvas editor placeholder
    </div>
  </AppDialog>
</template>

<script setup>
import AppDialog from "@/components/common/AppDialog.vue";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  gate: { type: Object, default: () => ({}) },
});

const emit = defineEmits(["update:modelValue", "save", "close"]);

function confirm() {
  emit("save", props.gate);
  emit("update:modelValue", false);
}
</script>
