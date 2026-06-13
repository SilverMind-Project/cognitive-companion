<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 report-header" :class="embedded ? 'mb-4' : 'mb-6'">
      <div>
        <h2 :class="embedded ? 'text-h6' : 'text-h4'" class="font-weight-bold tracking-tight">
          Weekly Report
        </h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Trend report for clinical review. Print or save as PDF.
        </div>
      </div>
      <v-spacer />
      <v-btn variant="flat" color="primary" prepend-icon="mdi-printer" class="print-hide" @click="window.print()">
        Print / Save PDF
      </v-btn>
    </div>

    <v-alert v-if="error" type="error" class="mb-4 print-hide" closable>{{ error }}</v-alert>

    <!-- Picker -->
    <v-card variant="flat" class="mb-4 px-4 py-2 print-hide" border>
      <v-row dense align="center">
        <v-col cols="12" sm="4">
          <v-text-field
            v-model="personId"
            label="Person ID"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="12" sm="4">
          <v-text-field
            v-model="weekStart"
            label="Week start (YYYY-MM-DD)"
            variant="outlined"
            density="compact"
            type="date"
            hide-details
          />
        </v-col>
        <v-col cols="12" sm="2">
          <v-btn variant="tonal" color="primary" :loading="loading" block @click="fetch">
            Generate
          </v-btn>
        </v-col>
      </v-row>
    </v-card>

    <!-- Report sheet -->
    <v-card v-if="report" class="glass-card report-sheet">
      <div class="pa-6">
        <h3 class="text-h5 mb-1">Weekly Dementia Signal Report</h3>
        <div class="text-body-1 text-medium-emphasis mb-4">
          Person: {{ report.person_id }} &middot;
          Week of {{ report.week?.start?.slice(0, 10) || '' }} to {{ report.week?.end?.slice(0, 10) || '' }}
        </div>

        <v-divider class="mb-4" />

        <!-- Signal counts -->
        <div class="text-h6 mb-3">Signal Counts</div>
        <div v-if="Object.keys(report.signal_counts || {}).length === 0" class="text-medium-emphasis mb-3">
          No signals recorded this week.
        </div>
        <svg v-else :viewBox="`0 0 ${reportChartWidth} 140`" width="100%" height="140" class="mb-4">
          <g v-for="(bar, i) in reportBars" :key="bar.kind">
            <rect
              :x="i * rbarWidth + 4"
              :y="140 - bar.height - 20"
              :width="rbarWidth - 8"
              :height="bar.height"
              rx="3"
              :fill="bar.color"
            />
            <text :x="i * rbarWidth + rbarWidth / 2" :y="140 - bar.height - 24" text-anchor="middle" font-size="9" fill="var(--cc-chart-axis-label)">{{ bar.count }}</text>
            <text :x="i * rbarWidth + (rbarWidth > 60 ? rbarWidth / 2 : rbarWidth)" :y="135" text-anchor="middle" font-size="8" fill="var(--cc-chart-axis-label)" :transform="rbarWidth < 50 ? `rotate(-45 ${i * rbarWidth + 20} 130)` : ''">{{ bar.kind.replace(/_/g, ' ') }}</text>
          </g>
        </svg>

        <v-divider class="mb-4" />

        <!-- Dwell totals -->
        <div class="text-h6 mb-3">Dwell by Room</div>
        <div v-if="(report.dwell_by_room || []).length === 0" class="text-medium-emphasis mb-3">No dwell data.</div>
        <div v-for="d in (report.dwell_by_room || [])" :key="d.room_id" class="d-flex align-center ga-2 mb-1">
          <span class="text-body-2" style="min-width: 120px;">{{ d.room_name }}</span>
          <v-progress-linear :model-value="dwellPct(d)" height="10" rounded color="primary" style="flex: 1;" />
          <span class="text-caption text-medium-emphasis" style="min-width: 60px;">{{ d.minutes?.toFixed(0) || 0 }} m</span>
        </div>

        <v-divider class="mb-4" />

        <!-- Highlights -->
        <div class="text-h6 mb-3">Highlights</div>
        <div v-if="(report.highlights || []).length === 0" class="text-medium-emphasis mb-3">No signal highlights.</div>
        <div v-for="h in (report.highlights || [])" :key="h.fired_at" class="d-flex align-center ga-2 mb-1 text-body-2">
          <v-chip size="x-small" :color="h.severity === 'emergency' ? 'error' : 'warning'" variant="tonal">
            {{ (h.kind || '').replace(/_/g, ' ') }}
          </v-chip>
          <span class="text-caption text-medium-emphasis">{{ (h.fired_at || '').slice(0, 16) }}</span>
        </div>

        <div class="text-caption text-medium-emphasis mt-6 pt-4 report-footer">
          Generated {{ new Date().toISOString().slice(0, 10) }} &middot;
          Cognitive Companion &middot; For clinical review only &middot; Not a diagnosis
        </div>
      </div>
    </v-card>

    <div v-else-if="!loading" class="pa-4 text-center text-medium-emphasis">
      Select a person and week, then click Generate to view the report.
    </div>
  </div>
</template>

<script>
import { ref, computed } from "vue";
import { cts } from "@/services/cts.js";

// DS data-viz palette in salience order (mirrors --cc-chart-1..6). Hardcoded so
// the print sheet renders the brand colours even without computed-style access.
const PALETTE = ["#3F6B52", "#C8704F", "#4E7A8C", "#C98A2E", "#82B292", "#B3A286"];

export default {
  name: "WeeklyReportView",

  props: {
    embedded: { type: Boolean, default: false },
  },

  setup() {
    const personId = ref("");
    const weekStart = ref(new Date(Date.now() - 7 * 86400000 * (new Date().getDay() || 7) + 86400000).toISOString().slice(0, 10));
    const loading = ref(false);
    const error = ref("");
    const report = ref(null);
    const reportChartWidth = 600;

    const reportBars = computed(() => {
      const counts = report.value?.signal_counts || {};
      return Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .map(([kind, count], i) => ({
          kind,
          count,
          color: PALETTE[i % PALETTE.length],
          height: Math.max((count / Math.max(...Object.values(counts), 1)) * 100, 4),
        }));
    });

    const rbarWidth = computed(() =>
      Math.min(reportChartWidth / Math.max(reportBars.value.length, 1), 100)
    );

    function dwellPct(d) {
      const max = Math.max(...(report.value?.dwell_by_room || []).map((x) => x.minutes || 0), 1);
      return ((d.minutes || 0) / max) * 100;
    }

    async function loadReport() {
      if (!personId.value || !weekStart.value) return;
      loading.value = true;
      error.value = "";
      try {
        report.value = await cts.getWeeklyReport(personId.value, weekStart.value);
      } catch (e) {
        error.value = e.message || "Failed to generate report";
      } finally {
        loading.value = false;
      }
    }

    return { personId, weekStart, loading, error, report, reportBars, rbarWidth, reportChartWidth, dwellPct, fetch: loadReport, window };
  },
};
</script>

<style scoped>
@media print {
  .print-hide, .v-toolbar, nav, .v-navigation-drawer { display: none !important; }
  .report-sheet { box-shadow: none !important; border: none !important; }
  body { font-size: 11pt; }
  .report-header { margin-top: 0 !important; }
}
.report-footer { border-top: 1px solid var(--cc-divider); }
</style>
