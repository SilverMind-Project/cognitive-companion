<template>
  <div>
    <v-alert
      v-if="store.forbidden"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-2"
      data-test="targets-forbidden"
    >
      You do not have permission to see the household list.
    </v-alert>
    <v-alert
      v-else-if="store.error"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-2"
      data-test="targets-error"
    >
      {{ store.error }}
      <template #append>
        <v-btn size="small" variant="text" @click="store.load(true)">Retry</v-btn>
      </template>
    </v-alert>
    <v-autocomplete
      :model-value="modelValue"
      :items="items"
      item-title="title"
      item-value="value"
      item-props="props"
      :label="label"
      :loading="store.loading"
      :disabled="disabled"
      :no-data-text="store.loading ? 'Loading household members' : 'No household members'"
      variant="outlined"
      clearable
      data-test="identity-target-picker"
      @update:model-value="$emit('update:modelValue', $event)"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * Pick a household member for an identity decision.
 *
 * The one selector every identity review surface uses, over the shared `identityTargets` store.
 * With `requireEnrolledFace`, members without enrolled face photos are shown but disabled, with
 * the reason, because the decision needs their enrolled face (visitor attribution).
 */
import { computed, onMounted } from "vue";

import { useIdentityTargetsStore } from "@/stores/identityTargets";

const props = withDefaults(
  defineProps<{
    modelValue: string | null;
    label?: string;
    requireEnrolledFace?: boolean;
    disabled?: boolean;
  }>(),
  { label: "Household member", requireEnrolledFace: false, disabled: false },
);
defineEmits<{ "update:modelValue": [value: string | null] }>();

const store = useIdentityTargetsStore();

const items = computed(() =>
  store.targets.map((t) => {
    const unenrolled = props.requireEnrolledFace && t.face_enrolled === false;
    const notes = [t.is_guest ? "Guest" : "", unenrolled ? "No enrolled face photos" : ""];
    return {
      title: t.display_name,
      value: t.identity_id,
      props: { disabled: unenrolled, subtitle: notes.filter(Boolean).join(" · ") || undefined },
    };
  }),
);

onMounted(() => void store.load());
</script>
