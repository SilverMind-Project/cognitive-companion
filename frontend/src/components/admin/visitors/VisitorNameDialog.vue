<template>
  <AppDialog
    :model-value="modelValue"
    size="sm"
    icon="mdi-account-plus-outline"
    label="Visitor"
    title="Name this visitor"
    confirm-label="Name visitor"
    :confirm-loading="saving"
    :confirm-disabled="!nameValid || !personIdValid"
    @update:model-value="$emit('update:modelValue', $event)"
    @confirm="onConfirm"
  >
    <div class="pa-4">
      <p class="text-body-2 text-medium-emphasis mb-4">
        Naming creates a household member and lets this visitor be recognized on future visits.
      </p>
      <v-text-field
        v-model="name"
        label="Name"
        variant="outlined"
        autofocus
        class="mb-3"
        :error-messages="nameError"
        @update:model-value="onNameChange"
      />
      <v-text-field
        v-model="personId"
        label="Person ID"
        variant="outlined"
        hint="Lowercase letters, digits, and hyphens only. Auto-suggested from the name."
        persistent-hint
        :error-messages="personIdError"
        @update:model-value="personIdTouched = true"
      />
    </div>
  </AppDialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import AppDialog from "@/components/common/AppDialog.vue";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  saving: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "submit"]);

const name = ref("");
const personId = ref("");
const personIdTouched = ref(false);

const _SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

function slugify(value) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function onNameChange(value) {
  if (!personIdTouched.value) personId.value = slugify(value ?? "");
}

const nameValid = computed(() => name.value.trim().length > 0);
const nameError = computed(() => (nameValid.value ? [] : ["Name is required"]));

const personIdValid = computed(() => _SLUG_RE.test(personId.value));
const personIdError = computed(() =>
  personIdValid.value ? [] : ["Lowercase letters, digits, and hyphens only (e.g. nurse-priya)"],
);

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      name.value = "";
      personId.value = "";
      personIdTouched.value = false;
    }
  },
);

function onConfirm() {
  if (!nameValid.value || !personIdValid.value) return;
  emit("submit", { name: name.value.trim(), personId: personId.value });
}
</script>
