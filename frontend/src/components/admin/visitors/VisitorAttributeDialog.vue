<template>
  <AppDialog
    :model-value="modelValue"
    size="sm"
    icon="mdi-account-check-outline"
    label="Visitors"
    :title="count === 1 ? 'Whose faces are these?' : `Whose faces are these ${count} groups?`"
    confirm-label="Mark as theirs"
    :confirm-loading="saving"
    :confirm-disabled="!target"
    @update:model-value="$emit('update:modelValue', $event)"
    @confirm="$emit('submit', target)"
  >
    <div class="pa-4">
      <IdentityTargetPicker v-model="target" require-enrolled-face class="mb-2" />
      <p class="text-body-2 text-medium-emphasis" data-test="attribute-effect">
        {{ VISITOR_EFFECTS.is_member }}
      </p>
    </div>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";

import AppDialog from "@/components/common/AppDialog.vue";
import IdentityTargetPicker from "@/components/identity/IdentityTargetPicker.vue";
import { VISITOR_EFFECTS } from "@/constants/identityReview";

const props = defineProps<{ modelValue: boolean; count: number; saving?: boolean }>();
defineEmits<{ "update:modelValue": [value: boolean]; submit: [identityId: string | null] }>();

const target = ref<string | null>(null);
watch(
  () => props.modelValue,
  (open) => {
    if (open) target.value = null;
  },
);
</script>
