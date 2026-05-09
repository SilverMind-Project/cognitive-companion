<!-- Backend: backend/steps/builtin/interactive_prompt.py -->
<template>
  <v-alert type="info" variant="tonal" density="compact" class="mb-4">
    Configure at least one channel (popup or voice) to prompt the user for a response.
  </v-alert>

  <v-textarea
    :model-value="modelValue.popup_message_template"
    label="Popup Message Template"
    rows="3"
    hint="Message shown in the PWA popup dialog. Use {{variable}} syntax for pipeline data."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, popup_message_template: $event })"
  />

  <v-row>
    <v-col cols="12" md="6">
      <v-text-field
        :model-value="modelValue.popup_title"
        label="Popup Title"
        hint="Default: 'Question for You'"
        persistent-hint
        @update:model-value="emit('update:modelValue', { ...modelValue, popup_title: $event })"
      />
    </v-col>
    <v-col cols="12" md="6">
      <v-select
        :model-value="modelValue.popup_icon"
        :items="interactivePromptIconOptions"
        item-title="title"
        item-value="value"
        label="Popup Icon"
        hint="Icon displayed at the top of the popup"
        persistent-hint
        @update:model-value="emit('update:modelValue', { ...modelValue, popup_icon: $event })"
      >
        <template #item="{ props: itemProps, item }">
          <v-list-item v-bind="itemProps">
            <template #prepend>
              <v-icon>{{ item.raw.value }}</v-icon>
            </template>
          </v-list-item>
        </template>
        <template #selection="{ item }">
          <v-icon class="mr-2">{{ item.raw.value }}</v-icon>
          {{ item.raw.title }}
        </template>
      </v-select>
    </v-col>
  </v-row>

  <v-textarea
    :model-value="modelValue.voice_prompt_template"
    label="Voice Prompt Template"
    rows="3"
    hint="Conversational prompt for Gemini Live voice channel. Use {{variable}} syntax. When set, the microphone auto-enables so the user can reply."
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, voice_prompt_template: $event })"
  />

  <v-divider class="mb-4" />

  <v-row>
    <v-col cols="6">
      <v-text-field
        :model-value="modelValue.escalate_button_text"
        label="Escalate Button Text"
        hint="Default: 'I need help'"
        persistent-hint
        @update:model-value="emit('update:modelValue', { ...modelValue, escalate_button_text: $event })"
      />
    </v-col>
    <v-col cols="6">
      <v-text-field
        :model-value="modelValue.dismiss_button_text"
        label="Dismiss Button Text"
        hint="Default: 'I'm okay'"
        persistent-hint
        @update:model-value="emit('update:modelValue', { ...modelValue, dismiss_button_text: $event })"
      />
    </v-col>
  </v-row>

  <v-slider
    :model-value="modelValue.countdown_seconds"
    label="Countdown Duration (seconds)"
    :min="5" :max="300" :step="5"
    thumb-label="always"
    color="primary"
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, countdown_seconds: $event })"
  />

  <v-select
    :model-value="modelValue.timeout_action"
    :items="[
      { title: 'Escalate (treat as help needed)', value: 'escalate' },
      { title: 'Dismiss (treat as okay)', value: 'dismiss' },
    ]"
    item-title="title"
    item-value="value"
    label="Timeout Action"
    hint="Action to take when user doesn't respond in time"
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, timeout_action: $event })"
  />

  <v-checkbox
    :model-value="modelValue.auto_escalate"
    label="Auto-escalate on affirmative response or timeout"
    hint="Sets pipeline_data.auto_escalate_triggered flag for downstream conditional logic"
    persistent-hint
    class="mb-4"
    @update:model-value="emit('update:modelValue', { ...modelValue, auto_escalate: $event })"
  />

  <v-text-field
    :model-value="modelValue.output_key"
    label="Output Key"
    hint="pipeline_data key for the response. Default: interactive_response"
    persistent-hint
    @update:model-value="emit('update:modelValue', { ...modelValue, output_key: $event })"
  />
</template>

<script>
export const stepDefaults = {
  popup_message_template: "",
  voice_prompt_template: "",
  escalate_button_text: "",
  dismiss_button_text: "",
  countdown_seconds: 30,
  timeout_action: "escalate",
  auto_escalate: false,
  popup_title: "",
  popup_icon: "mdi-message-question",
  output_key: "interactive_response",
};
export const stepTabs = [];
</script>

<script setup>
defineProps({
  modelValue: { type: Object, required: true },
});
const emit = defineEmits(["update:modelValue"]);

const interactivePromptIconOptions = [
  { title: "Question", value: "mdi-message-question" },
  { title: "Help", value: "mdi-help-circle" },
  { title: "Warning", value: "mdi-alert" },
  { title: "Alert", value: "mdi-alert-circle" },
  { title: "Critical Alert", value: "mdi-alert-octagon" },
  { title: "Bell", value: "mdi-bell" },
  { title: "Bell Ring", value: "mdi-bell-ring" },
  { title: "Information", value: "mdi-information" },
  { title: "Speaker", value: "mdi-volume-high" },
  { title: "Voice", value: "mdi-account-voice" },
  { title: "Check", value: "mdi-check-circle" },
  { title: "Health", value: "mdi-heart-pulse" },
  { title: "Medication", value: "mdi-pill" },
  { title: "Greeting", value: "mdi-human-greeting" },
];
</script>
