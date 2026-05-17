<template>
  <div>
    <!-- Page header -->
    <div class="d-flex align-center mb-4">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Identity Corrections</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Review and override identity assignments for active tracking graphs.
        </div>
      </div>
      <v-spacer />
      <v-btn
        v-if="selected.length"
        variant="tonal"
        color="warning"
        prepend-icon="mdi-checkbox-multiple-marked"
        class="mr-3"
        @click="confirmBulkUnknown"
      >
        Confirm {{ selected.length }} as UNKNOWN
      </v-btn>
      <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="refreshAll">
        Refresh
      </v-btn>
    </div>

    <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = ''">
      {{ error }}
    </v-alert>

    <!-- Filter row -->
    <v-card variant="flat" class="mb-4 px-4 py-2" border>
      <v-row dense align="center">
        <v-col cols="12" sm="4" md="3">
          <v-select
            v-model="filters.status"
            :items="statusOptions"
            label="Status"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            @update:model-value="loadTracks()"
          />
        </v-col>
        <v-col cols="12" sm="4" md="3">
          <v-select
            v-model="filters.camera_id"
            :items="cameraOptions"
            label="Camera"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            @update:model-value="loadTracks()"
          />
        </v-col>
        <v-col cols="12" sm="4" md="3">
          <v-text-field
            v-model="filters.search"
            label="Search identity"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            prepend-inner-icon="mdi-magnify"
            @update:model-value="debouncedSearch()"
          />
        </v-col>
        <v-col cols="12" sm="4" md="3" class="d-flex align-center">
          <v-switch
            v-model="showTransient"
            label="Show transient (< 10 s)"
            density="compact"
            hide-details
            @update:model-value="loadTracks()"
          />
        </v-col>
      </v-row>
    </v-card>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" class="mb-4" density="compact" @update:model-value="onTabChange">
      <v-tab value="active">
        Active
        <v-chip size="x-small" variant="tonal" class="ml-1">{{ activeCount }}</v-chip>
      </v-tab>
      <v-tab value="recent">
        Recent 24h
      </v-tab>
      <v-tab value="decisions">
        Decisions log
      </v-tab>
    </v-tabs>

    <!-- Tab: Active / Recent tracks -->
    <v-card v-if="activeTab !== 'decisions'" variant="flat" border>
      <v-data-table-server
        v-model="selected"
        v-model:items-per-page="pagination.itemsPerPage"
        v-model:page="pagination.page"
        :headers="trackHeaders"
        :items="tracks"
        :items-length="totalTracks"
        :loading="loading"
        show-select
        return-object
        item-value="global_track_id"
        items-per-page-text="Tracks per page"
        @update:options="onTableOptions"
      >
        <template #item.current_identity_id="{ item }">
          <v-chip
            :color="item.current_identity_id ? 'success' : 'warning'"
            size="small"
            variant="tonal"
          >
            {{ identityLabel(item) }}
          </v-chip>
        </template>
        <template #item.camera_ids="{ item }">
          <span class="text-caption text-medium-emphasis">
            {{ (item.camera_ids || []).join(", ") || "—" }}
          </span>
        </template>
        <template #item.last_seen_at="{ item }">
          <span class="text-caption text-medium-emphasis">
            {{ formatRelative(item.last_seen_at) }}
          </span>
        </template>
        <template #item.best_guess="{ item }">
          <span v-if="item.current_identity_id" class="text-caption text-medium-emphasis">—</span>
          <v-chip
            v-else-if="topCompetitor(item)"
            size="x-small"
            variant="tonal"
            color="info"
          >
            {{ topCompetitorLabel(item) }}
          </v-chip>
          <span v-else class="text-caption text-disabled">none</span>
        </template>
        <template #item.actions="{ item }">
          <v-btn
            size="small"
            variant="tonal"
            prepend-icon="mdi-account-edit"
            class="mr-1"
            @click="openInspector(item, 'correct')"
          >
            Correct
          </v-btn>
          <v-btn
            size="small"
            variant="outlined"
            prepend-icon="mdi-merge"
            @click="openInspector(item, 'merge')"
          >
            Merge
          </v-btn>
        </template>
      </v-data-table-server>
    </v-card>

    <!-- Tab: Decisions log -->
    <v-card v-else variant="flat" border>
      <div class="pa-3">
        <v-chip-group v-model="decisionsKindFilter" @update:model-value="loadDecisions()">
          <v-chip value="" filter>All</v-chip>
          <v-chip value="auto" filter>Auto</v-chip>
          <v-chip value="manual_correct" filter>Manual</v-chip>
          <v-chip value="manual_merge" filter>Merge</v-chip>
        </v-chip-group>
      </div>
      <v-list density="compact" lines="two">
        <v-list-item v-for="d in decisions" :key="d.revision_id">
          <template #title>
            <span class="text-caption text-medium-emphasis">
              {{ formatRelative(d.applied_at) }}
            </span>
            <v-chip
              size="x-small"
              :color="kindColor(d.kind)"
              variant="flat"
              class="ml-1"
            >
              {{ kindLabel(d.kind) }}
            </v-chip>
            &middot;
            <span v-if="d.new_identity_id" class="font-weight-medium">
              {{ identityDisplayName(d.new_identity_id) }}
            </span>
            <span v-else class="text-medium-emphasis">UNKNOWN</span>
            <span v-if="d.previous_identity_id">
              (was {{ identityDisplayName(d.previous_identity_id) }})
            </span>
          </template>
          <template #subtitle>
            <span class="text-caption text-medium-emphasis font-mono">
              track: {{ shortId(d.global_track_id) }}
            </span>
            <span class="text-caption text-medium-emphasis ml-2">
              {{ d.rewritten_rows }} rows rewritten
            </span>
          </template>
        </v-list-item>
        <v-list-item v-if="!decisions.length && !loadingDecisions">
          <template #title>
            <span class="text-caption text-medium-emphasis">
              No identity decisions recorded yet.
            </span>
          </template>
        </v-list-item>
      </v-list>
      <div class="pa-3 text-center" v-if="decisionsHasMore">
        <v-btn variant="tonal" size="small" :loading="loadingDecisions" @click="loadMoreDecisions">
          Load more
        </v-btn>
      </div>
    </v-card>

    <!-- Inspector drawer -->
    <v-navigation-drawer
      v-model="drawerOpen"
      location="right"
      width="480"
      temporary
    >
      <IdentityInspectorDrawer
        v-if="inspectorTrack"
        :track="inspectorTrack"
        :mode="drawerMode"
        :identities="identities"
        @apply="onDrawerApply"
        @close="drawerOpen = false"
      />
    </v-navigation-drawer>

    <!-- Bulk confirm dialog -->
    <v-dialog v-model="bulkDialogOpen" max-width="480">
      <v-card>
        <v-card-title>Confirm as UNKNOWN</v-card-title>
        <v-card-text>
          Mark {{ selected.length }} selected tracks as UNKNOWN?
          This will clear any assigned identity for these tracks.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="bulkDialogOpen = false">Cancel</v-btn>
          <v-btn variant="flat" color="warning" :loading="bulkSaving" @click="executeBulk">
            Confirm
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { cts } from "@/services/cts";
import { formatRelative } from "@/composables/useFormatRelative";
import IdentityInspectorDrawer from "@/components/cts/identity/IdentityInspectorDrawer.vue";

let searchTimer = null;

export default {
  name: "CTSIdentityCorrectionsView",
  components: { IdentityInspectorDrawer },
  data() {
    return {
      error: "",
      loading: false,
      loadingDecisions: false,
      tracks: [],
      totalTracks: 0,
      activeCount: 0,
      selected: [],
      identities: [],
      activeTab: "active",
      filters: { status: null, camera_id: null, search: "" },
      showTransient: false,
      pagination: { page: 1, itemsPerPage: 24 },
      // Decisions
      decisions: [],
      decisionsHasMore: false,
      decisionsKindFilter: "",
      decisionsCursor: null,
      // Drawer
      drawerOpen: false,
      drawerMode: "correct",
      inspectorTrack: null,
      // Bulk
      bulkDialogOpen: false,
      bulkSaving: false,
      // Camera filter options
      cameraOptions: [],
    };
  },
  computed: {
    trackHeaders() {
      return [
        { title: "Identity", key: "current_identity_id", sortable: false },
        { title: "Room / Camera", key: "camera_ids", sortable: false },
        { title: "Last seen", key: "last_seen_at", sortable: false },
        { title: "Best guess", key: "best_guess", sortable: false },
        { title: "", key: "actions", sortable: false, width: 1 },
      ];
    },
    statusOptions() {
      return [
        { title: "All", value: "" },
        { title: "Committed", value: "committed" },
        { title: "UNKNOWN", value: "UNKNOWN" },
      ];
    },
    identityItems() {
      return this.identities.map((id) => ({
        identity_id: id.identity_id,
        label: id.display_name || id.identity_id,
      }));
    },
    identityMap() {
      const m = {};
      for (const id of this.identities) {
        m[id.identity_id] = id.display_name || id.identity_id;
      }
      return m;
    },
  },
  mounted() {
    this.refreshAll();
  },
  methods: {
    formatRelative,
    identityLabel(track) {
      if (!track || !track.current_identity_id) return "UNKNOWN";
      return this.identityMap[track.current_identity_id] || track.current_identity_id;
    },
    identityDisplayName(identityId) {
      if (!identityId) return "—";
      return this.identityMap[identityId] || identityId;
    },
    shortId(id) {
      if (!id) return "—";
      return id.length > 16 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
    },
    kindColor(kind) {
      return kind === "auto" ? "info" : kind === "manual_merge" ? "primary" : "warning";
    },
    kindLabel(kind) {
      return kind === "auto" ? "Auto" : kind === "manual_merge" ? "Merge" : "Manual";
    },
    topCompetitor(track) {
      const posterior = track.last_posterior_jsonb;
      if (!posterior || !Array.isArray(posterior.top) || !posterior.top.length) return null;
      return posterior.top[0];
    },
    topCompetitorLabel(track) {
      const top = this.topCompetitor(track);
      if (!top) return "";
      const name = this.identityMap[top.identity_id] || top.identity_id;
      const pct = top.prob != null ? ` (${Math.round(top.prob * 100)}%)` : "";
      return `${name}${pct}`;
    },
    debouncedSearch() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => this.loadTracks(), 300);
    },
    async refreshAll() {
      await Promise.all([this.loadTracks(), this.loadIdentities()]);
    },
    async loadTracks() {
      this.loading = true;
      try {
        const params = {
          open_only: this.activeTab === "active",
          limit: this.pagination.itemsPerPage,
          offset: (this.pagination.page - 1) * this.pagination.itemsPerPage,
        };
        if (this.filters.status) params.status = this.filters.status;
        if (this.filters.camera_id) params.camera_id = this.filters.camera_id;
        if (this.filters.search) params.search = this.filters.search;
        params.include_transient = this.showTransient;
        if (!this.showTransient) params.min_duration_s = 10;
        const data = await cts.getGlobalTracks(params);
        this.tracks = data.tracks || [];
        this.totalTracks = data.count || this.tracks.length;
        this.activeCount = data.count || this.tracks.length;
        // Populate camera filter
        const cams = new Set();
        for (const t of this.tracks) {
          for (const cid of t.camera_ids || []) cams.add(cid);
        }
        this.cameraOptions = [...cams].map((c) => ({ title: c, value: c }));
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.loading = false;
      }
    },
    async loadIdentities() {
      try {
        const data = await cts.getIdentities();
        this.identities = data.identities || [];
      } catch (err) {
        this.error = String(err.message || err);
      }
    },
    async loadDecisions() {
      this.loadingDecisions = true;
      try {
        const params = { limit: 50 };
        if (this.decisionsKindFilter) params.kind = this.decisionsKindFilter;
        const data = await cts.getDecisions(params);
        this.decisions = data.decisions || [];
        this.decisionsHasMore = data.has_more || false;
        this.decisionsCursor = this.decisions.length
          ? this.decisions[this.decisions.length - 1].revision_id
          : null;
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.loadingDecisions = false;
      }
    },
    async loadMoreDecisions() {
      this.loadingDecisions = true;
      try {
        const params = { limit: 50, before_id: this.decisionsCursor };
        if (this.decisionsKindFilter) params.kind = this.decisionsKindFilter;
        const data = await cts.getDecisions(params);
        const newDecisions = data.decisions || [];
        this.decisions = [...this.decisions, ...newDecisions];
        this.decisionsHasMore = data.has_more || false;
        if (newDecisions.length) {
          this.decisionsCursor = newDecisions[newDecisions.length - 1].revision_id;
        }
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.loadingDecisions = false;
      }
    },
    onTabChange(tab) {
      this.selected = [];
      this.pagination.page = 1;
      if (tab === "decisions") {
        this.loadDecisions();
      } else {
        this.loadTracks();
      }
    },
    onTableOptions(opts) {
      this.pagination.page = opts.page;
      this.pagination.itemsPerPage = opts.itemsPerPage;
      this.loadTracks();
    },
    openInspector(track, mode) {
      this.drawerMode = mode;
      this.inspectorTrack = track;
      this.drawerOpen = true;
    },
    async onDrawerApply(form) {
      try {
        if (this.drawerMode === "merge") {
          await cts.mergeIdentities({
            global_track_id: this.inspectorTrack.global_track_id,
            from_identity_id: form.from_identity_id,
            to_identity_id: form.new_identity_id,
            reason: form.reason,
          });
        } else {
          await cts.applyCorrection({
            global_track_id: this.inspectorTrack.global_track_id,
            new_identity_id: form.new_identity_id || null,
            reason: form.reason,
          });
        }
        this.drawerOpen = false;
        await this.refreshAll();
      } catch (err) {
        this.error = String(err.message || err);
      }
    },
    confirmBulkUnknown() {
      this.bulkDialogOpen = true;
    },
    async executeBulk() {
      this.bulkSaving = true;
      try {
        const corrections = this.selected.map((t) => ({
          global_track_id: t.global_track_id,
          new_identity_id: null,
          reason: "bulk_confirm_unknown",
        }));
        await cts.batchCorrect(corrections);
        this.selected = [];
        this.bulkDialogOpen = false;
        await this.loadTracks();
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.bulkSaving = false;
      }
    },
  },
};
</script>

<style scoped>
.font-mono {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
}
</style>
