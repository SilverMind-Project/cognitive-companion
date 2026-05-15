<template>
  <v-dialog :model-value="visible" max-width="480" persistent @update:model-value="onClose">
    <v-card class="knowledge-answer-card">
      <v-card-item>
        <template #prepend>
          <v-icon color="primary" size="28">mdi-brain</v-icon>
        </template>
        <v-card-title class="text-h6">Knowledge</v-card-title>
      </v-card-item>
      <v-card-text>
        <p class="text-body-1 font-weight-medium">{{ queryText }}</p>
        <v-divider class="my-2" />
        <p class="text-body-1">{{ answerText || "I don't have that information." }}</p>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" color="primary" @click="onClose">Got it</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  queryText: { type: String, default: "" },
  answerText: { type: String, default: "" },
  sourceDocumentIds: { type: Array, default: () => [] },
});

const emit = defineEmits(["close"]);

const visible = ref(false);

function onClose() {
  visible.value = false;
  emit("close");
}

watch(
  () => props.queryText,
  (val) => {
    if (val) visible.value = true;
  }
);

function show(query, answer, sourceIds = []) {
  if (query) visible.value = true;
}

defineExpose({ show });
</script>
