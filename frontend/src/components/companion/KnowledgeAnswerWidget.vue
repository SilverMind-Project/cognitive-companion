<template>
  <v-dialog :model-value="visible" max-width="600" persistent @update:model-value="onClose">
    <v-card class="knowledge-answer-card">
      <v-card-item class="pb-0">
        <template #prepend>
          <div class="ka-icon-wrap">
            <v-icon color="var(--cc-brand)" size="28">mdi-lightbulb-on-outline</v-icon>
          </div>
        </template>
        <v-card-title class="ka-title">Here's what I found</v-card-title>
      </v-card-item>

      <v-divider class="mx-4 my-3" />

      <v-card-text class="pt-0">
        <p v-if="queryText" class="ka-query">{{ queryText }}</p>
        <p class="ka-answer">{{ answerText || "I don't have that information." }}</p>
      </v-card-text>

      <v-divider class="mx-4" />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn color="primary" variant="flat" size="large" class="px-8 ka-btn" @click="onClose">
          Got it
        </v-btn>
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
  // Changes on every delivered answer so the dialog reopens even when the
  // same question is asked again (identical queryText would not retrigger).
  serverTimestamp: { type: String, default: "" },
});

const emit = defineEmits(["close"]);

const visible = ref(false);

function onClose() {
  visible.value = false;
  emit("close");
}

// Reopen whenever a new answer is delivered (per-answer timestamp), provided
// there is a question to show.
watch(
  () => props.serverTimestamp,
  (ts) => {
    if (ts && props.queryText) visible.value = true;
  },
);
</script>

<style scoped>
.ka-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--cc-radius-pill);
  background: var(--cc-brand-soft);
}

.ka-title {
  font-family: var(--cc-font-display);
  font-weight: 500;
  font-size: 1.75rem;
  letter-spacing: -0.01em;
  line-height: 1.2;
}

/* The senior's own question, echoed in serif italic sage (DS TranscriptBubble) */
.ka-query {
  font-family: var(--cc-font-display);
  font-style: italic;
  font-size: 1.25rem;
  line-height: 1.4;
  color: var(--sage-700);
  margin: 8px 0 12px;
}

.ka-answer {
  font-size: 1.25rem;
  line-height: 1.55;
  color: var(--cc-text-1);
  margin: 0;
  white-space: pre-wrap;
}

.ka-btn {
  min-height: 56px;
  font-weight: 600;
  letter-spacing: 0.01em;
  border-radius: var(--cc-radius-md);
}
</style>
