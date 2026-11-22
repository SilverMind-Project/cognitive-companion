<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Visitors</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Faces the cameras keep seeing but cannot match to anyone. Many are faces of people already
          enrolled, seen at an angle or from far away: mark those as theirs. Name only someone new,
          and dismiss the rest.
        </div>
      </div>
      <v-spacer />
      <CcSegmentedToggle
        :model-value="state.statusFilter"
        :options="STATUS_OPTIONS"
        size="default"
        @update:model-value="actions.setStatusFilter"
      />
    </div>

    <ReviewSelectionToolbar
      class="mb-4"
      :active="selectMode"
      :selectable-count="state.clusters.length"
      :selected-count="state.selection.length"
      @update:active="toggleSelectMode"
      @select-all="selectAll"
      @clear="actions.clearSelection"
    >
      <v-btn
        size="small"
        color="primary"
        variant="flat"
        prepend-icon="mdi-account-check-outline"
        :disabled="!state.selection.length"
        :loading="state.acting"
        data-test="attribute-selected"
        @click="openAttribute(state.selection)"
      >
        {{ VERDICT_LABELS.is_member }}
      </v-btn>
      <v-btn
        size="small"
        variant="outlined"
        prepend-icon="mdi-close"
        :disabled="!state.selection.length"
        :loading="state.acting"
        data-test="dismiss-selected"
        @click="onDismiss(state.selection)"
      >
        {{ VISITOR_DISMISS_LABEL }}
      </v-btn>
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-call-merge"
        :disabled="state.selection.length !== 2"
        :loading="state.acting"
        data-test="merge-selected"
        @click="onMerge"
      >
        Merge two
      </v-btn>
    </ReviewSelectionToolbar>

    <v-alert
      v-if="state.disabled"
      type="warning"
      variant="tonal"
      density="comfortable"
      class="mb-4"
    >
      Visitor clustering is currently disabled. Existing surfaced clusters can still be reviewed,
      but new visitors will not be captured until it is re-enabled.
    </v-alert>

    <v-alert v-if="state.listError" type="error" variant="tonal" class="mb-4">
      {{ state.listError }}
    </v-alert>

    <div v-if="state.listLoading" class="d-flex justify-center pa-8">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <v-card v-else-if="!state.clusters.length" flat class="pa-8 text-center glass-card">
      <v-card-text class="text-medium-emphasis text-h6">No visitors here yet</v-card-text>
      <v-card-text class="text-medium-emphasis">
        A visitor is surfaced for review once the same face has been seen on 3 distinct days within
        30 days. Unnamed clusters are purged automatically after 60 days without a sighting. If
        clustering has been turned off, no new visitors will be captured.
      </v-card-text>
    </v-card>

    <v-row v-else>
      <v-col
        v-for="cluster in state.clusters"
        :key="cluster.cluster_id"
        cols="12"
        sm="6"
        md="4"
        lg="3"
      >
        <VisitorClusterCard
          :cluster="cluster"
          :select-mode="selectMode"
          :selected="state.selection.includes(cluster.cluster_id)"
          @name="openNameDialog"
          @attribute="(id) => openAttribute([id])"
          @dismiss="(id) => onDismiss([id])"
          @toggle-select="actions.toggleSelection"
        />
      </v-col>
    </v-row>

    <VisitorNameDialog
      v-model="nameDialogOpen"
      :saving="state.acting"
      @submit="onName"
      @attribute="onNameAsExisting"
    />
    <VisitorAttributeDialog
      v-model="attributeDialogOpen"
      :count="attributeIds.length"
      :saving="state.acting"
      @submit="onAttribute"
    />

    <v-dialog v-model="confirmDialog" max-width="400" persistent>
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
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";
import ReviewSelectionToolbar from "@/components/identity/ReviewSelectionToolbar.vue";
import VisitorClusterCard from "@/components/admin/visitors/VisitorClusterCard.vue";
import VisitorAttributeDialog from "@/components/admin/visitors/VisitorAttributeDialog.vue";
import VisitorNameDialog from "@/components/admin/visitors/VisitorNameDialog.vue";
import { VERDICT_LABELS, VISITOR_DISMISS_LABEL } from "@/constants/identityReview";
import { useIdentityReviewStore } from "@/stores/identityReview";
import { useVisitorReview } from "@/composables/useVisitorReview.js";
import { useNotify } from "@/composables/useNotify.js";
import { useConfirm } from "@/composables/useConfirm.js";

const STATUS_OPTIONS = [
  { value: "surfaced", label: "Surfaced" },
  { value: "candidate", label: "Candidate" },
  { value: "attributed", label: "Marked as member" },
  { value: "named", label: "Named" },
  { value: "dismissed", label: "Dismissed" },
];

const { notify } = useNotify();
const { state, actions } = useVisitorReview(notify);
const review = useIdentityReviewStore();
const {
  confirmDialog,
  confirmTitle,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  require: confirmRequire,
  onConfirm,
  onCancel,
} = useConfirm();

const selectMode = ref(false);
const nameDialogOpen = ref(false);
const nameTargetId = ref(null);
const attributeDialogOpen = ref(false);
const attributeIds = ref([]);

function toggleSelectMode() {
  selectMode.value = !selectMode.value;
  actions.clearSelection();
}

function selectAll() {
  for (const c of state.clusters) {
    if (!state.selection.includes(c.cluster_id)) actions.toggleSelection(c.cluster_id);
  }
}

function openAttribute(clusterIds) {
  attributeIds.value = [...clusterIds];
  attributeDialogOpen.value = true;
}

async function onAttribute(identityId) {
  try {
    await actions.review(attributeIds.value, "is_member", identityId);
    attributeDialogOpen.value = false;
  } catch {
    // Error surfaced via notify inside the composable; keep the dialog open for a retry.
  }
}

function onNameAsExisting(identityId) {
  nameDialogOpen.value = false;
  attributeIds.value = [nameTargetId.value];
  actions.review(attributeIds.value, "is_member", identityId).catch(() => {});
}

function openNameDialog(cluster) {
  nameTargetId.value = cluster.cluster_id;
  nameDialogOpen.value = true;
}

async function onName({ name, personId }) {
  try {
    await actions.nameCluster(nameTargetId.value, { name, personId });
    nameDialogOpen.value = false;
  } catch {
    // Error surfaced via notify inside the composable; keep the dialog open for a retry.
  }
}

async function onDismiss(clusterIds) {
  const what = clusterIds.length === 1 ? "this group" : `these ${clusterIds.length} groups`;
  const ok = await confirmRequire(`Dismiss ${what}? ${review.effect("visitors", "not_usable")}`);
  if (!ok) return;
  await actions.review([...clusterIds], "not_usable").catch(() => {});
}

async function onMerge() {
  const ok = await confirmRequire("Merge these two clusters into one? This cannot be undone.");
  if (!ok) return;
  await actions.mergeSelected().catch(() => {});
}

onMounted(() => {
  void review.load();
  void actions.loadList();
});
</script>
