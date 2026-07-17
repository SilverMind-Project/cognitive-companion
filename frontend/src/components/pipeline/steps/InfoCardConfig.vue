<!-- Backend: backend/steps/builtin/info_card.py -->
<template>
  <div>
    <v-alert v-if="cardsError" type="warning" variant="tonal" density="compact" class="mb-4">
      Could not load info cards: {{ cardsError }}
    </v-alert>

    <v-autocomplete
      :model-value="modelValue.info_card_id"
      :items="approvedCards"
      :loading="cardsLoading"
      item-title="title"
      item-value="id"
      label="Info Card"
      hint="The card to deliver. Only approved cards are listed; templated title/body_text are rendered at delivery time."
      persistent-hint
      variant="outlined"
      density="compact"
      hide-details="auto"
      rounded="lg"
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, info_card_id: $event })"
    >
      <template #item="{ props: itemProps, item }">
        <v-list-item v-bind="itemProps">
          <template #subtitle>
            <span class="text-caption">
              #{{ item.raw.id }}
              <span v-if="item.raw.layout_id"> · layout {{ item.raw.layout_id }}</span>
              <span v-if="containsTemplate(item.raw.title) || containsTemplate(item.raw.body_text)">
                · <v-icon size="12">mdi-code-braces</v-icon> templated
              </span>
            </span>
          </template>
        </v-list-item>
      </template>
    </v-autocomplete>

    <div class="text-overline text-medium-emphasis mb-2">Delivery channels</div>

    <v-row dense class="mb-4">
      <v-col cols="12" sm="4">
        <v-checkbox
          :model-value="hasChannel('pwa')"
          label="PWA popup"
          hide-details
          density="compact"
          @update:model-value="toggleChannel('pwa', $event)"
        />
      </v-col>
      <v-col cols="12" sm="4">
        <v-checkbox
          :model-value="hasChannel('eink')"
          label="eInk display"
          hide-details
          density="compact"
          @update:model-value="toggleChannel('eink', $event)"
        />
      </v-col>
      <v-col cols="12" sm="4">
        <v-checkbox
          :model-value="hasChannel('voice')"
          label="Voice (Gemini Live)"
          hide-details
          density="compact"
          @update:model-value="toggleChannel('voice', $event)"
        />
      </v-col>
    </v-row>

    <v-row dense>
      <v-col v-if="hasChannel('pwa')" cols="12" md="6">
        <v-text-field
          :model-value="modelValue.pwa_dismiss_seconds"
          label="PWA dismiss after (seconds)"
          type="number"
          :min="5"
          :max="600"
          variant="outlined"
          density="compact"
          hide-details="auto"
          rounded="lg"
          hint="Auto-dismiss the popup after N seconds"
          persistent-hint
          class="mb-4"
          @update:model-value="
            emit('update:modelValue', {
              ...modelValue,
              pwa_dismiss_seconds: Math.max(5, Math.min(600, Number($event) || 60)),
            })
          "
        />
      </v-col>
      <v-col v-if="hasChannel('eink')" cols="12" md="6">
        <v-text-field
          :model-value="modelValue.eink_expiry_minutes"
          label="eInk expiry (minutes)"
          type="number"
          :min="1"
          :max="1440"
          variant="outlined"
          density="compact"
          hide-details="auto"
          rounded="lg"
          hint="Revert eInk to default after N minutes"
          persistent-hint
          class="mb-4"
          @update:model-value="
            emit('update:modelValue', {
              ...modelValue,
              eink_expiry_minutes: Math.max(1, Math.min(1440, Number($event) || 30)),
            })
          "
        />
      </v-col>
    </v-row>

    <template v-if="hasChannel('voice')">
      <div class="text-overline text-medium-emphasis mb-2">Voice instruction (optional)</div>
      <TemplateInput
        :model-value="modelValue.voice_instruction"
        :multiline="true"
        :rows="3"
        hint="Overrides the Gemini Live system instruction. Supports {{template}} syntax (type {{ for variable autocomplete)."
        @update:model-value="
          emit('update:modelValue', { ...modelValue, voice_instruction: $event })
        "
      />
    </template>

    <v-divider class="my-4" />

    <v-checkbox
      :model-value="modelValue.trigger_cooloff"
      label="Trigger cool-off after delivery"
      hint="Prevents this rule from firing again until its cooldown elapses."
      persistent-hint
      hide-details="auto"
      class="mb-1"
      @update:model-value="emit('update:modelValue', { ...modelValue, trigger_cooloff: $event })"
    />
  </div>
</template>

<script>
import TemplateInput from "./_shared/TemplateInput.vue";

export const stepDefaults = {
  info_card_id: null,
  channels: ["pwa"],
  pwa_dismiss_seconds: 60,
  eink_expiry_minutes: 30,
  voice_instruction: "",
  trigger_cooloff: true,
};
export const stepTabs = [];
</script>

<script setup>
import { ref, computed, onMounted } from "vue";
import { api } from "@/services/api.js";

const props = defineProps({
  modelValue: { type: Object, required: true },
});
const emit = defineEmits(["update:modelValue"]);

const allCards = ref([]);
const cardsLoading = ref(false);
const cardsError = ref("");

const approvedCards = computed(() => allCards.value.filter((c) => c.status === "approved"));

function hasChannel(name) {
  const channels = props.modelValue.channels || [];
  return channels.includes(name);
}

function toggleChannel(name, on) {
  const current = new Set(props.modelValue.channels || []);
  if (on) current.add(name);
  else current.delete(name);
  // Preserve original ordering for stable diffs: pwa, eink, voice.
  const ordered = ["pwa", "eink", "voice"].filter((c) => current.has(c));
  emit("update:modelValue", { ...props.modelValue, channels: ordered });
}

function containsTemplate(s) {
  return typeof s === "string" && s.includes("{{");
}

onMounted(async () => {
  cardsLoading.value = true;
  try {
    const res = await api.getInfoCards({ status: "approved", limit: 500 });
    allCards.value = res.items ?? [];
  } catch (err) {
    cardsError.value = err.message || String(err);
  } finally {
    cardsLoading.value = false;
  }
});
</script>
