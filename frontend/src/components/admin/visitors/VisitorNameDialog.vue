<template>
  <AppDialog
    :model-value="modelValue"
    size="sm"
    icon="mdi-account-plus-outline"
    label="Visitor"
    title="Name this visitor"
    confirm-label="Name visitor"
    :confirm-loading="saving"
    :confirm-disabled="!nameValid || !personIdValid || !!existingById"
    @update:model-value="$emit('update:modelValue', $event)"
    @confirm="onConfirm"
  >
    <div class="pa-4">
      <p class="text-body-2 text-medium-emphasis mb-4">
        Naming creates a new household member from these faces and lets them be recognized on future
        visits. If these are faces of someone already enrolled, mark them as theirs instead.
      </p>
      <v-alert
        v-if="existing"
        type="warning"
        variant="tonal"
        density="compact"
        class="mb-4"
        data-test="already-enrolled"
      >
        {{ existing.display_name }} is already in the household. Naming would create a second
        identity for the same person.
        <template #append>
          <v-btn size="small" variant="text" @click="$emit('attribute', existing.identity_id)">
            Mark as theirs
          </v-btn>
        </template>
      </v-alert>
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
import { useIdentityTargetsStore } from "@/stores/identityTargets";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  saving: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "submit", "attribute"]);

const targets = useIdentityTargetsStore();

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

// A member with this id already exists: naming is refused, so offer attribution instead.
const existingById = computed(() => targets.byId.get(personId.value) ?? null);
// Same id, or same display name ignoring case: very likely the same person.
const existing = computed(
  () =>
    existingById.value ??
    targets.targets.find(
      (t) => name.value.trim() && t.display_name.toLowerCase() === name.value.trim().toLowerCase(),
    ) ??
    null,
);

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
      void targets.load();
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
