<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <div class="text-subtitle-1 font-weight-bold">Reports</div>
      <v-spacer />
      <!-- Period selector (skill pattern: individual v-btn, no v-btn-toggle) -->
      <div class="d-flex ga-2">
        <v-btn
          v-for="opt in periodOptions"
          :key="opt.value"
          size="small"
          :variant="period === opt.value ? 'flat' : 'outlined'"
          :color="period === opt.value ? 'primary' : undefined"
          @click="period = opt.value"
        >{{ opt.label }}</v-btn>
      </div>
    </div>

    <!-- Daily report view -->
    <template v-if="period === 'day'">
      <DailyReportsView />
    </template>

    <!-- Weekly report view -->
    <template v-if="period === 'week'">
      <WeeklyReportView />
    </template>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRoute } from "vue-router";
import DailyReportsView from "@/views/admin/DailyReportsView.vue";
import WeeklyReportView from "@/views/medical/WeeklyReportView.vue";

const route = useRoute();

const periodOptions = [
  { value: "day",  label: "Daily"  },
  { value: "week", label: "Weekly" },
];

const period = ref(route.query.period === "week" ? "week" : "day");
</script>
