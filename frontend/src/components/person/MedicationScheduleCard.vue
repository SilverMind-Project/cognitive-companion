<template>
  <v-card class="glass-card">
    <v-card-text class="pa-5">
      <div class="d-flex align-center mb-1">
        <span class="text-subtitle-1 font-weight-medium">Medication schedule</span>
        <v-spacer />
        <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openAdd">
          Add dose
        </v-btn>
      </div>
      <p class="text-body-2 text-medium-emphasis mb-4">
        Daily reports compare logged doses with this schedule.
      </p>

      <v-alert v-if="state.error" type="error" variant="tonal">{{ state.error }}</v-alert>

      <v-skeleton-loader
        v-else-if="state.loading && !state.entries.length"
        type="list-item-two-line"
      />

      <v-alert v-else-if="!state.entries.length" type="info" variant="tonal">
        No doses scheduled. Add one to track adherence.
      </v-alert>

      <v-list v-else lines="two" class="bg-transparent pa-0">
        <v-list-item v-for="entry in state.entries" :key="entry.id" class="px-0">
          <v-list-item-title class="font-weight-medium">{{ entry.label }}</v-list-item-title>
          <v-list-item-subtitle>
            {{ formatWallClock(entry.dose_time) }} · {{ formatDays(entry.days_of_week) }}
          </v-list-item-subtitle>
          <template #append>
            <v-btn
              icon="mdi-pencil-outline"
              variant="text"
              size="small"
              :aria-label="`Edit ${entry.label}`"
              @click="openEdit(entry)"
            />
            <v-btn
              icon="mdi-delete-outline"
              variant="text"
              size="small"
              :aria-label="`Remove ${entry.label}`"
              @click="remove(entry)"
            />
          </template>
        </v-list-item>
      </v-list>
    </v-card-text>

    <AppDialog
      v-model="dialogOpen"
      icon="mdi-pill"
      label="Medication"
      :title="editingId ? 'Edit dose' : 'Add dose'"
      hint="Changes apply from the next dose."
      :confirm-loading="state.saving"
      :confirm-disabled="!formValid"
      @confirm="save"
    >
      <v-text-field v-model="form.label" label="Name" counter="128" maxlength="128" class="mb-2" />
      <v-text-field v-model="form.dose_time" label="Time" type="time" class="mb-2" />
      <div class="text-body-2 text-medium-emphasis mb-1">Days</div>
      <v-chip-group v-model="form.days_of_week" multiple column>
        <v-chip
          v-for="(day, index) in WEEKDAYS"
          :key="day"
          :value="index"
          filter
          variant="tonal"
          color="primary"
        >
          {{ day }}
        </v-chip>
      </v-chip-group>
    </AppDialog>

    <v-dialog v-model="confirmDialog" max-width="420" persistent>
      <v-card>
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup>
import { computed, reactive, ref, toRef } from "vue";
import AppDialog from "@/components/common/AppDialog.vue";
import { useConfirm } from "@/composables/useConfirm.js";
import { useMedicationSchedule } from "@/composables/useMedicationSchedule.js";
import { useNotify } from "@/composables/useNotify.js";
import { formatWallClock } from "@/services/timezone.js";
import { WEEKDAYS, formatDays } from "./medicationDays.js";

const props = defineProps({
  personId: { type: String, required: true },
});

const { notify } = useNotify();
const { state, actions } = useMedicationSchedule(toRef(props, "personId"), { notify });
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  showConfirm,
  onConfirm,
  onCancel,
} = useConfirm();

const EVERY_DAY = [0, 1, 2, 3, 4, 5, 6];
const dialogOpen = ref(false);
const editingId = ref(null);
const form = reactive({ label: "", dose_time: "08:00", days_of_week: [...EVERY_DAY] });

const formValid = computed(
  () => form.label.trim() && form.dose_time && form.days_of_week.length > 0,
);

function open(entryId, values) {
  editingId.value = entryId;
  Object.assign(form, values);
  dialogOpen.value = true;
}

const openAdd = () => open(null, { label: "", dose_time: "08:00", days_of_week: [...EVERY_DAY] });

const openEdit = (entry) =>
  open(entry.id, {
    label: entry.label,
    dose_time: entry.dose_time,
    days_of_week: [...entry.days_of_week],
  });

async function save() {
  const dose = { ...form, label: form.label.trim() };
  const saved = editingId.value
    ? await actions.updateDose(editingId.value, dose)
    : await actions.addDose(dose);
  if (saved) dialogOpen.value = false;
}

async function remove(entry) {
  if (await showConfirm("Remove this dose?", `${entry.label} stops after its next dose.`)) {
    await actions.removeDose(entry.id);
  }
}
</script>
