<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Knowledge Interactions</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          What the senior asked, the quizzes they took, and the cards they were shown.
        </div>
      </div>
    </div>

    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="queries">Questions Asked</v-tab>
      <v-tab value="sessions">Quiz Sessions</v-tab>
      <v-tab value="deliveries">Info Card Deliveries</v-tab>
      <v-tab value="analytics" data-test="tab-analytics">Tag Analytics</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <v-window-item v-for="tab in LIST_TABS" :key="tab.name" :value="tab.name">
        <v-card variant="tonal" class="pa-2 mb-2">
          <v-row dense align="center">
            <v-col cols="auto">
              <v-text-field
                v-model="state[tab.name].dateFrom"
                label="From"
                type="date"
                density="compact"
                hide-details
                :data-test="`${tab.name}-from`"
              />
            </v-col>
            <v-col cols="auto">
              <v-text-field
                v-model="state[tab.name].dateTo"
                label="To"
                type="date"
                density="compact"
                hide-details
                :data-test="`${tab.name}-to`"
              />
            </v-col>
            <v-col cols="auto">
              <v-btn
                size="small"
                variant="outlined"
                :data-test="`${tab.name}-apply`"
                @click="actions.applyDates(tab.name)"
              >
                Apply
              </v-btn>
            </v-col>
          </v-row>
        </v-card>

        <v-card class="glass-card">
          <v-data-table-server
            v-model:expanded="expandedSessions"
            :headers="tab.headers"
            :items="state[tab.name].items"
            :items-length="state[tab.name].total"
            :items-per-page="state[tab.name].itemsPerPage"
            :page="state[tab.name].page"
            :loading="state[tab.name].loading"
            :show-expand="tab.name === 'sessions'"
            item-value="id"
            @update:options="(opts) => actions.onOptions(tab.name, opts)"
            @update:expanded="onSessionsExpanded"
          >
            <template v-for="key in tab.timeKeys" :key="key" #[`item.${key}`]="{ item }">
              {{ item[key] ? formatDateTime(item[key]) : "-" }}
            </template>
            <template #[`item.query_text`]="{ item }">
              {{ truncate(item.query_text, 80) }}
            </template>
            <template #[`item.latency_ms`]="{ item }">
              {{ formatLatency(item.latency_ms) }}
            </template>
            <template #[`item.channels`]="{ item }">
              {{ (item.channels || []).join(", ") }}
            </template>

            <template #expanded-row="{ columns, item }">
              <td :colspan="columns.length" class="pa-4">
                <v-progress-circular
                  v-if="state.loadingSessionId === item.id"
                  indeterminate
                  size="20"
                />
                <template v-else-if="state.sessionDetails[item.id]">
                  <div
                    v-for="resp in state.sessionDetails[item.id].responses || []"
                    :key="resp.id"
                    class="mb-3"
                    data-test="session-response"
                  >
                    <v-card variant="outlined" class="pa-2">
                      <div><strong>Q:</strong> {{ resp.question_text }}</div>
                      <div>
                        <strong>A:</strong>
                        {{ resp.chosen_choice_text || resp.open_ended_text || "-" }}
                      </div>
                      <div class="mt-1">
                        <v-chip :color="answerChip(resp).color" size="x-small">
                          {{ answerChip(resp).label }}
                        </v-chip>
                        <span class="ml-2 text-caption text-medium-emphasis">
                          {{ resp.channel }} · {{ formatLatency(resp.latency_ms) }}
                        </span>
                      </div>
                    </v-card>
                  </div>
                  <div
                    v-if="!state.sessionDetails[item.id].responses?.length"
                    class="text-medium-emphasis"
                  >
                    No answers recorded.
                  </div>
                </template>
              </td>
            </template>

            <template #no-data>
              <div class="pa-6 text-center text-medium-emphasis">{{ tab.empty }}</div>
            </template>
          </v-data-table-server>
        </v-card>
      </v-window-item>

      <v-window-item value="analytics">
        <v-card class="glass-card pa-4 mb-4">
          <div class="text-subtitle-1 mb-1">Answers correct by topic</div>
          <div class="text-caption text-medium-emphasis mb-3">
            Share of graded quiz answers that matched, per tag, across completed sessions (archived
            quizzes included). A topic without graded answers is not shown. Document and quiz counts
            below leave out archived items.
          </div>
          <div style="height: 260px">
            <CcBarChart
              :categories="scoredTags.map((t) => t.tag)"
              :series="[{ name: 'Correct', values: scoredTags.map((t) => t.avg_quiz_score_pct) }]"
              unit="%"
              :loading="state.analytics.loading"
              :error="state.analytics.error"
            >
              <template #empty>
                <div class="pa-6 text-center text-medium-emphasis">No graded quiz answers yet.</div>
              </template>
            </CcBarChart>
          </div>
        </v-card>
        <v-card class="glass-card">
          <v-data-table
            :headers="ANALYTICS_HEADERS"
            :items="state.analytics.tags"
            :loading="state.analytics.loading"
            item-value="tag"
            data-test="analytics-table"
          >
            <template #[`item.avg_quiz_score_pct`]="{ item }">
              {{ item.avg_quiz_score_pct == null ? "-" : `${item.avg_quiz_score_pct}%` }}
            </template>
            <template #no-data>
              <div class="pa-6 text-center text-medium-emphasis">
                Tag documents and quizzes to see them here.
              </div>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>
    </v-window>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useNotify } from "@/composables/useNotify.js";
import { useKnowledgeInteractions } from "@/composables/useKnowledgeInteractions.js";
import { DATETIME_COLUMN_WIDTH, formatDateTime } from "@/services/timezone.js";
import CcBarChart from "@/components/charts/CcBarChart.vue";

const { notify } = useNotify();
const { state, actions } = useKnowledgeInteractions({ notify });

const activeTab = ref("queries");
const expandedSessions = ref([]);

const time = (title, key) => ({ title, key, sortable: false, width: DATETIME_COLUMN_WIDTH });

const LIST_TABS = [
  {
    name: "queries",
    timeKeys: ["asked_at"],
    empty: "Questions the senior asks the companion will appear here.",
    headers: [
      time("Asked At", "asked_at"),
      { title: "Resident", key: "senior_id", sortable: false },
      { title: "Question", key: "query_text", sortable: false },
      { title: "Answered From", key: "answered_via", sortable: false },
      { title: "Channel", key: "channel", sortable: false },
      { title: "Response Time", key: "latency_ms", sortable: false },
    ],
  },
  {
    name: "sessions",
    timeKeys: ["started_at", "completed_at"],
    empty: "Quiz sessions will appear here once a rule delivers a quiz.",
    headers: [
      time("Started At", "started_at"),
      { title: "Quiz ID", key: "quiz_id", sortable: false },
      { title: "Resident", key: "senior_id", sortable: false },
      { title: "Status", key: "status", sortable: false },
      { title: "Answers", key: "response_count", sortable: false, width: 90 },
      time("Ended At", "completed_at"),
    ],
  },
  {
    name: "deliveries",
    timeKeys: ["delivered_at", "viewed_at", "dismissed_at"],
    empty: "Info cards will appear here once a rule delivers one.",
    headers: [
      time("Delivered At", "delivered_at"),
      { title: "Info Card ID", key: "info_card_id", sortable: false },
      { title: "Channels", key: "channels", sortable: false },
      time("Viewed At", "viewed_at"),
      time("Dismissed At", "dismissed_at"),
      { title: "Dismissed By", key: "dismissed_by", sortable: false },
    ],
  },
];

const ANALYTICS_HEADERS = [
  { title: "Tag", key: "tag" },
  { title: "Documents", key: "document_count" },
  { title: "Quizzes", key: "quiz_count" },
  { title: "Answers Correct", key: "avg_quiz_score_pct" },
];

const scoredTags = computed(() => state.analytics.tags.filter((t) => t.avg_quiz_score_pct != null));

function truncate(text, len) {
  if (!text) return "";
  return text.length > len ? text.slice(0, len) + "..." : text;
}

function formatLatency(ms) {
  if (ms == null) return "-";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

// Caregiver view: is_correct is recorded even in gentle mode. Null means the answer was not
// graded (an open answer with no expected answer, or grading failed), not "wrong".
function answerChip(resp) {
  if (resp.is_correct === true) return { label: "Correct", color: "success" };
  if (resp.is_correct === false) return { label: "Not correct", color: "warning" };
  return { label: "Not graded", color: "default" };
}

function onSessionsExpanded(ids) {
  for (const id of ids) actions.loadSessionDetail(id);
}

watch(activeTab, (tab) => {
  if (tab === "analytics" && !state.analytics.tags.length) actions.loadTagAnalytics();
});

onMounted(() => {
  for (const tab of LIST_TABS) actions.load(tab.name);
});
</script>
