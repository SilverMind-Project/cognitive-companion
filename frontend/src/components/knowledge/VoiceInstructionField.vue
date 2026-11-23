<template>
  <div class="d-flex align-start ga-2" data-test="voice-instruction-field">
    <v-textarea
      :model-value="modelValue"
      label="Voice instruction (optional)"
      rows="2"
      auto-grow
      :placeholder="defaultText"
      persistent-placeholder
      :hint="hint"
      persistent-hint
      data-test="voice-instruction"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <v-btn
      variant="tonal"
      color="secondary"
      prepend-icon="mdi-auto-fix"
      :loading="suggesting"
      :disabled="!documentId"
      data-test="suggest-voice"
      @click="suggest"
    >
      Suggest
    </v-btn>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useNotify } from "@/composables/useNotify.js";
import { getVoiceDefaults } from "@/services/modules/knowledge";
import { suggestQuizVoiceInstruction } from "@/services/modules/quizzes";

const props = defineProps({
  modelValue: { type: String, default: "" },
  // "quiz" or "info_card": picks the default shown and the kind of suggestion.
  resourceType: { type: String, required: true },
  // The source document a suggestion is drafted from; Suggest is disabled without one.
  documentId: { type: Number, default: null },
});
const emit = defineEmits(["update:modelValue"]);
const { notify } = useNotify();

const defaultText = ref("");
const suggesting = ref(false);

const hint = computed(() =>
  props.resourceType === "quiz"
    ? "How the companion conducts this quiz, added to its usual persona. Blank uses the default shown. The gentle or standard rules always follow it."
    : "How the companion reads this card aloud, added to its usual persona. Blank uses the default shown.",
);

async function suggest() {
  if (!props.documentId) return;
  suggesting.value = true;
  try {
    const res = await suggestQuizVoiceInstruction(props.documentId, props.resourceType);
    if (res?.voice_instruction) emit("update:modelValue", res.voice_instruction);
  } catch (err) {
    notify.error("Failed to suggest a voice instruction: " + (err.message || err));
  } finally {
    suggesting.value = false;
  }
}

onMounted(async () => {
  try {
    const defaults = await getVoiceDefaults();
    defaultText.value = defaults?.[`${props.resourceType}_default`] ?? "";
  } catch (err) {
    notify.warning("Could not load the default voice instruction: " + (err.message || err));
  }
});
</script>
