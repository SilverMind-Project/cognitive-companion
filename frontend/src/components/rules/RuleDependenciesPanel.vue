<template>
  <v-card>
    <v-card-text>
      <div class="d-flex align-center mb-3">
        <h4 class="text-subtitle-1">Rule Dependencies</h4>
        <v-spacer />
        <v-btn
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-plus"
          @click="depDialog = true"
        >
          Add Dependency
        </v-btn>
      </div>
      <v-list v-if="dependencies?.length">
        <v-list-item v-for="dep in dependencies" :key="dep.id">
          <v-list-item-title>
            {{ ruleNameById(dep.parent_rule_id) }} (Rule #{{ dep.parent_rule_id }}) &middot;
            lookback {{ dep.lookback_minutes }}min
            <v-chip
              size="x-small"
              :color="dep.require_success ? 'success' : 'warning'"
              class="ml-2"
            >
              {{ dep.require_success ? "require success" : "require no success" }}
            </v-chip>
          </v-list-item-title>
          <template #append>
            <v-btn
              icon="mdi-delete"
              size="x-small"
              variant="text"
              color="error"
              @click="deleteDep(dep.id)"
            />
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="text-center text-grey py-4">No dependencies</div>
    </v-card-text>
  </v-card>

  <!-- Add dependency: small form -->
  <AppDialog
    v-model="depDialog"
    size="sm"
    persistent
    icon="mdi-source-branch"
    label="Rule"
    title="Add Dependency"
    confirm-label="Add"
    :confirm-disabled="!depForm.parent_rule_id"
    @confirm="addDep"
  >
    <div class="px-6 py-5">
      <v-autocomplete
        v-model="depForm.parent_rule_id"
        :items="otherRuleItems"
        item-title="_label"
        item-value="id"
        label="Parent Rule"
        variant="outlined"
        class="mb-3"
      />
      <v-row dense align="center">
        <v-col cols="12" sm="6">
          <v-text-field
            v-model.number="depForm.lookback_minutes"
            label="Lookback (min)"
            type="number"
            variant="outlined"
          />
        </v-col>
        <v-col cols="12" sm="6">
          <v-switch v-model="depForm.require_success" label="Require Success" hide-details />
        </v-col>
      </v-row>
    </div>
  </AppDialog>
</template>

<script setup>
import { toRef } from "vue";
import { useRuleDependencies } from "@/composables/useRuleDependencies.js";
import { useNotify } from "@/composables/useNotify.js";
import AppDialog from "@/components/common/AppDialog.vue";

const props = defineProps({
  ruleId: { type: Number, required: true },
  dependencies: { type: Array, default: () => [] },
  otherRuleItems: { type: Array, required: true },
  ruleNameById: { type: Function, required: true },
});
const emit = defineEmits(["changed"]);

const ruleId = toRef(props, "ruleId");
const { notify } = useNotify();
const { depDialog, depForm, addDep, deleteDep } = useRuleDependencies(ruleId, {
  onChanged: () => emit("changed"),
  notify,
});
</script>
