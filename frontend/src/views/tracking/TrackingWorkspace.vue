<template>
  <div class="tracking-workspace">
    <div class="d-flex align-center flex-wrap ga-3 mb-5">
      <div class="tracking-workspace__intro">
        <h1 class="text-h4 font-weight-bold tracking-tight">Tracking</h1>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Unified monitoring workspace: presence, signals, reports, and live views.
        </div>
      </div>
    </div>

    <nav class="tracking-workspace__nav mb-5" aria-label="Tracking workspace sections">
      <v-tabs
        v-model="activePanel"
        color="primary"
        density="compact"
        align-tabs="start"
        show-arrows
      >
        <v-tab
          v-for="tab in visibleTabs"
          :key="tab.id"
          :value="tab.id"
          :prepend-icon="tab.icon"
        >
          {{ tab.label }}
        </v-tab>
      </v-tabs>
    </nav>

    <v-window v-model="activePanel" class="tracking-workspace__content">
      <v-window-item value="overview">
        <OverviewPanel :locations="presence.locations.value" :loading="presence.loading.value" />
      </v-window-item>

      <v-window-item value="live-floor">
        <LiveFloorPanel />
      </v-window-item>

      <v-window-item value="people">
        <PeoplePanel :locations="presence.locations.value" />
      </v-window-item>

      <v-window-item value="presence-timeline">
        <PresenceTimelinePanel />
      </v-window-item>

      <v-window-item value="signals">
        <SignalsPanel />
      </v-window-item>

      <v-window-item value="reports">
        <ReportsPanel />
      </v-window-item>
    </v-window>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { usePersonPresence } from "@/composables/usePersonPresence.js";
import OverviewPanel from "./panels/OverviewPanel.vue";
import LiveFloorPanel from "./panels/LiveFloorPanel.vue";
import PeoplePanel from "./panels/PeoplePanel.vue";
import PresenceTimelinePanel from "./panels/PresenceTimelinePanel.vue";
import SignalsPanel from "./panels/SignalsPanel.vue";
import ReportsPanel from "./panels/ReportsPanel.vue";

const props = defineProps({
  /** Role governs default panel and visible panel set (D4). No role system exists yet; defaults to admin. */
  role: { type: String, default: "admin" },
});

const ALL_TABS = [
  { id: "overview",           label: "Overview",          icon: "mdi-view-dashboard-outline" },
  { id: "live-floor",         label: "Live & Floor",      icon: "mdi-video-outline"          },
  { id: "people",             label: "People",            icon: "mdi-account-group-outline"  },
  { id: "presence-timeline",  label: "Presence Timeline", icon: "mdi-timeline-clock"         },
  { id: "signals",            label: "Signals",           icon: "mdi-chart-bar"              },
  { id: "reports",            label: "Reports",           icon: "mdi-chart-box"              },
];

const ROLE_CONFIG = {
  admin:    { panels: ALL_TABS.map((t) => t.id), default: "overview" },
  caregiver: { panels: ["presence-timeline", "people", "reports", "live-floor"], default: "presence-timeline" },
  medical:  { panels: ["signals", "reports", "presence-timeline"], default: "signals" },
};

const route = useRoute();
const router = useRouter();

const roleConf = computed(() => ROLE_CONFIG[props.role] ?? ROLE_CONFIG.admin);
const visibleTabs = computed(() => ALL_TABS.filter((t) => roleConf.value.panels.includes(t.id)));

function resolvePanel(panelId) {
  const id = panelId || "";
  if (roleConf.value.panels.includes(id)) return id;
  return roleConf.value.default;
}

const activePanel = ref(resolvePanel(route.query.panel));

// Sync query param → tab when route changes
watch(
  () => route.query.panel,
  (qp) => {
    const resolved = resolvePanel(qp);
    if (resolved !== activePanel.value) activePanel.value = resolved;
  }
);

// Sync tab → query param when tab changes
watch(activePanel, (panel) => {
  if (route.query.panel !== panel) {
    router.replace({ query: { ...route.query, panel } });
  }
});

// Shared presence data (D1: one composable feeds all panels needing current locations)
const presence = usePersonPresence();

defineExpose({ activePanel, visibleTabs, roleConf });
</script>

<style scoped>
.tracking-workspace,
.tracking-workspace__intro,
.tracking-workspace__content {
  min-width: 0;
}

.tracking-workspace__intro {
  max-width: 760px;
}

.tracking-workspace__nav {
  min-width: 0;
  overflow: hidden;
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-sm);
}

.tracking-workspace__nav :deep(.v-tab) {
  min-width: max-content;
}

@media (max-width: 599px) {
  .tracking-workspace__nav {
    margin-inline: -8px;
    border-right: 0;
    border-left: 0;
    border-radius: 0;
  }
}
</style>
