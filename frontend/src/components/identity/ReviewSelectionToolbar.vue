<template>
  <div class="d-flex align-center flex-wrap ga-3" data-test="selection-toolbar">
    <v-btn
      size="small"
      :variant="active ? 'flat' : 'outlined'"
      :color="active ? 'primary' : undefined"
      prepend-icon="mdi-checkbox-multiple-marked-outline"
      data-test="select-mode"
      @click="$emit('update:active', !active)"
    >
      {{ active ? "Done selecting" : "Select several" }}
    </v-btn>
    <template v-if="active">
      <v-btn
        v-if="selectableCount > 0"
        size="small"
        variant="text"
        data-test="select-all"
        @click="$emit('select-all')"
      >
        Select all {{ selectableCount }}
      </v-btn>
      <v-chip size="small" variant="tonal" data-test="selection-count">
        {{ selectedCount }} selected
      </v-chip>
      <v-btn
        v-if="selectedCount > 0"
        size="small"
        variant="text"
        data-test="clear-selection"
        @click="$emit('clear')"
      >
        Clear
      </v-btn>
      <slot />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * The selection mode every identity review queue uses for a decision about several subjects.
 *
 * The surface owns the selection and passes its counts; this bar owns the controls and their
 * words, so "Select several", "Select all", the count, and "Clear" read the same everywhere. The
 * decision buttons go in the default slot and should open a confirm that states the server's
 * effect before one batch call.
 */
defineProps<{ active: boolean; selectableCount: number; selectedCount: number }>();
defineEmits<{ "update:active": [value: boolean]; "select-all": []; clear: [] }>();
</script>
