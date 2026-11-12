<template>
  <AppDialog
    :model-value="modelValue"
    size="sm"
    persistent
    icon="mdi-delete-outline"
    label="Delete"
    :title="title"
    confirm-label="Delete permanently"
    confirm-color="error"
    :confirm-loading="loading"
    @update:model-value="$emit('update:modelValue', $event)"
    @confirm="$emit('delete')"
  >
    <div class="px-6 py-5 text-body-2">
      Deleting removes this {{ noun }} permanently. Archiving keeps it but takes it out of use, and
      it can be restored later.
    </div>
    <template #footerActions>
      <v-btn
        variant="tonal"
        color="warning"
        prepend-icon="mdi-archive-outline"
        :disabled="loading"
        @click="$emit('archive')"
      >
        Archive instead
      </v-btn>
    </template>
  </AppDialog>
</template>

<script setup>
/**
 * The review step before deleting content that can also be archived (info cards, quizzes,
 * knowledge documents). Deletion is permanent, so it is the explicit red action; archiving is
 * offered beside it as the reversible alternative. The parent performs whichever is emitted.
 */
import { computed } from "vue";
import AppDialog from "./AppDialog.vue";

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  /** What is being deleted, in lower case: "info card", "quiz", "document". */
  noun: { type: String, required: true },
  /** The item's title, when it has one. */
  name: { type: String, default: "" },
  loading: { type: Boolean, default: false },
});

defineEmits(["update:modelValue", "archive", "delete"]);

const title = computed(() =>
  props.name ? `Delete "${props.name}"?` : `Delete this ${props.noun}?`,
);
</script>
