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
        {{ review.effect("visitors", "is_member", targets.nameOf(target) || null) }}
      </p>
    </div>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";

import AppDialog from "@/components/common/AppDialog.vue";
import IdentityTargetPicker from "@/components/identity/IdentityTargetPicker.vue";
import { useIdentityReviewStore } from "@/stores/identityReview";
import { useIdentityTargetsStore } from "@/stores/identityTargets";

const props = defineProps<{ modelValue: boolean; count: number; saving?: boolean }>();
defineEmits<{ "update:modelValue": [value: boolean]; submit: [identityId: string | null] }>();

const review = useIdentityReviewStore();
const targets = useIdentityTargetsStore();
const target = ref<string | null>(null);
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      target.value = null;
      void review.load();
    }
  },
  { immediate: true },
);
</script>
