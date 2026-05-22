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
        v-if="selected.length && !mergeMode"
        variant="tonal"
        color="warning"
        prepend-icon="mdi-checkbox-multiple-marked"
        class="mr-2"
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

    <!-- Filter bar (shared across Tracks tab; hidden on People + History) -->
    <v-card
      v-if="activeTab === 'tracks'"
      variant="flat"
      class="mb-4 px-4 py-2"
      border
    >
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
    <v-tabs
      v-model="activeTab"
      color="primary"
      class="mb-4"
      density="compact"
      @update:model-value="onTabChange"
    >
      <v-tab value="people">People</v-tab>
      <v-tab value="tracks">
        Tracks
        <v-chip size="x-small" variant="tonal" class="ml-1">{{ activeCount }}</v-chip>
      </v-tab>
      <v-tab value="decisions">History</v-tab>
    </v-tabs>

    <!-- ─────────────────────────────── TAB: People ─────────────────────────────── -->
    <div v-if="activeTab === 'people'">
      <div v-if="loadingPeople" class="d-flex justify-center pa-8">
        <v-progress-circular indeterminate />
      </div>
      <template v-else>
        <div v-if="identities.length" class="d-flex flex-column ga-3 mb-6">
          <PersonTrackCard
            v-for="identity in identities"
            :key="identity.identity_id"
            :identity="identity"
            :tracks="tracksByIdentity[identity.identity_id] || []"
            @open-track="openInspector($event, 'correct')"
            @correct-track="openInspector($event, 'correct')"
            @merge-fragments="openFragmentMergeDialog"
          />
        </div>
        <div v-else class="text-center pa-8 text-medium-emphasis">
          No identities enrolled. Add people in the gallery first.
        </div>

        <v-card variant="flat" border rounded="lg" class="pa-4">
          <UnknownTracksPanel
            :tracks="unknownTracks"
            :identities="identities"
            @open-track="openInspector($event, 'correct')"
            @assigned="onQuickAssign"
          />
        </v-card>
      </template>
    </div>

    <!-- ─────────────────────────────── TAB: Tracks ─────────────────────────────── -->
    <div v-else-if="activeTab === 'tracks'">
      <!-- Time-range toggle -->
      <div class="d-flex align-center ga-3 mb-3">
        <v-chip-group v-model="timeRange" mandatory @update:model-value="onTimeRangeChange">
          <v-chip value="active" filter size="small">Active now</v-chip>
          <v-chip value="24h"    filter size="small">Last 24 h</v-chip>
        </v-chip-group>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">{{ totalTracks }} track{{ totalTracks === 1 ? "" : "s" }}</span>
      </div>

      <!-- Merge mode toolbar -->
      <div v-if="timeRange === 'active'" class="d-flex align-center ga-3 mb-3">
        <v-btn
          :color="mergeMode ? 'warning' : 'default'"
          :variant="mergeMode ? 'flat' : 'outlined'"
          size="small"
          prepend-icon="mdi-merge"
          @click="toggleMergeMode"
        >
          {{ mergeMode ? 'Cancel merge' : 'Select to merge' }}
        </v-btn>
        <v-btn
          v-if="mergeMode && selected.length === 2"
          color="error"
          size="small"
          prepend-icon="mdi-call-merge"
          @click="openMergeDialog"
        >
          Merge 2 tracks
        </v-btn>
        <span v-if="mergeMode" class="text-caption text-medium-emphasis">
          Select exactly 2 tracks to merge. The first selected will be the default target.
        </span>
      </div>

      <v-card class="glass-card">
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
              :src="displaySrc(frameUrl(item.latest_keyframe_minio_key))"
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

          <!-- Best guess / evidence bar -->
          <template #item.best_guess="{ item }">
            <div v-if="item.current_identity_id" class="text-caption text-medium-emphasis">committed</div>
            <template v-else>
              <div v-if="posteriorEntries(item).length > 0" class="mini-posterior">
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
              <v-btn size="small" variant="tonal" prepend-icon="mdi-account-edit" @click="openInspector(item, 'correct')">
                Correct
              </v-btn>
              <v-btn size="small" variant="outlined" prepend-icon="mdi-merge" @click="openInspector(item, 'merge')">
                Merge
              </v-btn>
            </div>
          </template>

          <!-- Expanded row -->
          <template #expanded-row="{ columns, item, isExpanded }">
            <tr v-if="isExpanded" class="expanded-row">
              <td :colspan="columns.length" class="pa-0">
                <div class="expanded-content pa-4">
                  <v-row dense>
                    <!-- Posture distribution (new) -->
                    <v-col cols="12" md="4">
                      <div class="text-caption font-weight-medium mb-2">
                        <v-icon size="13" class="mr-1">mdi-human-greeting-variant</v-icon>
                        Posture Distribution
                      </div>
                      <PostureDistributionBar
                        :points="expandedTrail[item.global_track_id] || []"
                        :loading="trailLoading[item.global_track_id]"
                      />
                    </v-col>

                    <!-- Identity evidence -->
                    <v-col cols="12" md="4">
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
                            v-for="seg in posteriorEntries(item).slice(0, 4)"
                            :key="seg.label"
                            class="d-flex align-center ga-1"
                          >
                            <div class="posterior-dot" :style="{ background: seg.color }" />
                            <span class="text-caption">{{ seg.label }}</span>
                            <span class="text-caption text-medium-emphasis ml-1">
                              {{ (seg.prob * 100).toFixed(0) }}%
                            </span>
                          </div>
                        </div>
                      </div>
                      <span v-else class="text-caption text-medium-emphasis">No posterior evidence recorded.</span>
                    </v-col>

                    <!-- Keyframes + track info -->
                    <v-col cols="12" md="4">
                      <div class="text-caption font-weight-medium mb-2">Keyframes</div>
                      <div v-if="keyframeLoading[item.global_track_id]" class="d-flex align-center ga-2">
                        <v-progress-circular indeterminate size="16" width="2" />
                        <span class="text-caption text-medium-emphasis">Loading…</span>
                      </div>
                      <KeyframeStrip
                        v-else
                        :frames="expandedKeyframes[item.global_track_id] || []"
                        @click="openKeyframeBboxEditor"
                      />
                      <div class="d-flex flex-wrap ga-3 mt-2 text-caption text-medium-emphasis">
                        <span><span class="font-weight-medium text-on-surface">Started:</span> {{ formatRelative(item.started_at) }}</span>
                        <span><span class="font-weight-medium text-on-surface">Duration:</span> {{ trackDuration(item) }}</span>
                        <span><span class="font-weight-medium text-on-surface">Tracklets:</span> {{ (item.tracklet_ids || []).length }}</span>
                        <span><span class="font-weight-medium text-on-surface">State:</span> {{ item.state || "active" }}</span>
                      </div>
                    </v-col>
                  </v-row>

                  <!-- Quick actions -->
                  <div class="d-flex ga-2 mt-3 pt-3" style="border-top: 1px solid var(--cc-divider)">
                    <v-btn size="small" variant="tonal" prepend-icon="mdi-account-edit" @click="openInspector(item, 'correct')">
                      Correct identity
                    </v-btn>
                    <v-btn size="small" variant="outlined" prepend-icon="mdi-merge" @click="openInspector(item, 'merge')">
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
                Active tracks appear when a person is detected by a camera.
              </div>
            </div>
          </template>
        </v-data-table-server>
      </v-card>
    </div>

    <!-- ─────────────────────────────── TAB: History ─────────────────────────────── -->
    <v-card v-else-if="activeTab === 'decisions'" class="glass-card">
      <div class="pa-3 d-flex align-center ga-3">
        <v-chip-group v-model="decisionsKindFilter" @update:model-value="loadDecisions()">
          <v-chip value="" filter size="small">All</v-chip>
          <v-chip value="auto"           filter size="small">Auto-commit</v-chip>
          <v-chip value="manual_correct" filter size="small">Manual</v-chip>
          <v-chip value="manual_merge"   filter size="small">Merge</v-chip>
        </v-chip-group>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">
          {{ decisionGroups.length }} track{{ decisionGroups.length === 1 ? "" : "s" }}
        </span>
      </div>
      <v-divider />

      <v-list
        v-if="decisionGroups.length"
        density="compact"
        lines="two"
        v-model:opened="openedDecisionGroups"
      >
        <template v-for="group in decisionGroups" :key="group.global_track_id">
          <v-list-group :value="group.global_track_id">
            <template #activator="{ props: groupProps }">
              <v-list-item v-bind="groupProps" class="py-2">
                <template #prepend>
                  <v-avatar
                    size="36"
                    :color="group.current_identity_id ? 'primary' : 'warning'"
                    variant="tonal"
                    class="mr-3 flex-shrink-0"
                  >
                    <v-icon v-if="!group.current_identity_id" size="18">mdi-help-circle-outline</v-icon>
                    <span v-else class="text-caption font-weight-bold">
                      {{ identityInitial(group.current_identity_id) }}
                    </span>
                  </v-avatar>
                </template>
                <template #title>
                  <span class="font-weight-medium">
                    {{ identityDisplayName(group.current_identity_id) || "UNKNOWN" }}
                  </span>
                </template>
                <template #subtitle>
                  <span class="text-caption text-medium-emphasis">
                    {{ groupLatestTime(group) }}
                    &nbsp;·&nbsp;
                    {{ group.decisions.length }} revision{{ group.decisions.length !== 1 ? "s" : "" }}
                    &nbsp;·&nbsp;
                    {{ groupTotalRows(group) }} rows updated
                  </span>
                </template>
                <template #append>
                  <code class="text-caption text-disabled mr-2 font-mono decision-track-id">
                    {{ shortId(group.global_track_id) }}
                  </code>
                </template>
              </v-list-item>
            </template>

            <!-- ── Expanded: keyframe + decision timeline ── -->
            <div class="decision-expanded-body">
              <v-row dense class="ma-0">
                <!-- Keyframe column -->
                <v-col cols="12" sm="3" class="pa-4 decision-keyframe-col">
                  <div class="text-caption text-medium-emphasis mb-2 font-weight-medium">Latest frame</div>
                  <div
                    v-if="decisionKeyframeLoading[group.global_track_id]"
                    class="decision-keyframe-placeholder d-flex align-center justify-center"
                  >
                    <v-progress-circular indeterminate size="22" width="2" color="primary" />
                  </div>
                  <v-img
                    v-else-if="decisionKeyframes[group.global_track_id]"
                    :src="displaySrc(frameUrl(decisionKeyframes[group.global_track_id]))"
                    width="100%"
                    :aspect-ratio="4/3"
                    cover
                    rounded="lg"
                    class="decision-keyframe-img"
                  />
                  <div
                    v-else
                    class="decision-keyframe-placeholder d-flex align-center justify-center text-disabled"
                  >
                    <div class="text-center">
                      <v-icon size="28" class="mb-1">mdi-camera-off-outline</v-icon>
                      <div class="text-caption">No frame</div>
                    </div>
                  </div>
                  <v-btn
                    size="x-small"
                    variant="tonal"
                    class="mt-2 w-100"
                    prepend-icon="mdi-account-edit-outline"
                    @click.stop="openTrackFromHistory(group.global_track_id)"
                  >
                    Open inspector
                  </v-btn>
                </v-col>

                <!-- Decision timeline column -->
                <v-col cols="12" sm="9" class="pa-4 pl-sm-0">
                  <div class="text-caption text-medium-emphasis mb-3 font-weight-medium">
                    Decision timeline &mdash; newest first
                  </div>
                  <div class="decision-timeline">
                    <div
                      v-for="(d, idx) in group.decisions"
                      :key="d.revision_id"
                      class="decision-event"
                      :class="{ 'decision-event--last': idx === group.decisions.length - 1 }"
                    >
                      <!-- Connector line + dot -->
                      <div class="decision-event__track">
                        <div class="decision-event__dot" :class="'dot--' + d.kind">
                          <v-icon size="11" color="white">{{ kindIcon(d.kind) }}</v-icon>
                        </div>
                        <div v-if="idx < group.decisions.length - 1" class="decision-event__line" />
                      </div>

                      <!-- Event body -->
                      <div class="decision-event__body pb-5">
                        <!-- Row 1: kind + timestamp + actor -->
                        <div class="d-flex align-center flex-wrap ga-2 mb-2">
                          <v-chip size="x-small" :color="kindColor(d.kind)" variant="flat" class="font-weight-medium">
                            {{ kindLabel(d.kind) }}
                          </v-chip>
                          <span class="text-caption text-medium-emphasis">{{ formatRelative(d.applied_at) }}</span>
                          <span v-if="d.actor" class="text-caption text-disabled d-flex align-center ga-1">
                            <v-icon size="11">{{ actorIcon(d.actor) }}</v-icon>
                            {{ actorLabel(d.actor) }}
                          </span>
                        </div>

                        <!-- Row 2: identity transition -->
                        <div class="d-flex align-center flex-wrap ga-2 mb-2">
                          <v-chip size="small" variant="tonal" color="secondary" class="identity-chip">
                            <v-icon start size="12">mdi-account-outline</v-icon>
                            {{ identityDisplayName(d.previous_identity_id) || "UNKNOWN" }}
                          </v-chip>
                          <v-icon size="14" color="medium-emphasis">mdi-arrow-right</v-icon>
                          <v-chip
                            size="small"
                            variant="flat"
                            :color="d.new_identity_id ? 'success' : 'warning'"
                            class="identity-chip"
                          >
                            <v-icon start size="12">mdi-account-check-outline</v-icon>
                            {{ identityDisplayName(d.new_identity_id) || "UNKNOWN" }}
                          </v-chip>
                          <span class="text-caption text-disabled">
                            {{ d.rewritten_rows }} row{{ d.rewritten_rows !== 1 ? "s" : "" }} rewritten
                          </span>
                        </div>

                        <!-- Row 3: reason (humanised) -->
                        <div
                          v-if="d.reason"
                          class="text-caption text-medium-emphasis d-flex align-center ga-1 mb-2"
                        >
                          <v-icon size="12" color="medium-emphasis">mdi-comment-text-outline</v-icon>
                          {{ humaniseReason(d.reason) }}
                        </div>

                        <!-- Row 4: evidence bar -->
                        <template v-if="decisionEvidenceEntries(d).length">
                          <div class="text-caption text-disabled mb-1">Evidence at time of decision</div>
                          <div class="mini-posterior evidence-bar">
                            <div
                              v-for="seg in decisionEvidenceEntries(d)"
                              :key="seg.label"
                              class="mini-posterior-seg"
                              :style="{ width: seg.pct + '%', background: seg.color }"
                              :title="`${seg.label}: ${(seg.prob * 100).toFixed(1)}%`"
                            />
                          </div>
                          <div class="d-flex flex-wrap ga-3 mt-1">
                            <div
                              v-for="seg in decisionEvidenceEntries(d).slice(0, 4)"
                              :key="seg.label"
                              class="d-flex align-center ga-1"
                            >
                              <div class="posterior-dot" :style="{ background: seg.color }" />
                              <span class="text-caption">
                                {{ identityDisplayName(seg.label) || seg.label }}
                              </span>
                              <span class="text-caption text-medium-emphasis">
                                {{ (seg.prob * 100).toFixed(0) }}%
                              </span>
                            </div>
                          </div>
                        </template>
                      </div>
                    </div>
                  </div>
                </v-col>
              </v-row>
            </div>
          </v-list-group>
          <v-divider />
        </template>
      </v-list>

      <div v-else-if="!loadingDecisions" class="pa-8 text-center">
        <v-icon size="40" color="medium-emphasis" class="mb-2">mdi-history</v-icon>
        <div class="text-body-1 text-medium-emphasis">No identity decisions recorded yet</div>
        <div class="text-caption text-medium-emphasis mt-1">
          Decisions appear when the system auto-commits an identity or a manual correction is applied.
        </div>
      </div>

      <div v-if="decisionsHasMore" class="pa-3 text-center">
        <v-btn variant="tonal" size="small" :loading="loadingDecisions" @click="loadMoreDecisions">
          Load more
        </v-btn>
      </div>
    </v-card>

    <!-- Inspector drawer -->
    <v-navigation-drawer v-model="drawerOpen" location="right" width="480" temporary class="cc-drawer-right">
      <IdentityInspectorDrawer
        v-if="inspectorTrack"
        :track="inspectorTrack"
        :mode="drawerMode"
        :identities="identities"
        @apply="onDrawerApply"
        @close="drawerOpen = false"
        @keyframe-click="openKeyframeBboxEditor"
        @refresh="loadTracks"
      />
    </v-navigation-drawer>

    <!-- Bulk UNKNOWN dialog -->
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
          <v-btn variant="flat" color="warning" :loading="bulkSaving" @click="executeBulk">Confirm</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Merge confirmation dialog -->
    <v-dialog v-model="mergeDialog" max-width="500">
      <v-card rounded="xl">
        <v-card-title>Merge Global Tracks</v-card-title>
        <v-card-text>
          <p>Select which track to keep (target). The other will be tombstoned.</p>
          <template v-if="selected.length === 2">
            <v-radio-group v-model="mergeTarget">
              <v-radio
                v-for="gt in selected"
                :key="gt.global_track_id"
                :value="gt.global_track_id"
              >
                <template #label>
                  <div>
                    <span class="font-weight-medium">{{ identityLabel(gt) }}</span>
                    <span class="text-caption text-medium-emphasis ml-2">
                      ({{ (gt.tracklet_ids || []).length }} tracklets, {{ trackDuration(gt) }})
                    </span>
                  </div>
                </template>
              </v-radio>
            </v-radio-group>
          </template>
          <v-alert type="warning" variant="tonal" density="compact" class="mt-4">
            All trajectory, dwell, and signal data from the source track will be re-attributed to the target. This cannot be automatically reversed.
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="mergeDialog = false">Cancel</v-btn>
          <v-btn
            color="error"
            :disabled="!mergeTarget"
            :loading="merging"
            @click="executeMerge"
          >
            Merge
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Keyframe Annotation Dialog -->
    <KeyframeAnnotationDialog
      v-model="keyframeBboxDialog"
      :image-url="bboxEditorImageUrl"
      :keyframe-id="bboxEditorKeyframe?.sample_id || bboxEditorKeyframe?.keyframe_id || ''"
      :identities="identities"
      @saved="onAnnotationSaved"
      @error="error = $event"
    />
  </div>
</template>

<script>
import { cts } from "@/services/cts";
import { formatRelative } from "@/composables/useFormatRelative";
import { identityColor } from "@/composables/useIdentityColor";
import { useBlurMode, useDisplaySrc } from "@/composables/useBlurMode";
import IdentityInspectorDrawer from "@/components/cts/identity/IdentityInspectorDrawer.vue";
import KeyframeStrip from "@/components/cts/identity/KeyframeStrip.vue";
import KeyframeAnnotationDialog from "@/components/cts/keyframes/KeyframeAnnotationDialog.vue";
import PersonTrackCard from "@/components/cts/identity/PersonTrackCard.vue";
import PostureDistributionBar from "@/components/cts/identity/PostureDistributionBar.vue";
import UnknownTracksPanel from "@/components/cts/identity/UnknownTracksPanel.vue";
import BlurToggle from "@/components/cts/BlurToggle.vue";

let searchTimer = null;

export default {
  name: "CTSIdentityCorrectionsView",

  setup() {
    const { blurMode } = useBlurMode();
    const { displaySrc } = useDisplaySrc(blurMode);
    return { blurMode, displaySrc };
  },

  components: {
    IdentityInspectorDrawer,
    KeyframeStrip,
    KeyframeAnnotationDialog,
    PersonTrackCard,
    PostureDistributionBar,
    UnknownTracksPanel,
    BlurToggle,
  },

  data() {
    return {
      error: "",
      loading: false,
      loadingDecisions: false,
      loadingPeople: false,
      tracks: [],
      totalTracks: 0,
      activeCount: 0,
      selected: [],
      expanded: [],
      identities: [],
      allTodayTracks: [],
      activeTab: "people",
      timeRange: "active",   // "active" | "24h" — used by Tracks tab
      filters: { status: null, camera_id: null, search: "", sort: "recent" },
      showTransient: false,
      pagination: { page: 1, itemsPerPage: 24 },
      // Decisions
      decisions: [],
      decisionsHasMore: false,
      decisionsKindFilter: "",
      decisionsCursor: null,
      openedDecisionGroups: [],
      decisionKeyframes: {},
      decisionKeyframeLoading: {},
      // Drawer
      drawerOpen: false,
      drawerMode: "correct",
      inspectorTrack: null,
      // Bulk
      bulkDialogOpen: false,
      bulkSaving: false,
      // Merge mode
      mergeMode: false,
      mergeDialog: false,
      mergeTarget: null,
      merging: false,
      // Keyframes (expanded rows)
      expandedKeyframes: {},
      keyframeLoading: {},
      // Trail / posture (expanded rows)
      expandedTrail: {},
      trailLoading: {},
      // Bbox annotation editor
      keyframeBboxDialog: false,
      bboxEditorKeyframe: null,
      // Camera options (populated from loaded tracks)
      cameraOptions: [],
    };
  },

  computed: {
    tracksByIdentity() {
      const byId = {};
      for (const t of this.allTodayTracks) {
        if (t.current_identity_id) {
          (byId[t.current_identity_id] = byId[t.current_identity_id] || []).push(t);
        }
      }
      return byId;
    },
    bboxEditorImageUrl() {
      const kf = this.bboxEditorKeyframe;
      if (!kf) return "";
      if (kf.image_url) return kf.image_url;
      return this.frameUrl(kf.minio_key);
    },
    unknownTracks() {
      return this.allTodayTracks.filter((t) => !t.current_identity_id && t.state === "active");
    },
    trackHeaders() {
      return [
        { title: "",            key: "thumbnail",           sortable: false, width: 72  },
        { title: "Identity",    key: "current_identity_id", sortable: false, width: 160 },
        { title: "Duration",    key: "duration",            sortable: false, width: 90  },
        { title: "Cameras",     key: "camera_ids",          sortable: false, width: 160 },
        { title: "Last seen",   key: "last_seen_at",        sortable: false, width: 120 },
        { title: "Best guess",  key: "best_guess",          sortable: false, width: 180 },
        { title: "",            key: "actions",             sortable: false, width: 210 },
      ];
    },
    statusOptions() {
      return [
        { title: "All",       value: ""          },
        { title: "Committed", value: "committed" },
        { title: "UNKNOWN",   value: "UNKNOWN"   },
      ];
    },
    sortOptions() {
      return [
        { title: "Most recent",        value: "recent"         },
        { title: "Longest duration",   value: "duration_desc"  },
        { title: "Highest confidence", value: "confidence_desc" },
      ];
    },
    identityMap() {
      const m = {};
      for (const id of this.identities) m[id.identity_id] = id.display_name || id.identity_id;
      return m;
    },
    decisionGroups() {
      const byTrack = new Map();
      for (const d of this.decisions) {
        const gtid = d.global_track_id || "unknown";
        if (!byTrack.has(gtid)) {
          // Decisions arrive newest-first from the server; first seen = most recent state.
          byTrack.set(gtid, { global_track_id: gtid, current_identity_id: d.new_identity_id, decisions: [] });
        }
        byTrack.get(gtid).decisions.push(d);
      }
      return [...byTrack.values()];
    },
  },

  mounted() {
    this.refreshAll();
    this.loadPeopleTab();
  },

  watch: {
    openedDecisionGroups(newVal, oldVal) {
      const added = newVal.filter((v) => !oldVal.includes(v));
      for (const gtid of added) {
        this.loadDecisionKeyframe(gtid);
      }
    },

    expanded(newVal, oldVal) {
      const added   = newVal.filter((v) => !oldVal.includes(v));
      const removed = oldVal.filter((v) => !newVal.includes(v));
      for (const item of added) {
        const id = item?.global_track_id;
        if (id) {
          this.loadKeyframes(id);
          this.loadTrail(id);
        }
      }
      for (const item of removed) {
        const id = item?.global_track_id;
        if (!id) continue;
        if (this.expandedKeyframes[id]) {
          const next = { ...this.expandedKeyframes };
          delete next[id];
          this.expandedKeyframes = next;
        }
        if (this.expandedTrail[id]) {
          const next = { ...this.expandedTrail };
          delete next[id];
          this.expandedTrail = next;
        }
      }
    },
  },

  methods: {
    formatRelative,

    // ── URL helpers ─────────────────────────────────────────────────────────
    frameUrl(minioKey) {
      if (!minioKey) return "";
      const encoded = minioKey.split("/").map(encodeURIComponent).join("/");
      const apiKey  = encodeURIComponent(localStorage.getItem("cc_api_key") || "");
      return `/api/v1/cts/frames/${encoded}?api_key=${apiKey}`;
    },

    // ── Identity helpers ────────────────────────────────────────────────────
    identityLabel(track) {
      if (!track?.current_identity_id) return "UNKNOWN";
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

    // ── Decision log helpers ────────────────────────────────────────────────
    kindColor(kind) {
      return kind === "auto" ? "info" : kind === "manual_merge" ? "primary" : "warning";
    },
    kindLabel(kind) {
      return kind === "auto" ? "Auto-commit" : kind === "manual_merge" ? "Merge" : "Manual";
    },
    kindIcon(kind) {
      return kind === "auto" ? "mdi-robot-outline" : kind === "manual_merge" ? "mdi-merge" : "mdi-account-edit-outline";
    },
    actorIcon(actor) {
      return actor === "system" || actor === "resolver" ? "mdi-robot-outline" : "mdi-account-outline";
    },
    actorLabel(actor) {
      if (!actor || actor === "system" || actor === "resolver") return "System";
      return actor;
    },
    humaniseReason(reason) {
      if (!reason) return "";
      const map = {
        quick_unknown: "Marked as UNKNOWN via quick action",
        quick_assign_people_tab: "Quick-assigned from People tab",
        bulk_confirm_unknown: "Bulk confirmed UNKNOWN",
        auto_commit: "Auto-committed by identity resolver",
      };
      return map[reason] || reason.replace(/_/g, " ");
    },
    identityInitial(identityId) {
      if (!identityId) return "?";
      const name = this.identityMap[identityId] || identityId;
      return name.charAt(0).toUpperCase();
    },
    groupLatestTime(group) {
      if (!group.decisions.length) return "";
      // Decisions are newest-first; index 0 is the most recent.
      return formatRelative(group.decisions[0].applied_at);
    },
    groupTotalRows(group) {
      return group.decisions.reduce((sum, d) => sum + (d.rewritten_rows || 0), 0);
    },
    decisionEvidenceEntries(d) {
      const ev = d.evidence;
      if (!ev?.distribution || !Object.keys(ev.distribution).length) return [];
      return Object.entries(ev.distribution)
        .sort((a, b) => b[1] - a[1])
        .map(([label, prob]) => ({
          label,
          prob,
          pct: Math.max(prob * 100, 1.5),
          color: label === "UNKNOWN" ? "var(--cc-text-3)" : identityColor(label),
        }));
    },
    async loadDecisionKeyframe(globalTrackId) {
      if (
        this.decisionKeyframes[globalTrackId] !== undefined ||
        this.decisionKeyframeLoading[globalTrackId]
      ) return;
      this.decisionKeyframeLoading = { ...this.decisionKeyframeLoading, [globalTrackId]: true };
      try {
        const data = await cts.getTrackKeyframes(globalTrackId);
        const frames = data.keyframes || [];
        this.decisionKeyframes = {
          ...this.decisionKeyframes,
          [globalTrackId]: frames[0]?.minio_key ?? null,
        };
      } catch {
        this.decisionKeyframes = { ...this.decisionKeyframes, [globalTrackId]: null };
      } finally {
        this.decisionKeyframeLoading = { ...this.decisionKeyframeLoading, [globalTrackId]: false };
      }
    },
    async openTrackFromHistory(globalTrackId) {
      try {
        const data = await cts.getGlobalTrackDetail(globalTrackId);
        if (data) {
          this.openInspector(data, "correct");
        }
      } catch (err) {
        this.error = String(err.message || err);
      }
    },

    // ── Posterior helpers ───────────────────────────────────────────────────
    posteriorEntries(track) {
      const posterior = track.last_posterior_jsonb;
      if (!posterior?.distribution || !Object.keys(posterior.distribution).length) return [];
      return Object.entries(posterior.distribution)
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
      return entries.length ? entries[0].prob : 0;
    },

    // ── Duration formatting ─────────────────────────────────────────────────
    trackDuration(track) {
      if (!track.started_at) return "—";
      const started = new Date(track.started_at);
      const ended   = track.last_seen_at ? new Date(track.last_seen_at) : new Date();
      const sec     = Math.round((ended - started) / 1000);
      if (sec < 60) return `${sec}s`;
      const min = Math.floor(sec / 60);
      if (min < 60) return `${min}m`;
      const hr  = Math.floor(min / 60);
      const rem = min % 60;
      return rem ? `${hr}h ${rem}m` : `${hr}h`;
    },
    _trackDurationSec(track) {
      if (!track.started_at) return 0;
      const started = new Date(track.started_at);
      const ended   = track.last_seen_at ? new Date(track.last_seen_at) : new Date();
      return Math.round((ended - started) / 1000);
    },

    // ── Client-side sort ────────────────────────────────────────────────────
    applySort(tracks) {
      if (this.filters.sort === "duration_desc") {
        return [...tracks].sort((a, b) => this._trackDurationSec(b) - this._trackDurationSec(a));
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

    // ── Filter / pagination callbacks ───────────────────────────────────────
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
    onTimeRangeChange() {
      this.pagination.page = 1;
      this.loadTracks();
    },

    // ── Data loading ────────────────────────────────────────────────────────
    async refreshAll() {
      await Promise.all([this.loadTracks(), this.loadIdentities()]);
    },
    async loadPeopleTab() {
      this.loadingPeople = true;
      try {
        const now = new Date();
        const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
        const data = await cts.getGlobalTracks({
          open_only: false,
          since: todayStart.toISOString(),
          limit: 500,
          include_transient: false,
          min_duration_s: 5,
        });
        this.allTodayTracks = data.tracks || [];
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.loadingPeople = false;
      }
    },
    async loadTracks() {
      this.loading = true;
      try {
        const params = {
          open_only: this.timeRange === "active",
          limit:  this.pagination.itemsPerPage,
          offset: (this.pagination.page - 1) * this.pagination.itemsPerPage,
        };
        if (this.filters.status)    params.status    = this.filters.status;
        if (this.filters.camera_id) params.camera_id = this.filters.camera_id;
        if (this.filters.search)    params.search    = this.filters.search;
        params.include_transient = this.showTransient;
        if (!this.showTransient)    params.min_duration_s = 10;

        const data      = await cts.getGlobalTracks(params);
        const rawTracks = data.tracks || [];
        this.tracks     = this.applySort(rawTracks);
        this.totalTracks = data.count || this.tracks.length;
        if (this.timeRange === "active") {
          this.activeCount = this.totalTracks;
        }

        // Rebuild camera filter options from current page.
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
        const data   = await cts.getIdentities();
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
        this.decisions         = data.decisions || [];
        this.decisionsHasMore  = data.has_more || false;
        this.decisionsCursor   = this.decisions.length
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
        const data       = await cts.getDecisions(params);
        const newDecisions = data.decisions || [];
        this.decisions   = [...this.decisions, ...newDecisions];
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

    // ── Keyframe loading (expanded row) ─────────────────────────────────────
    async loadKeyframes(globalTrackId) {
      this.keyframeLoading = { ...this.keyframeLoading, [globalTrackId]: true };
      try {
        const data = await cts.getTrackKeyframes(globalTrackId);
        this.expandedKeyframes = { ...this.expandedKeyframes, [globalTrackId]: data.keyframes || [] };
      } catch {
        this.expandedKeyframes = { ...this.expandedKeyframes, [globalTrackId]: [] };
      } finally {
        this.keyframeLoading = { ...this.keyframeLoading, [globalTrackId]: false };
      }
    },

    // ── Trail / posture loading (expanded row) ───────────────────────────────
    async loadTrail(globalTrackId) {
      this.trailLoading = { ...this.trailLoading, [globalTrackId]: true };
      try {
        const track = this.tracks.find((t) => t.global_track_id === globalTrackId);
        const since = track?.started_at ?? undefined;
        const data = await cts.getTrackTrail(globalTrackId, { since });
        this.expandedTrail = { ...this.expandedTrail, [globalTrackId]: data.points || [] };
      } catch {
        this.expandedTrail = { ...this.expandedTrail, [globalTrackId]: [] };
      } finally {
        this.trailLoading = { ...this.trailLoading, [globalTrackId]: false };
      }
    },

    // ── Tab routing ──────────────────────────────────────────────────────────
    onTabChange(tab) {
      this.selected = [];
      this.expanded = [];
      this.mergeMode = false;
      this.pagination.page = 1;
      if (tab === "people") {
        this.loadPeopleTab();
        if (!this.identities.length) this.loadIdentities();
      } else if (tab === "decisions") {
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

    // ── People-tab helpers ───────────────────────────────────────────────────
    openFragmentMergeDialog(tracks) {
      if (tracks.length) this.openInspector(tracks[0], "merge");
    },
    async onQuickAssign({ track, identity_id }) {
      try {
        await cts.applyCorrection({
          global_track_id: track.global_track_id,
          new_identity_id: identity_id,
          reason: "quick_assign_people_tab",
        });
        await this.loadPeopleTab();
      } catch (err) {
        this.error = String(err.message || err);
      }
    },

    // ── Corrections ──────────────────────────────────────────────────────────
    openInspector(track, mode) {
      this.drawerMode    = mode;
      this.inspectorTrack = track;
      this.drawerOpen    = true;
    },
    async onDrawerApply(form) {
      try {
        if (this.drawerMode === "merge") {
          await cts.mergeIdentities({
            global_track_id: this.inspectorTrack.global_track_id,
            from_identity_id: form.from_identity_id,
            to_identity_id:   form.new_identity_id,
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

    // ── Bulk ─────────────────────────────────────────────────────────────────
    confirmBulkUnknown() { this.bulkDialogOpen = true; },
    async executeBulk() {
      this.bulkSaving = true;
      try {
        const corrections = this.selected.map((t) => ({
          global_track_id: t.global_track_id,
          new_identity_id: null,
          reason: "bulk_confirm_unknown",
        }));
        await cts.batchCorrect(corrections);
        this.selected      = [];
        this.expanded      = [];
        this.bulkDialogOpen = false;
        await this.loadTracks();
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.bulkSaving = false;
      }
    },

    // ── Merge ────────────────────────────────────────────────────────────────
    toggleMergeMode() {
      this.mergeMode = !this.mergeMode;
      if (!this.mergeMode) this.selected = [];
    },
    openMergeDialog() {
      this.mergeTarget = this.selected[0]?.global_track_id || null;
      this.mergeDialog = true;
    },
    async executeMerge() {
      if (!this.mergeTarget) return;
      const source = this.selected.find((gt) => gt.global_track_id !== this.mergeTarget);
      if (!source) return;
      this.merging = true;
      try {
        await cts.mergeGlobalTracks(source.global_track_id, this.mergeTarget);
        this.mergeDialog = false;
        this.mergeMode = false;
        this.selected = [];
        await this.loadTracks();
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.merging = false;
      }
    },

    // ── Keyframe Annotation Editor ───────────────────────────────────────────
    openKeyframeBboxEditor(kf) {
      if (!kf) return;
      this.bboxEditorKeyframe = kf;
      if (!this.identities.length) {
        cts.getIdentities()
          .then((d) => { this.identities = d.identities || []; })
          .catch(() => {});
      }
      this.keyframeBboxDialog = true;
    },
    onAnnotationSaved() {
      this.loadTracks();
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
.keyframe-thumb:hover { border-color: rgb(var(--v-theme-primary)); }

/* Mini posterior bar (best-guess column) */
.mini-posterior {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.06);
  min-width: 80px;
}
.mini-posterior-seg { transition: width 0.3s ease; min-width: 2px; }

/* Expanded row */
.expanded-content { background: rgba(var(--v-theme-on-surface), 0.02); }

/* Full-width posterior bar (expanded row) */
.posterior-bar-lg {
  display: flex;
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.posterior-bar-lg-seg { transition: width 0.35s ease; min-width: 4px; }

/* Legend dot */
.posterior-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

/* Monospace IDs */
.font-mono { font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace; }
.decision-track-id { font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace; font-size: 0.7rem; }

/* ─── Decision history expanded area ─── */
.decision-expanded-body {
  background: rgba(var(--v-theme-on-surface), 0.02);
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}

.decision-keyframe-col {
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}

.decision-keyframe-img {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}

.decision-keyframe-placeholder {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.15);
}

/* ─── Vertical decision timeline ─── */
.decision-timeline { padding-top: 2px; }

.decision-event {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.decision-event__track {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 20px;
}

.decision-event__dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.dot--auto          { background: rgb(var(--v-theme-info)); }
.dot--manual_correct { background: rgb(var(--v-theme-warning)); }
.dot--manual_merge  { background: rgb(var(--v-theme-primary)); }

.decision-event__line {
  width: 2px;
  flex: 1;
  min-height: 20px;
  background: rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 1px;
  margin-top: 4px;
}

.decision-event__body {
  flex: 1;
  min-width: 0;
}

.identity-chip { max-width: 180px; }
.identity-chip :deep(.v-chip__content) { overflow: hidden; text-overflow: ellipsis; }

.evidence-bar {
  min-width: 140px;
  max-width: 260px;
  height: 8px;
  border-radius: 4px;
}

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
