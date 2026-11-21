<template>
  <v-card class="glass-card" data-test="member-height-profile-card">
    <div class="d-flex align-center flex-wrap ga-2 pa-4 pb-2">
      <div class="d-flex align-center ga-2">
        <v-icon size="18">mdi-human-male-height</v-icon>
        <span class="text-subtitle-1 font-weight-bold">Standing Height Profile</span>
      </div>
      <v-chip
        v-if="profile?.source"
        size="x-small"
        variant="tonal"
        :color="profile.source === 'learned' ? 'success' : 'info'"
        data-test="height-source-chip"
      >
        {{ profile.source === "learned" ? "Learned" : "Operator" }}
      </v-chip>
      <v-spacer />
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-refresh"
        :loading="loading"
        :disabled="saving"
        data-test="height-refresh"
        @click="load"
      >
        Refresh
      </v-btn>
    </div>

    <v-card-text>
      <div v-if="loading" class="d-flex justify-center py-4" data-test="height-loading">
        <v-progress-circular indeterminate color="primary" size="24" />
      </div>

      <v-alert
        v-else-if="error"
        type="error"
        variant="tonal"
        density="compact"
        class="mb-3"
        data-test="height-error"
      >
        {{ error }}
        <template #append>
          <v-btn size="small" variant="text" @click="load">Retry</v-btn>
        </template>
      </v-alert>

      <template v-else-if="profile">
        <v-alert
          v-if="!profile.cts_available"
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-3"
          data-test="height-cts-unavailable"
        >
          Camera tracking service is currently unreachable; showing locally saved operator height
          only.
        </v-alert>

        <div v-if="profile.effective_height_m != null" class="mb-4" data-test="height-effective">
          <div class="text-h6 font-weight-semibold">
            {{ formatCm(profile.effective_height_m) }} cm
            <span class="text-body-2 text-medium-emphasis font-weight-regular">
              ({{ profile.effective_height_m.toFixed(2) }} m
              <template v-if="profile.effective_sigma_m != null">
                ± {{ formatCm(profile.effective_sigma_m) }} cm
              </template>
              )
            </span>
          </div>
          <div class="text-caption text-medium-emphasis mt-1" data-test="height-stats">
            <template v-if="profile.source === 'learned'">
              Learned from {{ profile.samples }} standing sample{{
                profile.samples === 1 ? "" : "s"
              }}
              across {{ profile.cameras }} camera{{ profile.cameras === 1 ? "" : "s" }}.
            </template>
            <template v-else>
              Using operator-entered height until enough multi-camera standing observations are
              collected.
            </template>
          </div>
        </div>
        <div v-else class="text-body-2 text-medium-emphasis mb-4" data-test="height-empty">
          No standing height profile yet. Enter an optional standing height below as an initial
          estimate, or let calibrated cameras learn it automatically.
        </div>

        <v-divider class="my-3" />

        <div class="d-flex align-center flex-wrap ga-3">
          <v-text-field
            v-model="heightInput"
            label="Operator height (cm)"
            hint="Optional standing height between 90 and 220 cm"
            persistent-hint
            type="number"
            min="90"
            max="220"
            step="0.5"
            variant="outlined"
            density="compact"
            clearable
            :disabled="saving"
            :error-messages="validationError ? [validationError] : []"
            style="max-width: 240px"
            data-test="height-input"
          />
          <v-btn
            color="primary"
            variant="tonal"
            size="small"
            :loading="saving"
            :disabled="Boolean(validationError)"
            data-test="height-save"
            @click="onSave"
          >
            Save
          </v-btn>
        </div>
      </template>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ApiError } from "@/services/http";
import {
  getPersonHeightProfile,
  updatePerson,
  type PersonHeightProfileOut,
} from "@/services/modules/persons";
import { useNotify } from "@/composables/useNotify.js";

const props = defineProps<{
  personId: string;
}>();

const { notify } = useNotify();

const loading = ref(false);
const saving = ref(false);
const error = ref<string | null>(null);
const profile = ref<PersonHeightProfileOut | null>(null);
const heightInput = ref<string>("");

const parsedHeight = computed<number | null | "invalid">(() => {
  const raw = heightInput.value == null ? "" : String(heightInput.value).trim();
  if (raw === "") return null;
  const num = Number(raw);
  if (!Number.isFinite(num) || num < 90 || num > 220) return "invalid";
  return num;
});

const validationError = computed<string | null>(() => {
  if (parsedHeight.value === "invalid") {
    return "Height must be between 90 and 220 cm.";
  }
  return null;
});

function formatCm(metres: number): string {
  return (metres * 100).toFixed(1);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const res = await getPersonHeightProfile(props.personId);
    profile.value = res;
    heightInput.value = res.operator_height_cm != null ? String(res.operator_height_cm) : "";
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Could not load standing height profile.";
  } finally {
    loading.value = false;
  }
}

async function onSave() {
  if (parsedHeight.value === "invalid") return;
  saving.value = true;
  try {
    await updatePerson(props.personId, { height_cm: parsedHeight.value });
    notify.success(
      parsedHeight.value == null
        ? "Cleared operator height."
        : `Saved operator height (${parsedHeight.value.toFixed(1)} cm).`,
    );
    await load();
  } catch (err) {
    notify.error(err instanceof ApiError ? err.message : "Failed to save operator height.");
  } finally {
    saving.value = false;
  }
}

onMounted(load);
watch(() => props.personId, load);
</script>
