<template>
  <div>
    <!-- Page header -->
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">People & Hypotheses</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Inspect, correct, merge, and split Person Hypotheses from the world-coordinate tracker.
        </div>
      </div>
      <v-spacer />
      <v-btn
        variant="tonal"
        prepend-icon="mdi-refresh"
        :loading="phList.state.loading.value"
        @click="phList.actions.fetch()"
      >
        Refresh
      </v-btn>
      <BlurToggle />
    </div>

    <v-alert v-if="phList.state.error.value" type="error" class="mb-4" closable @click:close="phList.state.error.value = ''">
      {{ phList.state.error.value }}
    </v-alert>

    <!-- WS disconnect banner (only after first connection attempt) -->
    <v-alert
      v-if="wsAttempted && wsStatus !== 'open' && wsStatus !== 'connecting'"
      type="warning"
      variant="tonal"
      class="mb-4"
      density="compact"
    >
      <span class="d-flex align-center ga-2">
        <v-icon size="16">mdi-wifi-off</v-icon>
        Live updates paused. Reconnecting...
        <v-btn size="x-small" variant="outlined" @click="phList.actions.fetch()">Refresh now</v-btn>
      </span>
    </v-alert>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4" density="compact">
      <v-tab value="people">People</v-tab>
      <v-tab value="hypotheses">
        Hypotheses
        <v-chip size="x-small" variant="tonal" class="ml-1">{{ phList.state.total.value }}</v-chip>
      </v-tab>
      <v-tab value="history">History</v-tab>
    </v-tabs>

    <!-- ─────────────── TAB: Hypotheses ─────────────── -->
    <v-card v-if="activeTab === 'hypotheses'" class="glass-card">
      <!-- Filter bar -->
      <v-card variant="flat" class="px-4 py-2" border>
        <v-row dense align="center">
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="phList.state.filters.identity_id"
              :items="identityOptions"
              label="Identity"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              @update:model-value="onFilterChange()"
            />
          </v-col>
          <v-col cols="6" sm="4" md="2">
            <v-select
              v-model="phList.state.filters.room_id"
              :items="roomOptions"
              label="Room"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              @update:model-value="onFilterChange()"
            />
          </v-col>
          <v-col cols="6" sm="4" md="2">
            <v-select
              v-model="phList.state.filters.state"
              :items="stateOptions"
              label="State"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              @update:model-value="onFilterChange()"
            />
          </v-col>
          <v-col cols="6" sm="4" md="2">
            <v-switch
              v-model="phList.state.filters.include_transient"
              label="Transient"
              density="compact"
              hide-details
              color="primary"
              @update:model-value="onFilterChange()"
            />
          </v-col>
          <v-col cols="6" sm="4" md="3">
            <v-text-field
              v-model="phList.state.filters.search"
              label="Search by name"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              @update:model-value="debouncedSearch"
            />
          </v-col>
        </v-row>
      </v-card>

      <v-data-table-server
        v-model:items-per-page="phList.state.pagination.itemsPerPage"
        v-model:page="phList.state.pagination.page"
        :headers="headers"
        :items="phList.state.items.value"
        :items-length="phList.state.total.value"
        :loading="phList.state.loading.value"
        item-value="ph_id"
        items-per-page-text="PHs per page"
        hover
        @click:row="(_event, { item }) => openInspector(item, 'view')"
        @update:options="onTableOptions"
      >
        <!-- Identity -->
        <template #item.current_identity_id="{ item }">
          <div class="d-flex align-center ga-2">
            <v-chip
              :color="item.current_identity_id ? 'success' : 'warning'"
              size="small"
              variant="tonal"
            >
              {{ item.identity_display_name || item.current_identity_id || "UNKNOWN" }}
            </v-chip>
          </div>
        </template>

        <!-- Duration -->
        <template #item.duration="{ item }">
          <span class="text-body-2">{{ formatDuration(item) }}</span>
        </template>

        <!-- Cameras -->
        <template #item.active_cameras="{ item }">
          <div class="d-flex flex-wrap ga-1">
            <v-chip v-for="cid in (item.active_cameras || [])" :key="cid" size="x-small" variant="tonal">
              <v-icon start size="12">mdi-cctv</v-icon> {{ cid }}
            </v-chip>
            <span v-if="!(item.active_cameras || []).length" class="text-caption text-medium-emphasis">—</span>
          </div>
        </template>

        <!-- Last seen -->
        <template #item.last_seen_at="{ item }">
          <span class="text-body-2">{{ formatRelative(item.last_seen_at) }}</span>
        </template>

        <!-- Actions -->
        <template #item.actions="{ item }">
          <div class="d-flex ga-2">
            <v-btn
              size="small"
              variant="tonal"
              prepend-icon="mdi-eye"
              :data-testid="`ph-row-${item.ph_id}`"
              @click="openInspector(item, 'view')"
            >
              Inspect
            </v-btn>
            <v-btn size="small" variant="outlined" prepend-icon="mdi-account-edit" @click="openInspector(item, 'correct')">
              Correct
            </v-btn>
          </div>
        </template>

        <template #no-data>
          <div class="pa-8 text-center">
            <v-icon size="40" color="medium-emphasis" class="mb-2">mdi-account-search-outline</v-icon>
            <div class="text-body-1 text-medium-emphasis">No Person Hypotheses found</div>
            <div class="text-caption text-medium-emphasis mt-1">
              Active PHs appear when a person is detected by a camera.
            </div>
          </div>
        </template>
      </v-data-table-server>
    </v-card>

    <!-- ─────────────── TAB: People ─────────────── -->
    <div v-if="activeTab === 'people'">
      <v-card class="glass-card pa-6">
        <PHPeopleSummary
          :identity-groups="identityGroups"
          :unidentified-count="unidentifiedCount"
        />
      </v-card>
    </div>

    <!-- ─────────────── TAB: History ─────────────── -->
    <v-card v-if="activeTab === 'history'" class="glass-card">
      <div class="pa-3 d-flex align-center ga-3">
        <v-chip-group v-model="revisionsKindFilter" @update:model-value="loadRevisions()">
          <v-chip value="" filter size="small">All</v-chip>
          <v-chip value="auto" filter size="small">Auto</v-chip>
          <v-chip value="manual_correct" filter size="small">Manual</v-chip>
          <v-chip value="manual_merge" filter size="small">Merge</v-chip>
          <v-chip value="manual_split" filter size="small">Split</v-chip>
        </v-chip-group>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">{{ revisions.length }} revision{{ revisions.length !== 1 ? 's' : '' }}</span>
      </div>
      <v-divider />

      <v-list v-if="revisions.length" density="compact" lines="two">
        <template v-for="(rev, idx) in revisions" :key="rev.revision_id">
          <v-list-item class="py-2">
            <template #prepend>
              <v-avatar size="36" :color="kindColor(rev.kind)" variant="tonal" class="mr-3">
                <v-icon size="18">{{ kindIcon(rev.kind) }}</v-icon>
              </v-avatar>
            </template>
            <template #title>
              <span class="font-weight-medium">
                {{ rev.previous_identity_id || "UNKNOWN" }}
                <v-icon size="14" class="mx-1">mdi-arrow-right</v-icon>
                {{ rev.new_identity_id || "UNKNOWN" }}
              </span>
            </template>
            <template #subtitle>
              <span class="text-caption text-medium-emphasis">
                {{ formatRelative(rev.applied_at) }} · {{ rev.actor }} · {{ rev.rewritten_rows }} rows
              </span>
            </template>
          </v-list-item>
          <v-divider v-if="idx + 1 < revisions.length" />
        </template>
      </v-list>

      <div v-else class="pa-8 text-center">
        <v-icon size="40" color="medium-emphasis" class="mb-2">mdi-history</v-icon>
        <div class="text-body-1 text-medium-emphasis">No revisions recorded yet</div>
      </div>

      <div v-if="revisionsHasMore" class="pa-3 text-center">
        <v-btn variant="tonal" size="small" :loading="loadingRevisions" @click="loadMoreRevisions">
          Load more
        </v-btn>
      </div>
    </v-card>

    <!-- Inspector drawer -->
    <v-navigation-drawer v-model="drawerOpen" location="right" width="480" temporary class="cc-drawer-right">
      <PHInspectorDrawer
        v-if="inspectorPh"
        :ph-id="inspectorPh.ph_id"
        :mode="drawerMode"
        :identities="identities"
        @apply="onDrawerApply"
        @close="drawerOpen = false"
      />
    </v-navigation-drawer>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from "vue";
import { formatRelative } from "@/composables/useFormatRelative";
import { identityColor } from "@/composables/useIdentityColor";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";
import { usePHList } from "@/composables/usePHList";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket";
import { ctsPh } from "@/services/cts_ph";
import PHInspectorDrawer from "@/components/cts/ph/PHInspectorDrawer.vue";
import PHPeopleSummary from "@/components/cts/ph/PHPeopleSummary.vue";
import BlurToggle from "@/components/cts/BlurToggle.vue";

let searchTimer = null;

const stateOptions = [
  { title: "Active", value: "active" },
  { title: "Coasting", value: "coasting" },
  { title: "Ended", value: "ended" },
];

export default {
  name: "CTSPersonHypothesesView",

  components: { PHInspectorDrawer, PHPeopleSummary, BlurToggle },

  setup() {
    const { blurMode } = useBlurMode();
    const phList = usePHList();

    const wsStatus = ref("disconnected");
    const drawerOpen = ref(false);
    const drawerMode = ref("view");
    const inspectorPh = ref(null);
    const identities = ref([]);
    const activeTab = ref("hypotheses");

    // Revisions
    const revisions = ref([]);
    const revisionsHasMore = ref(false);
    const revisionsKindFilter = ref("");
    const loadingRevisions = ref(false);
    let revisionsCursor = null;

    // WS
    function onWsMessage(raw) {
      try {
        const event = JSON.parse(raw.data);
        if (event.type === "cts_ph_update" || event.type === "cts_ph_correction") {
          phList.actions.handleWsEvent(event);
        }
      } catch { /* ignore malformed */ }
    }

    const { status, attempted: wsAttempted } = useCtsWebSocket(onWsMessage);

    onMounted(() => {
      phList.actions.fetch();
      loadIdentities();
    });

    // Mirror WS status into a local ref for the template
    watch(status, (val) => {
      wsStatus.value = val;
    }, { immediate: true });

    async function loadIdentities() {
      try {
        const { cts } = await import("@/services/cts");
        const data = await cts.getIdentities();
        identities.value = data.identities || [];
      } catch { /* identities are non-critical */ }
    }

    // ── Identity groups for People tab ──
    const identityGroups = computed(() => {
      const byId = new Map();
      for (const ph of phList.state.items.value) {
        const id = ph.current_identity_id;
        if (!id) continue;
        if (!byId.has(id)) {
          byId.set(id, {
            identity_id: id,
            display_name: ph.identity_display_name || id,
            count: 0,
          });
        }
        byId.get(id).count++;
      }
      return [...byId.values()];
    });

    const unidentifiedCount = computed(
      () => phList.state.items.value.filter((ph) => !ph.current_identity_id).length
    );

    // ── Table ──
    const headers = [
      { title: "Identity", key: "current_identity_id", sortable: false, width: 180 },
      { title: "Duration", key: "duration", sortable: false, width: 90 },
      { title: "Cameras", key: "active_cameras", sortable: false, width: 180 },
      { title: "Last seen", key: "last_seen_at", sortable: false, width: 120 },
      { title: "", key: "actions", sortable: false, width: 210 },
    ];

    const identityOptions = computed(() => {
      const seen = new Set();
      const opts = [];
      for (const ph of phList.state.items.value) {
        if (ph.current_identity_id && !seen.has(ph.current_identity_id)) {
          seen.add(ph.current_identity_id);
          opts.push({
            title: ph.identity_display_name || ph.current_identity_id,
            value: ph.current_identity_id,
          });
        }
      }
      return opts;
    });

    const roomOptions = computed(() => {
      const seen = new Set();
      const opts = [];
      for (const ph of phList.state.items.value) {
        const rn = ph.room_name;
        if (rn && !seen.has(rn)) {
          seen.add(rn);
          opts.push({ title: rn, value: rn });
        }
      }
      return opts;
    });

    function formatDuration(ph) {
      if (!ph.born_at) return "—";
      const started = new Date(ph.born_at);
      const ended = ph.last_seen_at ? new Date(ph.last_seen_at) : new Date();
      const sec = Math.round((ended - started) / 1000);
      if (sec < 60) return `${sec}s`;
      const min = Math.floor(sec / 60);
      if (min < 60) return `${min}m`;
      const hr = Math.floor(min / 60);
      const rem = min % 60;
      return rem ? `${hr}h ${rem}m` : `${hr}h`;
    }

    // ── Filter / pagination ──
    function onFilterChange() {
      phList.state.pagination.page = 1;
      phList.actions.fetch();
    }

    function debouncedSearch(val) {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        phList.state.pagination.page = 1;
        phList.actions.fetch();
      }, 300);
    }

    function onTableOptions(opts) {
      if (opts.itemsPerPage !== phList.state.pagination.itemsPerPage) {
        phList.state.pagination.itemsPerPage = opts.itemsPerPage;
        phList.state.pagination.page = 1;
      } else {
        phList.state.pagination.page = opts.page;
      }
      phList.actions.fetch();
    }

    // ── Inspector ──
    function openInspector(ph, mode) {
      inspectorPh.value = ph;
      drawerMode.value = mode;
      drawerOpen.value = true;
    }

    async function onDrawerApply() {
      drawerOpen.value = false;
      await phList.actions.fetch();
      loadIdentities();
    }

    // ── Revisions ──
    async function loadRevisions() {
      loadingRevisions.value = true;
      try {
        const params = { limit: 50 };
        if (revisionsKindFilter.value) params.kind = revisionsKindFilter.value;
        const data = await ctsPh.revisions(params);
        revisions.value = data.items || [];
        revisionsHasMore.value = data.has_more || false;
        if (revisions.value.length) {
          revisionsCursor = revisions.value[revisions.value.length - 1].revision_id;
        }
      } catch (err) {
        console.error("Failed to load revisions", err);
      } finally {
        loadingRevisions.value = false;
      }
    }

    async function loadMoreRevisions() {
      loadingRevisions.value = true;
      try {
        const params = { limit: 50, before_id: revisionsCursor };
        if (revisionsKindFilter.value) params.kind = revisionsKindFilter.value;
        const data = await ctsPh.revisions(params);
        const more = data.items || [];
        revisions.value = [...revisions.value, ...more];
        revisionsHasMore.value = data.has_more || false;
        if (more.length) revisionsCursor = more[more.length - 1].revision_id;
      } catch (err) {
        console.error("Failed to load more revisions", err);
      } finally {
        loadingRevisions.value = false;
      }
    }

    function kindColor(kind) {
      return kind === "auto" ? "info" : kind === "manual_merge" ? "primary" : "warning";
    }

    function kindIcon(kind) {
      return kind === "auto" ? "mdi-robot-outline" : kind === "manual_merge" ? "mdi-merge" : "mdi-account-edit-outline";
    }

    return {
      phList,
      wsStatus,
      wsAttempted,
      activeTab,
      drawerOpen,
      drawerMode,
      inspectorPh,
      identities,
      identityGroups,
      unidentifiedCount,
      headers,
      identityOptions,
      roomOptions,
      revisions,
      revisionsHasMore,
      revisionsKindFilter,
      loadingRevisions,
      formatRelative,
      identityColor,
      formatDuration,
      onFilterChange,
      debouncedSearch,
      onTableOptions,
      openInspector,
      onDrawerApply,
      loadRevisions,
      loadMoreRevisions,
      kindColor,
      kindIcon,
    };
  },
};
</script>

<style scoped>
/* Right-side drawer: pin to viewport, clear app bar, independent scroll */
.cc-drawer-right {
  position: fixed !important;
  top: 0 !important;
  bottom: 0 !important;
  height: auto !important;
}
.cc-drawer-right :deep(.v-navigation-drawer__content) {
  flex: 1 1 0;
  min-height: 0;
  padding-top: 64px;
}
</style>
