<!-- Generic fallback for unknown/plugin step types -->
<template>
  <v-alert type="info" variant="tonal" class="mb-4">
    This step type uses a plugin configuration. Edit the JSON config below.
  </v-alert>
  <v-textarea
    :model-value="jsonText"
    label="Config JSON"
    rows="12"
    :error-messages="jsonError"
    @update:model-value="onJsonChange"
  />
</template>

<script>
export const stepTabs = [];
</script>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({ modelValue: { type: Object, required: true } });
const emit = defineEmits(["update:modelValue"]);

const jsonText = ref("{}");
const jsonError = ref("");

watch(
  () => props.modelValue,
  (val) => {
    jsonText.value = JSON.stringify(val, null, 2);
    jsonError.value = "";
  },
  { immediate: true },
);

function onJsonChange(text) {
  jsonText.value = text;
  try {
    const parsed = JSON.parse(text);
    jsonError.value = "";
    emit("update:modelValue", parsed);
  } catch (e) {
    jsonError.value = "Invalid JSON: " + e.message;
  }
}

defineExpose({
  validateJson() {
    try {
      JSON.parse(jsonText.value);
      jsonError.value = "";
      return true;
    } catch (e) {
      jsonError.value = "Invalid JSON: " + e.message;
      return false;
    }
  },
});
</script>
