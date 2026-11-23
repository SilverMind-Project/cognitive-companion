<!-- Backend: backend/steps/builtin/quiz_start.py -->
<template>
  <div>
    <v-alert v-if="quizzesError" type="warning" variant="tonal" density="compact" class="mb-4">
      Could not load quizzes: {{ quizzesError }}
    </v-alert>

    <v-autocomplete
      :model-value="modelValue.quiz_id"
      :items="quizzes"
      :loading="quizzesLoading"
      item-title="title"
      item-value="id"
      label="Quiz"
      hint="Only approved quizzes are listed."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, quiz_id: $event })"
    >
      <template #item="{ props: itemProps, item }">
        <v-list-item v-bind="itemProps">
          <template #subtitle>
            <span class="text-caption">
              #{{ item.raw.id }} · {{ item.raw.question_count }}
              {{ item.raw.question_count === 1 ? "question" : "questions" }}
              <span v-if="item.raw.tags?.length"> · {{ item.raw.tags.join(", ") }}</span>
            </span>
          </template>
        </v-list-item>
      </template>
    </v-autocomplete>

    <v-select
      :model-value="modelValue.interaction_mode"
      :items="MODE_OPTIONS"
      label="How answers are treated"
      hint="Gentle never tells the senior an answer was wrong and shows no score; answers are still recorded for caregivers."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, interaction_mode: $event })"
    />

    <div class="text-overline text-medium-emphasis mb-2">Delivery</div>
    <v-row dense class="mb-2">
      <v-col v-for="option in CHANNEL_OPTIONS" :key="option.value" cols="12" sm="6">
        <v-checkbox
          :model-value="hasChannel(option.value)"
          :label="option.title"
          :disabled="hasChannel(option.value) && (modelValue.channels || []).length === 1"
          hide-details
          density="compact"
          @update:model-value="toggleChannel(option.value, $event)"
        />
      </v-col>
    </v-row>

    <v-row dense>
      <v-col cols="12" sm="4">
        <v-text-field
          :model-value="modelValue.max_questions"
          label="Questions to ask"
          type="number"
          :min="1"
          @update:model-value="emitInt('max_questions', $event, 1)"
        />
      </v-col>
      <v-col cols="12" sm="4">
        <v-text-field
          :model-value="modelValue.session_timeout_minutes"
          label="Time out after (minutes)"
          type="number"
          :min="1"
          @update:model-value="emitInt('session_timeout_minutes', $event, 1)"
        />
      </v-col>
      <v-col cols="12" sm="4">
        <v-text-field
          :model-value="modelValue.dedupe_hours"
          label="Skip if completed within (hours)"
          type="number"
          :min="0"
          hint="0 always delivers."
          persistent-hint
          @update:model-value="emitInt('dedupe_hours', $event, 0)"
        />
      </v-col>
    </v-row>

    <v-switch
      :model-value="modelValue.randomize_order"
      label="Shuffle question order"
      hide-details
      class="mb-2"
      @update:model-value="emit('update:modelValue', { ...modelValue, randomize_order: $event })"
    />

    <v-text-field
      :model-value="modelValue.person_id"
      label="Resident (optional)"
      hint="Fills {{senior_name}}. Blank uses the person in the trigger or upstream steps. Supports {{template}} syntax."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, person_id: $event })"
    />

    <template v-if="hasChannel('voice')">
      <TemplateInput
        :model-value="modelValue.voice_instruction"
        label="Voice instruction (optional)"
        :multiline="true"
        :rows="2"
        hint="Added to the companion's persona for this quiz; the gentle or standard rules always follow it. Type {{ to autocomplete."
        class="mb-4"
        @update:model-value="
          emit('update:modelValue', { ...modelValue, voice_instruction: $event })
        "
      />
    </template>

    <v-checkbox
      :model-value="modelValue.trigger_cooloff"
      label="Trigger cool-off after delivery"
      hint="Prevents this rule from firing again until its cooldown elapses."
      persistent-hint
      hide-details="auto"
      @update:model-value="emit('update:modelValue', { ...modelValue, trigger_cooloff: $event })"
    />
  </div>
</template>

<script>
import TemplateInput from "./_shared/TemplateInput.vue";

const CHANNEL_ORDER = ["pwa", "voice"];

export const stepDefaults = {
  quiz_id: null,
  channels: ["pwa", "voice"],
  interaction_mode: "gentle",
  person_id: "",
  max_questions: 5,
  randomize_order: false,
  session_timeout_minutes: 10,
  trigger_cooloff: true,
  dedupe_hours: 12,
  voice_instruction: "",
};
export const stepTabs = [];

export function chips(cfg, { chip }) {
  const out = [];
  if (cfg.quiz_id) out.push(chip(`Quiz #${cfg.quiz_id}`, "mdi-help-box-outline"));
  out.push(
    chip(
      cfg.interaction_mode === "standard" ? "graded" : "gentle",
      cfg.interaction_mode === "standard" ? "mdi-check-decagram" : "mdi-heart-outline",
    ),
  );
  const channels = (cfg.channels || []).filter((c) => CHANNEL_ORDER.includes(c));
  if (channels.length) out.push(chip(channels.join(" + "), "mdi-tablet-cellphone"));
  return out;
}
</script>

<script setup>
import { onMounted, ref } from "vue";
import { getQuizzes } from "@/services/modules/quizzes";

const props = defineProps({
  modelValue: { type: Object, required: true },
});
const emit = defineEmits(["update:modelValue"]);

const MODE_OPTIONS = [
  { title: "Gentle: errorless learning, no right or wrong (recommended)", value: "gentle" },
  { title: "Standard: right or not, with a score", value: "standard" },
];
const CHANNEL_OPTIONS = [
  { title: "Companion tablet", value: "pwa" },
  { title: "Voice (spoken by the companion)", value: "voice" },
];

const quizzes = ref([]);
const quizzesLoading = ref(false);
const quizzesError = ref("");

function hasChannel(name) {
  return (props.modelValue.channels || []).includes(name);
}

function toggleChannel(name, on) {
  const current = new Set(props.modelValue.channels || []);
  if (on) current.add(name);
  else current.delete(name);
  if (current.size === 0) return; // the backend requires at least one channel
  emit("update:modelValue", {
    ...props.modelValue,
    channels: CHANNEL_ORDER.filter((c) => current.has(c)),
  });
}

function emitInt(key, raw, min) {
  const parsed = parseInt(raw, 10);
  if (Number.isNaN(parsed)) return;
  emit("update:modelValue", { ...props.modelValue, [key]: Math.max(min, parsed) });
}

onMounted(async () => {
  quizzesLoading.value = true;
  try {
    // The list endpoint caps limit at 200.
    const res = await getQuizzes({ status: "approved", limit: 200 });
    quizzes.value = res.items ?? [];
  } catch (err) {
    quizzesError.value = err.message || String(err);
  } finally {
    quizzesLoading.value = false;
  }
});
</script>
