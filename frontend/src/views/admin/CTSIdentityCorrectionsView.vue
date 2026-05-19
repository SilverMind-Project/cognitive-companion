<template>
  <div>
    <!-- Page header -->
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Identity Corrections</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Review evidence and correct identity assignments for active tracking graphs.
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
      <BlurToggle />
    </div>

    <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = ''">
      {{ error }}
    </v-alert>

    <!-- Filter row -->
    <v-card variant="flat" class="mb-4 px-4 py-2" border>
      <v-row dense align="center">
        <v-col cols="6" sm="4" md="2">
          <v-select
            v-model="filters.status"
            :items="statusOptions"
            label="Status"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            @update:model-value="onFilterChange()"
          />
        </v-col>
        <v-col cols="6" sm="4" md="2">
          <v-select
            v-model="filters.camera_id"
            :items="cameraOptions"
            label="Camera"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            @update:model-value="onFilterChange()"
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
        <v-col cols="6" sm="4" md="2">
          <v-select
            v-model="filters.sort"
            :items="sortOptions"
            label="Sort"
            variant="outlined"
            density="compact"
            hide-details
            @update:model-value="onFilterChange()"
          />
        </v-col>
        <v-col cols="6" sm="4" md="2">
          <v-switch
            v-model="showTransient"
            label="Show transient"
            density="compact"
            hide-details
            @update:model-value="onFilterChange()"
          />
        </v-col>
      </v-row>
    </v-card>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4" density="compact" @update:model-value="onTabChange">
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
    <v-card v-if="activeTab !== 'decisions'" class="glass-card">
      <v-data-table-server
        v-model="selected"
        v-model:expanded="expanded"
        v-model:items-per-page="pagination.itemsPerPage"
        v-model:page="pagination.page"
        :headers="trackHeaders"
        :items="tracks"
        :items-length="totalTracks"
        :loading="loading"
        show-expand
        show-select
        return-object
        item-value="global_track_id"
        items-per-page-text="Tracks per page"
        @update:options="onTableOptions"
      >
        <!-- Thumbnail -->
        <template #item.thumbnail="{ item }">
          <v-img
            v-if="item.latest_keyframe_minio_key"
            :src="frameUrl(item.latest_keyframe_minio_key)"
            width="52"
            height="39"
            cover
            rounded="md"
            class="keyframe-thumb"
            :alt="'Keyframe for ' + (item.current_identity_id || 'unknown')"
          />
          <v-sheet
            v-else
            width="52"
            height="39"
            rounded="md"
            color="surface-variant"
            class="d-flex align-center justify-center"
          >
            <v-icon size="16" color="medium-emphasis">mdi-camera-off</v-icon>
          </v-sheet>
        </template>

        <!-- Identity -->
        <template #item.current_identity_id="{ item }">
          <div class="d-flex align-center ga-2">
            <v-chip
              :color="item.current_identity_id ? 'success' : 'warning'"
              size="small"
              variant="tonal"
            >
              {{ identityLabel(item) }}
            </v-chip>
            <v-chip
              v-if="item.current_identity_id && topPosteriorProb(item) > 0"
              size="x-small"
              variant="text"
              class="text-caption text-medium-emphasis"
            >
              {{ (topPosteriorProb(item) * 100).toFixed(0) }}%
            </v-chip>
          </div>
        </template>

        <!-- Duration -->
        <template #item.duration="{ item }">
          <span class="text-body-2">{{ trackDuration(item) }}</span>
        </template>

        <!-- Cameras -->
        <template #item.camera_ids="{ item }">
          <div class="d-flex flex-wrap ga-1">
            <v-chip
              v-for="cid in (item.camera_ids || [])"
              :key="cid"
              size="x-small"
              variant="tonal"
            >
              <v-icon start size="12">mdi-cctv</v-icon>
              {{ cid }}
            </v-chip>
            <span v-if="!(item.camera_ids || []).length" class="text-caption text-medium-emphasis">—</span>
          </div>
        </template>

        <!-- Last seen -->
        <template #item.last_seen_at="{ item }">
          <span class="text-body-2">{{ formatRelative(item.last_seen_at) }}</span>
        </template>

        <!-- Best guess with mini posterior bar -->
        <template #item.best_guess="{ item }">
          <div v-if="item.current_identity_id" class="text-caption text-medium-emphasis">committed</div>
          <template v-else>
            <div
              v-if="posteriorEntries(item).length > 0"
              class="mini-posterior"
            >
              <div
                v-for="seg in posteriorEntries(item).slice(0, 3)"
                :key="seg.label"
                class="mini-posterior-seg"
                :style="{ width: seg.pct + '%', background: seg.color }"
                :title="`${seg.label}: ${(seg.prob * 100).toFixed(1)}%`"
              />
            </div>
            <span v-else class="text-caption text-disabled">no evidence</span>
          </template>
        </template>

        <!-- Actions -->
        <template #item.actions="{ item }">
          <div class="d-flex ga-2">
            <v-btn
              size="small"
              variant="tonal"
              prepend-icon="mdi-account-edit"
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
          </div>
        </template>

        <!-- Expanded row: evidence preview -->
        <template #expanded-row="{ columns, item, isExpanded }">
          <tr v-if="isExpanded" class="expanded-row">
            <td :colspan="columns.length" class="pa-0">
              <div class="expanded-content pa-4">
                <v-row dense>
                  <!-- Posterior evidence -->
                  <v-col cols="12" md="6">
                    <div class="text-caption font-weight-medium mb-2">Identity Evidence</div>
                    <div v-if="posteriorEntries(item).length > 0">
                      <div class="posterior-bar-lg mb-2">
                        <div
                          v-for="seg in posteriorEntries(item)"
                          :key="seg.label"
                          class="posterior-bar-lg-seg"
                          :style="{ width: seg.pct + '%', background: seg.color }"
                          :title="`${seg.label}: ${(seg.prob * 100).toFixed(1)}%`"
                        />
                      </div>
                      <div class="d-flex flex-wrap ga-3">
                        <div
                          v-for="seg in posteriorEntries(item).slice(0, 5)"
                          :key="seg.label"
                          class="d-flex align-center ga-1"
                        >
                          <div
                            class="posterior-dot"
                            :style="{ background: seg.color }"
                          />
                          <span class="text-caption">{{ seg.label }}</span>
                          <span class="text-caption text-medium-emphasis ml-1">
                            {{ (seg.prob * 100).toFixed(0) }}%
                          </span>
                        </div>
                      </div>
                    </div>
                    <span v-else class="text-caption text-medium-emphasis">No posterior evidence recorded for this track.</span>
                  </v-col>

                  <!-- Track summary -->
                  <v-col cols="6" md="3">
                    <div class="text-caption font-weight-medium mb-2">Track Info</div>
                    <div class="d-flex flex-column ga-1">
                      <div class="text-caption">
                        <span class="text-medium-emphasis">Tracklets:</span>
                        {{ (item.tracklet_ids || []).length }}
                      </div>
                      <div class="text-caption">
                        <span class="text-medium-emphasis">Started:</span>
                        {{ formatRelative(item.started_at) }}
                      </div>
                      <div class="text-caption">
                        <span class="text-medium-emphasis">Duration:</span>
                        {{ trackDuration(item) }}
                      </div>
                      <div class="text-caption">
                        <span class="text-medium-emphasis">State:</span>
                        {{ item.state || 'active' }}
                      </div>
                    </div>
                  </v-col>

                  <!-- Keyframe previews -->
                  <v-col cols="6" md="3">
                    <div class="text-caption font-weight-medium mb-2">Keyframes</div>
                    <div v-if="keyframeLoading[item.global_track_id]" class="d-flex align-center ga-2">
                      <v-progress-circular indeterminate size="16" width="2" />
                      <span class="text-caption text-medium-emphasis">Loading...</span>
                    </div>
                    <KeyframeStrip
                      v-else
                      :frames="expandedKeyframes[item.global_track_id] || []"
                      @click="openKeyframeModal"
                    />
                  </v-col>
                </v-row>

                <!-- Quick actions -->
                <div class="d-flex ga-2 mt-3 pt-3" style="border-top: 1px solid var(--cc-divider)">
                  <v-btn
                    size="small"
                    variant="tonal"
                    prepend-icon="mdi-account-edit"
                    @click="openInspector(item, 'correct')"
                  >
                    Correct identity
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="outlined"
                    prepend-icon="mdi-merge"
                    @click="openInspector(item, 'merge')"
                  >
                    Merge with another
                  </v-btn>
                  <v-btn
                    v-if="item.current_identity_id"
                    size="small"
                    variant="text"
                    color="warning"
                    prepend-icon="mdi-close-circle-outline"
                    @click="quickUnknown(item)"
                  >
                    Mark UNKNOWN
                  </v-btn>
                </div>
              </div>
            </td>
          </tr>
        </template>

        <template #no-data>
          <div class="pa-8 text-center">
            <v-icon size="40" color="medium-emphasis" class="mb-2">mdi-account-search-outline</v-icon>
            <div class="text-body-1 text-medium-emphasis">No tracking graphs found</div>
            <div class="text-caption text-medium-emphasis mt-1">
              Active tracks will appear here when a person is detected by a camera.
            </div>
          </div>
        </template>
      </v-data-table-server>
    </v-card>

    <!-- Tab: Decisions log (grouped by track) -->
    <v-card v-else class="glass-card">
      <div class="pa-3 d-flex align-center ga-3">
        <v-chip-group v-model="decisionsKindFilter" @update:model-value="loadDecisions()">
          <v-chip value="" filter>All</v-chip>
          <v-chip value="auto" filter>Auto</v-chip>
          <v-chip value="manual_correct" filter>Manual</v-chip>
          <v-chip value="manual_merge" filter>Merge</v-chip>
        </v-chip-group>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">{{ decisionGroups.length }} track{{ decisionGroups.length === 1 ? '' : 's' }}</span>
      </div>
      <v-divider />

      <!-- Grouped decisions -->
      <v-list v-if="decisionGroups.length" density="compact" lines="two">
        <template v-for="group in decisionGroups" :key="group.global_track_id">
          <v-list-group :value="group.global_track_id">
            <template #activator="{ props: groupProps }">
              <v-list-item
                v-bind="groupProps"
                :title="identityDisplayName(group.current_identity_id) || 'UNKNOWN'"
              >
                <template #prepend>
                  <div class="mr-2">
                    <v-chip
                      :color="group.current_identity_id ? 'success' : 'warning'"
                      size="x-small"
                      variant="tonal"
                    >
                      {{ group.current_identity_id ? 'named' : 'UNKNOWN' }}
                    </v-chip>
                  </div>
                </template>
                <template #append>
                  <span class="text-caption text-medium-emphasis mr-2">
                    {{ group.decisions.length }} decision{{ group.decisions.length === 1 ? '' : 's' }}
                  </span>
                  <span class="text-caption text-medium-emphasis font-mono">
                    {{ shortId(group.global_track_id) }}
                  </span>
                </template>
              </v-list-item>
            </template>
            <v-list-item
              v-for="d in group.decisions"
              :key="d.revision_id"
              class="ps-8"
            >
              <template #title>
                <div class="d-flex align-center ga-2">
                  <span class="text-caption text-medium-emphasis">
                    {{ formatRelative(d.applied_at) }}
                  </span>
                  <v-chip
                    size="x-small"
                    :color="kindColor(d.kind)"
                    variant="flat"
                  >
                    {{ kindLabel(d.kind) }}
                  </v-chip>
                  <span v-if="d.previous_identity_id" class="text-caption text-medium-emphasis">
                    {{ identityDisplayName(d.previous_identity_id) }}
                  </span>
                  <v-icon v-if="d.previous_identity_id" size="14" color="medium-emphasis">mdi-arrow-right</v-icon>
                  <span class="text-caption font-weight-medium">
                    {{ identityDisplayName(d.new_identity_id) || 'UNKNOWN' }}
                  </span>
                </div>
              </template>
              <template #subtitle>
                <span class="text-caption text-medium-emphasis">
                  {{ d.rewritten_rows }} rows rewritten
                </span>
                <span v-if="d.reason" class="text-caption text-medium-emphasis ml-2">
                  · {{ d.reason }}
                </span>
              </template>
            </v-list-item>
          </v-list-group>
        </template>
      </v-list>

      <div v-else-if="!loadingDecisions" class="pa-8 text-center">
        <v-icon size="40" color="medium-emphasis" class="mb-2">mdi-history</v-icon>
        <div class="text-body-1 text-medium-emphasis">No identity decisions recorded yet</div>
        <div class="text-caption text-medium-emphasis mt-1">
          Decisions appear when the system auto-commits an identity or when a manual correction is applied.
        </div>
      </div>

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
      <v-card rounded="xl">
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

    <!-- Keyframe lightbox -->
    <v-dialog v-model="keyframeDialogOpen" max-width="800">
      <v-card v-if="selectedKeyframe" rounded="xl">
        <v-img
          :src="frameUrl(selectedKeyframe.minio_key)"
          max-height="70vh"
          contain
          class="bg-black"
        />
        <v-card-text class="d-flex align-center ga-4">
          <span v-if="selectedKeyframe.captured_at" class="text-caption text-medium-emphasis">
            Captured: {{ formatRelative(selectedKeyframe.captured_at) }}
          </span>
          <span v-if="selectedKeyframe.tag_reason" class="text-caption text-medium-emphasis">
            · {{ selectedKeyframe.tag_reason }}
          </span>
          <v-spacer />
          <v-btn variant="text" size="small" @click="keyframeDialogOpen = false">Close</v-btn>
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
import { cts } from "@/services/cts";
import { formatRelative } from "@/composables/useFormatRelative";
import { identityColor } from "@/composables/useIdentityColor";
import IdentityInspectorDrawer from "@/components/cts/identity/IdentityInspectorDrawer.vue";
import KeyframeStrip from "@/components/cts/identity/KeyframeStrip.vue";
import BlurToggle from "@/components/cts/BlurToggle.vue";

let searchTimer = null;

export default {
  name: "CTSIdentityCorrectionsView",
  components: { IdentityInspectorDrawer, KeyframeStrip, BlurToggle },
  data() {
    return {
      error: "",
      loading: false,
      loadingDecisions: false,
      tracks: [],
      totalTracks: 0,
      activeCount: 0,
      selected: [],
      expanded: [],
      identities: [],
      activeTab: "active",
      filters: { status: null, camera_id: null, search: "", sort: "recent" },
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
      // Keyframes
      expandedKeyframes: {},
      keyframeLoading: {},
      keyframeDialogOpen: false,
      selectedKeyframe: null,
      // Camera filter options
      cameraOptions: [],
    };
  },
  computed: {
    trackHeaders() {
      return [
        { title: "", key: "thumbnail", sortable: false, width: 72 },
        { title: "Identity", key: "current_identity_id", sortable: false, width: 160 },
        { title: "Duration", key: "duration", sortable: false, width: 90 },
        { title: "Cameras", key: "camera_ids", sortable: false, width: 160 },
        { title: "Last seen", key: "last_seen_at", sortable: false, width: 120 },
        { title: "Best guess", key: "best_guess", sortable: false, width: 180 },
        { title: "", key: "actions", sortable: false, width: 210 },
      ];
    },
    statusOptions() {
      return [
        { title: "All", value: "" },
        { title: "Committed", value: "committed" },
        { title: "UNKNOWN", value: "UNKNOWN" },
      ];
    },
    sortOptions() {
      return [
        { title: "Most recent", value: "recent" },
        { title: "Longest duration", value: "duration_desc" },
        { title: "Highest confidence", value: "confidence_desc" },
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
    decisionGroups() {
      const byTrack = new Map();
      for (const d of this.decisions) {
        const gtid = d.global_track_id || "unknown";
        if (!byTrack.has(gtid)) {
          byTrack.set(gtid, {
            global_track_id: gtid,
            current_identity_id: d.new_identity_id,
            decisions: [],
          });
        }
        const group = byTrack.get(gtid);
        group.decisions.push(d);
        // The most recent decision's new_identity_id is the current state
        if (group.decisions.indexOf(d) === 0) {
          group.current_identity_id = d.new_identity_id;
        }
      }
      return [...byTrack.values()];
    },
  },
  mounted() {
    this.refreshAll();
  },
  watch: {
    expanded(newVal, oldVal) {
      const added = newVal.filter((v) => !oldVal.includes(v));
      const removed = oldVal.filter((v) => !newVal.includes(v));
      for (const item of added) {
        const id = item?.global_track_id;
        if (id) this.loadKeyframes(id);
      }
      for (const item of removed) {
        const id = item?.global_track_id;
        if (id && this.expandedKeyframes[id]) {
          const next = { ...this.expandedKeyframes };
          delete next[id];
          this.expandedKeyframes = next;
        }
      }
    },
  },
  methods: {
    formatRelative,
    frameUrl(minioKey) {
      if (!minioKey) return "";
      const encodedKey = minioKey.split("/").map(encodeURIComponent).join("/");
      const apiKey = encodeURIComponent(localStorage.getItem("cc_api_key") || "");
      return `/api/v1/cts/frames/${encodedKey}?api_key=${apiKey}`;
    },
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
    // Posterior helpers
    posteriorEntries(track) {
      const posterior = track.last_posterior_jsonb;
      if (!posterior || !posterior.distribution || !Object.keys(posterior.distribution).length) {
        return [];
      }
      const dist = posterior.distribution;
      return Object.entries(dist)
        .sort((a, b) => b[1] - a[1])
        .map(([label, prob]) => ({
          label,
          prob,
          pct: Math.max(prob * 100, 1.5),
          color: label === "UNKNOWN" ? "var(--cc-text-3)" : identityColor(label),
        }));
    },
    topPosteriorProb(track) {
      const entries = this.posteriorEntries(track);
      return entries.length > 0 ? entries[0].prob : 0;
    },
    trackDuration(track) {
      if (!track.started_at) return "—";
      const started = new Date(track.started_at);
      const ended = track.last_seen_at ? new Date(track.last_seen_at) : new Date();
      const sec = Math.round((ended - started) / 1000);
      if (sec < 60) return `${sec}s`;
      const min = Math.floor(sec / 60);
      if (min < 60) return `${min}m`;
      const hr = Math.floor(min / 60);
      const rem = min % 60;
      return rem ? `${hr}h ${rem}m` : `${hr}h`;
    },
    // Client-side sort (applied after server fetch)
    applySort(tracks) {
      if (this.filters.sort === "duration_desc") {
        return [...tracks].sort((a, b) => {
          const aDur = this._trackDurationSec(b);
          const bDur = this._trackDurationSec(a);
          return bDur - aDur;
        });
      }
      if (this.filters.sort === "confidence_desc") {
        return [...tracks].sort((a, b) => {
          const aConf = a.current_identity_id ? 1 : this.topPosteriorProb(a);
          const bConf = b.current_identity_id ? 1 : this.topPosteriorProb(b);
          return bConf - aConf;
        });
      }
      return tracks; // "recent" — server default
    },
    _trackDurationSec(track) {
      if (!track.started_at) return 0;
      const started = new Date(track.started_at);
      const ended = track.last_seen_at ? new Date(track.last_seen_at) : new Date();
      return Math.round((ended - started) / 1000);
    },
    // Filters
    onFilterChange() {
      this.pagination.page = 1;
      this.loadTracks();
    },
    debouncedSearch() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        this.pagination.page = 1;
        this.loadTracks();
      }, 300);
    },
    // Data loading
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
        const rawTracks = data.tracks || [];
        this.tracks = this.applySort(rawTracks);
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
    // Tabs
    onTabChange(tab) {
      this.selected = [];
      this.expanded = [];
      this.pagination.page = 1;
      if (tab === "decisions") {
        this.loadDecisions();
      } else {
        this.loadTracks();
      }
    },
    onTableOptions(opts) {
      if (opts.itemsPerPage !== this.pagination.itemsPerPage) {
        this.pagination.itemsPerPage = opts.itemsPerPage;
        this.pagination.page = 1;
      } else {
        this.pagination.page = opts.page;
      }
      this.loadTracks();
    },
    // Corrections
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
    async quickUnknown(track) {
      try {
        await cts.applyCorrection({
          global_track_id: track.global_track_id,
          new_identity_id: null,
          reason: "quick_unknown",
        });
        await this.loadTracks();
      } catch (err) {
        this.error = String(err.message || err);
      }
    },
    async loadKeyframes(globalTrackId) {
      this.keyframeLoading = { ...this.keyframeLoading, [globalTrackId]: true };
      try {
        const data = await cts.getTrackKeyframes(globalTrackId);
        this.expandedKeyframes = {
          ...this.expandedKeyframes,
          [globalTrackId]: data.keyframes || [],
        };
      } catch {
        this.expandedKeyframes = {
          ...this.expandedKeyframes,
          [globalTrackId]: [],
        };
      } finally {
        this.keyframeLoading = { ...this.keyframeLoading, [globalTrackId]: false };
      }
    },
    openKeyframeModal(kf) {
      this.selectedKeyframe = kf;
      this.keyframeDialogOpen = true;
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
        this.expanded = [];
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
/* Keyframe thumbnail */
.keyframe-thumb {
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.15s;
}
.keyframe-thumb:hover {
  border-color: rgb(var(--v-theme-primary));
}

/* Mini posterior bar (in best-guess column) */
.mini-posterior {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.06);
  min-width: 80px;
}
.mini-posterior-seg {
  transition: width 0.3s ease;
  min-width: 2px;
}

/* Expanded row */
.expanded-content {
  background: rgba(var(--v-theme-on-surface), 0.02);
}

/* Full-width posterior bar (in expanded row) */
.posterior-bar-lg {
  display: flex;
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.posterior-bar-lg-seg {
  transition: width 0.35s ease;
  min-width: 4px;
}

/* Posterior legend dot */
.posterior-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Monospace for IDs */
.font-mono {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
}
</style>
