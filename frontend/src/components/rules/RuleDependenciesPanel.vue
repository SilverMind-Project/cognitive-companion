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
            <v-chip size="x-small" :color="dep.require_success ? 'success' : 'warning'" class="ml-2">
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

  <v-dialog v-model="depDialog" max-width="500">
    <v-card>
      <v-card-title>Add Dependency</v-card-title>
      <v-card-text>
        <v-autocomplete
          v-model="depForm.parent_rule_id"
          :items="otherRuleItems"
          item-title="_label"
          item-value="id"
          label="Parent Rule"
          variant="outlined"
          class="mb-3"
        />
        <v-text-field
          v-model.number="depForm.lookback_minutes"
          label="Lookback (min)"
          type="number"
          variant="outlined"
        />
        <v-switch v-model="depForm.require_success" label="Require Success" color="primary" />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="depDialog = false">Cancel</v-btn>
        <v-btn color="primary" @click="addDep">Add</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { toRef } from "vue";
import { useRuleDependencies } from "@/composables/useRuleDependencies.js";

const props = defineProps({
  ruleId: { type: Number, required: true },
  dependencies: { type: Array, default: () => [] },
  otherRuleItems: { type: Array, required: true },
  ruleNameById: { type: Function, required: true },
});
const emit = defineEmits(["changed"]);

const ruleId = toRef(props, "ruleId");
const { depDialog, depForm, addDep, deleteDep } = useRuleDependencies(ruleId, {
  onChanged: () => emit("changed"),
});
</script>
