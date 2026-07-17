<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <span class="text-subtitle-1">Recent executions</span>
      <v-spacer />
      <v-btn
        size="small"
        variant="tonal"
        prepend-icon="mdi-sitemap-outline"
        :to="{ name: 'admin-executions', query: { tab: 'history', rule_id: ruleId } }"
      >
        View all
      </v-btn>
    </v-card-title>
    <v-data-table
      :headers="execHeaders"
      :items="executions"
      :loading="execLoading"
      item-value="id"
      hover
      @click:row="(_, { item }) => openExecution(item)"
    >
      <template #item.status="{ item }">
        <v-chip :color="statusColor(item.status)" size="small">
          {{ item.status }}
        </v-chip>
      </template>
      <template #item.started_at="{ item }">
        {{ formatDate(item.started_at) }}
      </template>
      <template #item.completed_at="{ item }">
        {{ item.completed_at ? formatDate(item.completed_at) : "-" }}
      </template>
      <template #item._duration="{ item }">
        {{ formatDuration(item.started_at, item.completed_at) }}
      </template>
    </v-data-table>
  </v-card>
</template>

<script setup>
import { toRef } from "vue";
import { useRouter } from "vue-router";
import { useRuleExecutions, statusColor, formatDuration } from "@/composables/useRuleExecutions.js";

const props = defineProps({
  ruleId: { type: Number, required: true },
  tab: { type: String, required: true },
});

const router = useRouter();
const ruleId = toRef(props, "ruleId");
const { executions, execLoading, execHeaders, formatDate, openExecution } = useRuleExecutions(
  ruleId,
  () => props.tab,
  router,
);
</script>
