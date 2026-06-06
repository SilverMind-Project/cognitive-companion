<template>
  <div>
    <TrackingPanelHeader
      title="Reports"
      description="Review daily wellness summaries or generate a weekly clinical trend report."
    >
      <template #actions>
        <div class="d-flex ga-2">
          <v-btn
            v-for="opt in periodOptions"
            :key="opt.value"
            size="small"
            :variant="period === opt.value ? 'flat' : 'outlined'"
            :color="period === opt.value ? 'primary' : undefined"
            @click="period = opt.value"
          >
            {{ opt.label }}
          </v-btn>
        </div>
      </template>
    </TrackingPanelHeader>

    <template v-if="period === 'day'">
      <DailyReportsView embedded />
    </template>

    <template v-if="period === 'week'">
      <WeeklyReportView embedded />
    </template>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRoute } from "vue-router";
import DailyReportsView from "@/views/admin/DailyReportsView.vue";
import WeeklyReportView from "@/views/medical/WeeklyReportView.vue";
import TrackingPanelHeader from "@/components/tracking/TrackingPanelHeader.vue";

const route = useRoute();

const periodOptions = [
  { value: "day",  label: "Daily"  },
  { value: "week", label: "Weekly" },
];

const period = ref(route.query.period === "week" ? "week" : "day");
</script>
