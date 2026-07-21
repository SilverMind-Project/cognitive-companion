<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Visitors</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Recurring unnamed visitors surfaced from the household cameras. Name someone the household
          recognizes so they can be tracked like a household member.
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

    <div class="d-flex align-center ga-3 mb-4">
      <v-btn
        size="small"
        :variant="mergeMode ? 'flat' : 'outlined'"
        :color="mergeMode ? 'primary' : undefined"
        prepend-icon="mdi-call-merge"
        @click="toggleMergeMode"
      >
        {{ mergeMode ? "Cancel merge" : "Merge duplicates" }}
      </v-btn>
      <template v-if="mergeMode">
        <span class="text-body-2 text-medium-emphasis">
          Select two clusters that are the same person.
        </span>
        <v-chip v-if="state.mergeSelection.length" size="small" variant="tonal">
          {{ state.mergeSelection.length }} / 2 selected
        </v-chip>
        <v-btn
          size="small"
          color="primary"
          variant="flat"
          :disabled="state.mergeSelection.length !== 2"
          :loading="state.acting"
          @click="onMerge"
        >
          Merge selected
        </v-btn>
      </template>
    </div>

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
      <v-card-text class="text-grey text-h6">No visitors here yet</v-card-text>
      <v-card-text class="text-grey">
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
          :merge-mode="mergeMode"
          :selected="state.mergeSelection.includes(cluster.cluster_id)"
          @name="openNameDialog"
          @dismiss="onDismiss"
          @toggle-select="actions.toggleMergeSelection"
        />
      </v-col>
    </v-row>

    <VisitorNameDialog v-model="nameDialogOpen" :saving="state.acting" @submit="onName" />

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
import VisitorClusterCard from "@/components/admin/visitors/VisitorClusterCard.vue";
import VisitorNameDialog from "@/components/admin/visitors/VisitorNameDialog.vue";
import { useVisitorReview } from "@/composables/useVisitorReview.js";
import { useNotify } from "@/composables/useNotify.js";
import { useConfirm } from "@/composables/useConfirm.js";

const STATUS_OPTIONS = [
  { value: "surfaced", label: "Surfaced" },
  { value: "candidate", label: "Candidate" },
  { value: "named", label: "Named" },
  { value: "dismissed", label: "Dismissed" },
];

const { notify } = useNotify();
const { state, actions } = useVisitorReview(notify);
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

const mergeMode = ref(false);
const nameDialogOpen = ref(false);
const nameTargetId = ref(null);

function toggleMergeMode() {
  mergeMode.value = !mergeMode.value;
  actions.clearMergeSelection();
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

async function onDismiss(clusterId) {
  const ok = await confirmRequire(
    "Dismiss this cluster? It will no longer be surfaced for review.",
  );
  if (!ok) return;
  await actions.dismissCluster(clusterId).catch(() => {});
}

async function onMerge() {
  const ok = await confirmRequire("Merge these two clusters into one? This cannot be undone.");
  if (!ok) return;
  await actions.mergeSelected().catch(() => {});
  mergeMode.value = false;
}

onMounted(() => actions.loadList());
</script>
