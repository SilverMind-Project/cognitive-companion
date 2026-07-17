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
import { statusColor, formatDuration } from "@/composables/useRuleExecutions.js";

defineProps({
  ruleId: { type: Number, required: true },
  executions: { type: Array, required: true },
  execLoading: { type: Boolean, required: true },
  execHeaders: { type: Array, required: true },
  formatDate: { type: Function, required: true },
  openExecution: { type: Function, required: true },
});
</script>
