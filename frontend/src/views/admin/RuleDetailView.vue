<template>
  <div v-if="rule">
    <div class="d-flex align-center mb-5">
      <v-btn icon="mdi-arrow-left" variant="text" to="/admin/rules" />
      <div class="ml-2">
        <div class="text-overline text-medium-emphasis">Rule</div>
        <div class="d-flex align-center">
          <h2 class="text-h4 font-weight-bold tracking-tight">{{ rule.name }}</h2>
          <v-chip :color="rule.enabled ? 'success' : 'grey'" size="small" class="ml-3">
            {{ rule.enabled ? "Active" : "Disabled" }}
          </v-chip>
        </div>
      </div>
      <v-spacer />
      <v-btn variant="text" prepend-icon="mdi-download" :loading="exporting" @click="exportRule">
        Export
      </v-btn>
      <v-btn
        color="primary"
        variant="flat"
        prepend-icon="mdi-play"
        :loading="executing"
        @click="executeRule"
      >
        Test Run
      </v-btn>
    </div>

    <v-tabs v-model="tab" color="primary" class="mb-2">
      <v-tab value="settings">Settings</v-tab>
      <v-tab value="pipeline">Pipeline</v-tab>
      <v-tab value="contexts">Contexts</v-tab>
      <v-tab value="dependencies">Dependencies</v-tab>
      <v-tab value="executions">Executions</v-tab>
    </v-tabs>

    <v-window v-model="tab" class="mt-4">
      <v-window-item value="settings">
        <RuleSettingsForm
          v-model:form="form"
          :trigger-types="TRIGGER_TYPES"
          :sensor-items="sensorItems"
          @save="saveSettings"
        />
      </v-window-item>

      <v-window-item value="pipeline">
        <v-card>
          <v-card-text>
            <PipelineCanvas :rule-id="ruleId" @updated="loadRule" />
          </v-card-text>
        </v-card>
      </v-window-item>

      <v-window-item value="contexts">
        <RuleContextsPanel
          :rule-id="ruleId"
          :contexts="rule.contexts"
          :room-names="roomNames"
          :person-ids="personIds"
          @changed="loadRule"
        />
      </v-window-item>

      <v-window-item value="dependencies">
        <RuleDependenciesPanel
          :rule-id="ruleId"
          :dependencies="rule.dependencies"
          :other-rule-items="otherRuleItems"
          :rule-name-by-id="ruleNameById"
          @changed="loadRule"
        />
      </v-window-item>

      <v-window-item value="executions">
        <RuleExecutionsPanel
          :rule-id="ruleId"
          :executions="executions"
          :exec-loading="execLoading"
          :exec-headers="execHeaders"
          :format-date="formatDate"
          :open-execution="openExecution"
        />
      </v-window-item>
    </v-window>
  </div>
  <div v-else class="text-center py-8">
    <v-progress-circular indeterminate />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import PipelineCanvas from "../../components/pipeline/PipelineCanvas.vue";
import RuleSettingsForm from "../../components/rules/RuleSettingsForm.vue";
import RuleContextsPanel from "../../components/rules/RuleContextsPanel.vue";
import RuleDependenciesPanel from "../../components/rules/RuleDependenciesPanel.vue";
import RuleExecutionsPanel from "../../components/rules/RuleExecutionsPanel.vue";
import { useRuleDetail, TRIGGER_TYPES } from "../../composables/useRuleDetail.js";
import { useRuleExecutions } from "../../composables/useRuleExecutions.js";

const route = useRoute();
const router = useRouter();
const ruleId = computed(() => Number(route.params.id));

const tab = ref(route.query.tab === "liverun" ? "executions" : route.query.tab || "settings");

const {
  rule,
  form,
  executing,
  exporting,
  sensorItems,
  roomNames,
  personIds,
  otherRuleItems,
  ruleNameById,
  loadRule,
  loadTelegramDefaults,
  loadReferenceData,
  saveSettings,
  executeRule,
  exportRule,
} = useRuleDetail(ruleId, router);

const { executions, execLoading, execHeaders, formatDate, openExecution } = useRuleExecutions(
  ruleId,
  tab,
  router,
);

onMounted(async () => {
  if (route.query.tab === "liverun") {
    await router.replace({
      query: { ...route.query, tab: "executions" },
    });
  }
  await loadTelegramDefaults(); // must resolve before loadRule so the IIFE sees the defaults
  loadRule();
  loadReferenceData();
});
</script>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}

.cc-code {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}
</style>
