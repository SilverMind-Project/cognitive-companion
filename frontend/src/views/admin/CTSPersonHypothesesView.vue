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
      <div class="ph-filter-bar px-4 py-3">
        <div class="ph-filter-grid">
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
          <v-select
            v-model="phList.state.filters.min_duration_s"
            :items="durationOptions"
            label="Min duration"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            @update:model-value="onFilterChange()"
          />
          <v-switch
            v-model="phList.state.filters.include_transient"
            label="Include transient"
            density="compact"
            hide-details
            color="primary"
            @update:model-value="onFilterChange()"
          />
        </div>
      </div>

      <div class="d-flex align-center flex-wrap ga-3 px-4 py-3">
        <v-chip v-if="selectedPhIds.length" size="small" color="primary" variant="tonal">
          {{ selectedPhIds.length }} selected
        </v-chip>
        <v-btn
          v-if="selectedPhIds.length"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-merge"
          :disabled="selectedPhIds.length < 2"
          @click="openBulkMergeDialog"
        >
          Merge selected
        </v-btn>
        <v-btn
          v-if="selectedPhIds.length"
          color="error"
          variant="tonal"
          prepend-icon="mdi-delete-outline"
          :loading="bulkDeleting"
          @click="deleteSelected"
        >
          Delete selected
        </v-btn>
        <v-spacer />
        <v-text-field
          v-model.number="purgeOlderThanDays"
          label="Purge unknown older than"
          suffix="days"
          type="number"
          min="1"
          max="3650"
          variant="outlined"
          density="compact"
          hide-details
          style="max-width: 230px"
        />
        <v-btn
          color="warning"
          variant="outlined"
          prepend-icon="mdi-delete-clock-outline"
          :loading="purgingUnknown"
          @click="purgeUnknown"
        >
          Purge unknown
        </v-btn>
      </div>
      <v-divider />

      <v-data-table-server
        v-model="selectedPhIds"
        v-model:items-per-page="phList.state.pagination.itemsPerPage"
        v-model:page="phList.state.pagination.page"
        :headers="headers"
        :items="phList.state.items.value"
        :items-length="phList.state.total.value"
        :loading="phList.state.loading.value"
        item-value="ph_id"
        items-per-page-text="PHs per page"
        show-select
        hover
        @click:row="(_event, { item }) => openInspector(item, 'view')"
        @update:options="onTableOptions"
      >
        <!-- Hypothesis -->
        <template #item.hypothesis="{ item }">
          <div class="d-flex flex-column ga-1">
            <v-chip
              :color="item.current_identity_id ? 'success' : 'warning'"
              size="small"
              variant="tonal"
              class="align-self-start"
            >
              {{ item.identity_display_name || item.current_identity_id || "UNKNOWN" }}
            </v-chip>
            <span class="cc-code text-caption">{{ shortPhId(item.ph_id) }}</span>
          </div>
        </template>

        <!-- Duration -->
        <template #item.duration="{ item }">
          <span class="text-body-2">{{ formatDuration(item) }}</span>
        </template>

        <!-- Room -->
        <template #item.room_name="{ item }">
          <span class="text-body-2">{{ item.room_name || "—" }}</span>
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
              @click.stop="openInspector(item, 'view')"
            >
              Inspect
            </v-btn>
            <v-btn
              size="small"
              variant="outlined"
              prepend-icon="mdi-account-edit"
              @click.stop="openInspector(item, 'correct')"
            >
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
    <v-navigation-drawer v-model="drawerOpen" location="right" width="640" temporary class="cc-drawer-right">
      <PHInspectorDrawer
        v-if="inspectorPh"
        :ph-id="inspectorPh.ph_id"
        :mode="drawerMode"
        :identities="identities"
        :merge-candidates="tableMergeCandidates"
        @apply="onDrawerApply"
        @close="drawerOpen = false"
        @inspect-ph="openInspectorById"
      />
    </v-navigation-drawer>

    <v-dialog v-model="confirmDialogOpen" max-width="420" persistent>
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" @click="onConfirm">{{ confirmLabel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="bulkMergeDialogOpen" max-width="640" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-merge"
          label="Person Hypotheses"
          title="Merge Selected Tracks"
          @close="closeBulkMergeDialog"
        />
        <v-card-text>
          <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
            Choose the track to keep. All other selected PHs will be merged into it.
          </v-alert>
          <v-radio-group v-model="bulkMergeTargetId" hide-details>
            <div class="bulk-merge-list">
              <v-radio
                v-for="ph in selectedPhRows"
                :key="ph.ph_id"
                :value="ph.ph_id"
                class="bulk-merge-option"
              >
                <template #label>
                  <div class="d-flex flex-column ga-1">
                    <div class="d-flex align-center ga-2 flex-wrap">
                      <v-chip
                        :color="ph.current_identity_id ? 'success' : 'warning'"
                        size="x-small"
                        variant="tonal"
                      >
                        {{ ph.identity_display_name || ph.current_identity_id || "UNKNOWN" }}
                      </v-chip>
                      <span class="text-caption text-medium-emphasis">{{ shortPhId(ph.ph_id) }}</span>
                    </div>
                    <div class="text-caption text-medium-emphasis">
                      {{ ph.room_name || ph.last_seen_camera || "location unknown" }} ·
                      {{ formatRelative(ph.last_seen_at) }}
                    </div>
                  </div>
                </template>
              </v-radio>
            </div>
          </v-radio-group>
          <v-text-field
            v-model="bulkMergeReason"
            label="Reason"
            variant="outlined"
            density="compact"
            hide-details
            class="mt-4"
          />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <span class="text-caption text-medium-emphasis">
            {{ bulkMergeSourceCount }} source{{ bulkMergeSourceCount === 1 ? "" : "s" }} will be merged.
          </span>
          <v-spacer />
          <v-btn variant="text" @click="closeBulkMergeDialog">Cancel</v-btn>
          <v-btn
            color="warning"
            variant="flat"
            :disabled="!bulkMergeTargetId || bulkMergeSourceCount < 1"
            :loading="bulkMerging"
            @click="mergeSelected"
          >
            Merge
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from "vue";
import { formatRelative } from "@/composables/useFormatRelative";
import { usePHList } from "@/composables/usePHList";
import { useCtsWebSocket } from "@/composables/useCtsWebSocket";
import { useConfirm } from "@/composables/useConfirm";
import { useNotify } from "@/composables/useNotify";
import { ctsPh } from "@/services/cts_ph";
import PHInspectorDrawer from "@/components/cts/ph/PHInspectorDrawer.vue";
import PHPeopleSummary from "@/components/cts/ph/PHPeopleSummary.vue";
import BlurToggle from "@/components/cts/BlurToggle.vue";
import DialogHeader from "@/components/common/DialogHeader.vue";

const stateOptions = [
  { title: "Active", value: "active" },
  { title: "Coasting", value: "coasting" },
  { title: "Ended", value: "ended" },
];

const durationOptions = [
  { title: "> 10s", value: 10 },
  { title: "> 30s", value: 30 },
  { title: "> 1m", value: 60 },
  { title: "> 5m", value: 300 },
  { title: "> 30m", value: 1800 },
];

export default {
  name: "CTSPersonHypothesesView",

  components: { PHInspectorDrawer, PHPeopleSummary, BlurToggle, DialogHeader },

  setup() {
    const phList = usePHList();
    const { notify } = useNotify();
    const {
      require: confirm,
      confirmDialog: confirmDialogOpen,
      confirmTitle,
      confirmText,
      confirmLabel,
      cancelLabel,
      confirmColor,
      onConfirm,
      onCancel,
    } = useConfirm();

    const wsStatus = ref("disconnected");
    const drawerOpen = ref(false);
    const drawerMode = ref("view");
    const inspectorPh = ref(null);
    const identities = ref([]);
    const activeTab = ref("hypotheses");
    const selectedPhIds = ref([]);
    const bulkDeleting = ref(false);
    const bulkMerging = ref(false);
    const bulkMergeDialogOpen = ref(false);
    const bulkMergeTargetId = ref("");
    const bulkMergeReason = ref("manual_bulk_merge");
    const purgingUnknown = ref(false);
    const purgeOlderThanDays = ref(7);

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

    const tableMergeCandidates = computed(() =>
      phList.state.items.value.filter((ph) => ph.ph_id !== inspectorPh.value?.ph_id)
    );

    // ── Table ──
    const headers = [
      { title: "Hypothesis", key: "hypothesis", sortable: false, width: 230 },
      { title: "Duration", key: "duration", sortable: false, width: 100 },
      { title: "Room", key: "room_name", sortable: false, width: 150 },
      { title: "Cameras", key: "active_cameras", sortable: false, width: 210 },
      { title: "Last seen", key: "last_seen_at", sortable: false, width: 130 },
      { title: "", key: "actions", sortable: false, width: 190 },
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

    function shortPhId(phId) {
      return phId ? phId.slice(0, 8) : "";
    }

    const selectedPhRows = computed(() => {
      const selected = new Set(selectedPhIds.value);
      return phList.state.items.value.filter((ph) => selected.has(ph.ph_id));
    });

    const bulkMergeSourceIds = computed(() =>
      selectedPhRows.value.map((ph) => ph.ph_id).filter((phId) => phId !== bulkMergeTargetId.value)
    );

    const bulkMergeSourceCount = computed(() => bulkMergeSourceIds.value.length);

    // ── Filter / pagination ──
    function onFilterChange() {
      selectedPhIds.value = [];
      phList.state.pagination.page = 1;
      phList.actions.fetch();
    }

    function onTableOptions(opts) {
      const pageChanged = opts.page !== phList.state.pagination.page;
      const sizeChanged = opts.itemsPerPage !== phList.state.pagination.itemsPerPage;
      if (opts.itemsPerPage !== phList.state.pagination.itemsPerPage) {
        phList.state.pagination.itemsPerPage = opts.itemsPerPage;
        phList.state.pagination.page = 1;
      } else {
        phList.state.pagination.page = opts.page;
      }
      if (pageChanged || sizeChanged) selectedPhIds.value = [];
      phList.actions.fetch();
    }

    // ── Inspector ──
    function openInspector(ph, mode) {
      inspectorPh.value = ph;
      drawerMode.value = mode;
      drawerOpen.value = true;
    }

    async function openInspectorById(phId) {
      const existing = phList.state.items.value.find((ph) => ph.ph_id === phId);
      inspectorPh.value = existing || { ph_id: phId };
      drawerMode.value = "view";
      drawerOpen.value = true;
    }

    async function onDrawerApply() {
      drawerOpen.value = false;
      await phList.actions.fetch();
      loadIdentities();
    }

    async function deleteSelected() {
      if (!selectedPhIds.value.length) return;
      const ok = await confirm(
        `Delete ${selectedPhIds.value.length} selected Person Hypotheses? This removes their PH records and linked observations.`,
        { confirmText: "Delete", color: "error" }
      );
      if (!ok) return;
      bulkDeleting.value = true;
      try {
        const data = await ctsPh.batchDelete(selectedPhIds.value, "manual_bulk_delete");
        notify(`Deleted ${data.deleted} Person Hypotheses`, "success");
        selectedPhIds.value = [];
        await phList.actions.fetch();
      } catch (err) {
        notify(String(err.message || err), "error");
      } finally {
        bulkDeleting.value = false;
      }
    }

    function openBulkMergeDialog() {
      if (selectedPhIds.value.length < 2) {
        notify("Select at least two Person Hypotheses to merge.", "warning");
        return;
      }
      const identified = selectedPhRows.value.find((ph) => ph.current_identity_id);
      bulkMergeTargetId.value = identified?.ph_id || selectedPhIds.value[0] || "";
      bulkMergeReason.value = "manual_bulk_merge";
      bulkMergeDialogOpen.value = true;
    }

    function closeBulkMergeDialog() {
      if (bulkMerging.value) return;
      bulkMergeDialogOpen.value = false;
      bulkMergeTargetId.value = "";
      bulkMergeReason.value = "manual_bulk_merge";
    }

    async function mergeSelected() {
      if (!bulkMergeTargetId.value || bulkMergeSourceIds.value.length < 1) return;
      const ok = await confirm(
        `Merge ${bulkMergeSourceIds.value.length} selected Person Hypotheses into ${bulkMergeTargetId.value}? This cannot be undone.`,
        { confirmText: "Merge", color: "warning" }
      );
      if (!ok) return;

      bulkMerging.value = true;
      try {
        const data = await ctsPh.batchMerge({
          source_ph_ids: bulkMergeSourceIds.value,
          target_ph_id: bulkMergeTargetId.value,
          reason: bulkMergeReason.value || "manual_bulk_merge",
        });
        notify(`Merged ${data.applied} Person Hypotheses`, "success");
        selectedPhIds.value = [];
        bulkMergeDialogOpen.value = false;
        bulkMergeTargetId.value = "";
        bulkMergeReason.value = "manual_bulk_merge";
        await phList.actions.fetch();
        loadIdentities();
      } catch (err) {
        notify(String(err.message || err), "error");
      } finally {
        bulkMerging.value = false;
      }
    }

    async function purgeUnknown() {
      const days = Number(purgeOlderThanDays.value);
      if (!Number.isFinite(days) || days < 1) {
        notify("Purge age must be at least 1 day.", "error");
        return;
      }
      const ok = await confirm(
        `Delete closed UNKNOWN Person Hypotheses last seen more than ${days} day${days === 1 ? "" : "s"} ago?`,
        { confirmText: "Purge", color: "warning" }
      );
      if (!ok) return;
      purgingUnknown.value = true;
      try {
        const data = await ctsPh.purgeUnknown({ older_than_days: days, limit: 1000 });
        notify(`Purged ${data.deleted} unknown Person Hypotheses`, "success");
        await phList.actions.fetch();
      } catch (err) {
        notify(String(err.message || err), "error");
      } finally {
        purgingUnknown.value = false;
      }
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
      selectedPhIds,
      bulkDeleting,
      bulkMerging,
      bulkMergeDialogOpen,
      bulkMergeTargetId,
      bulkMergeReason,
      purgingUnknown,
      purgeOlderThanDays,
      identityGroups,
      unidentifiedCount,
      tableMergeCandidates,
      selectedPhRows,
      bulkMergeSourceCount,
      headers,
      identityOptions,
      roomOptions,
      durationOptions,
      revisions,
      revisionsHasMore,
      revisionsKindFilter,
      loadingRevisions,
      formatRelative,
      formatDuration,
      shortPhId,
      onFilterChange,
      onTableOptions,
      openInspector,
      openInspectorById,
      onDrawerApply,
      deleteSelected,
      openBulkMergeDialog,
      closeBulkMergeDialog,
      mergeSelected,
      purgeUnknown,
      loadRevisions,
      loadMoreRevisions,
      kindColor,
      kindIcon,
      confirmDialogOpen,
      confirmTitle,
      confirmText,
      confirmLabel,
      cancelLabel,
      confirmColor,
      onConfirm,
      onCancel,
    };
  },
};
</script>

<style scoped>
.ph-filter-bar {
  border-bottom: 1px solid var(--cc-divider);
}

.ph-filter-grid {
  display: grid;
  grid-template-columns: minmax(180px, 1.2fr) minmax(150px, 1fr) minmax(140px, 0.8fr) minmax(160px, 0.9fr) minmax(170px, auto);
  gap: 12px;
  align-items: center;
}

.bulk-merge-list {
  display: grid;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.bulk-merge-option {
  border: 1px solid var(--cc-divider);
  border-radius: var(--cc-radius-sm);
  padding: 8px;
}

@media (max-width: 960px) {
  .ph-filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .ph-filter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
