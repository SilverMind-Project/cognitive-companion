<!-- Backend: backend/steps/builtin/guided_task_start.py -->
<template>
  <div>
    <v-alert v-if="routinesError" type="warning" variant="tonal" density="compact" class="mb-4">
      Could not load routines: {{ routinesError }}
    </v-alert>

    <v-autocomplete
      :model-value="modelValue.routine_id"
      :items="routines"
      :loading="routinesLoading"
      item-title="name"
      item-value="id"
      label="Routine"
      hint="The step-by-step routine the companion walks the resident through."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, routine_id: $event })"
    >
      <template #item="{ props: itemProps, item }">
        <v-list-item v-bind="itemProps" :disabled="!item.raw.is_enabled">
          <template #subtitle>
            <span class="text-caption">
              #{{ item.raw.id }} · {{ item.raw.person_id }} · {{ item.raw.step_count }}
              {{ item.raw.step_count === 1 ? "step" : "steps" }}
              <span v-if="!item.raw.is_enabled"> · disabled</span>
            </span>
          </template>
        </v-list-item>
      </template>
    </v-autocomplete>

    <v-alert
      v-if="selected && !selected.is_enabled"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      This routine is disabled: the step will fail when it runs. Enable it in Routines.
    </v-alert>

    <v-switch
      :model-value="modelValue.require_presence"
      label="Wait for the resident before speaking the first step"
      hint="Summons the resident to a companion surface first; off starts immediately."
      persistent-hint
      class="mb-4"
      @update:model-value="emit('update:modelValue', { ...modelValue, require_presence: $event })"
    />

    <v-row dense>
      <v-col cols="12" sm="6">
        <v-text-field
          :model-value="modelValue.summon_timeout_s ?? ''"
          label="Give up waiting after (seconds)"
          type="number"
          :min="1"
          :disabled="!modelValue.require_presence"
          placeholder="Household default"
          hint="Blank uses the configured summon timeout."
          persistent-hint
          @update:model-value="emitOptionalInt('summon_timeout_s', $event, 1)"
        />
      </v-col>
      <v-col cols="12" sm="6">
        <v-text-field
          :model-value="modelValue.dedupe_hours"
          label="Skip if completed within (hours)"
          type="number"
          :min="0"
          hint="0 always starts."
          persistent-hint
          @update:model-value="emitOptionalInt('dedupe_hours', $event, 0)"
        />
      </v-col>
    </v-row>
  </div>
</template>

<script>
// summon_timeout_s is deliberately absent: its backend default comes from settings, and a
// copy here would silently override the household's configuration.
export const stepDefaults = {
  routine_id: null,
  require_presence: true,
  dedupe_hours: 0,
};
export const stepTabs = [];

export function chips(cfg, { chip }) {
  const out = [];
  if (cfg.routine_id) out.push(chip(`Routine #${cfg.routine_id}`, "mdi-format-list-checks"));
  out.push(
    cfg.require_presence === false
      ? chip("immediate", "mdi-play-outline")
      : chip("waits for resident", "mdi-account-clock-outline"),
  );
  if (cfg.dedupe_hours) out.push(chip(`dedupe ${cfg.dedupe_hours}h`, "mdi-timer-sand"));
  return out;
}
</script>

<script setup>
import { computed, onMounted, ref } from "vue";
import { listRoutines } from "@/services/modules/routines";

const props = defineProps({
  modelValue: { type: Object, required: true },
});
const emit = defineEmits(["update:modelValue"]);

const routines = ref([]);
const routinesLoading = ref(false);
const routinesError = ref("");

const selected = computed(() => routines.value.find((r) => r.id === props.modelValue.routine_id));

function emitOptionalInt(key, raw, min) {
  if (raw === "" || raw === null) {
    const next = { ...props.modelValue };
    delete next[key];
    emit("update:modelValue", next);
    return;
  }
  const parsed = parseInt(raw, 10);
  if (Number.isNaN(parsed)) return;
  emit("update:modelValue", { ...props.modelValue, [key]: Math.max(min, parsed) });
}

onMounted(async () => {
  routinesLoading.value = true;
  try {
    // The list endpoint caps limit at 200.
    const res = await listRoutines({ limit: 200 });
    routines.value = res.items ?? [];
  } catch (err) {
    routinesError.value = err.message || String(err);
  } finally {
    routinesLoading.value = false;
  }
});
</script>
