<template>
  <v-card class="glass-card" data-test="member-prototypes-card">
    <div class="d-flex align-center flex-wrap ga-2 pa-4 pb-2">
      <div class="d-flex align-center ga-2">
        <v-icon size="18">mdi-view-grid-outline</v-icon>
        <span class="text-subtitle-1 font-weight-bold">Face Prototypes</span>
      </div>
      <v-chip v-if="data" size="x-small" variant="tonal" data-test="gallery-revision-chip">
        Revision {{ data.gallery_revision }}
      </v-chip>
      <v-spacer />
      <v-btn
        v-if="data && !forbidden"
        size="small"
        variant="tonal"
        prepend-icon="mdi-refresh"
        :loading="acting"
        :disabled="loading || acting"
        data-test="rebuild-prototypes"
        @click="onRebuild"
      >
        Rebuild
      </v-btn>
    </div>

    <v-card-text>
      <div v-if="loading" class="d-flex justify-center py-6" data-test="prototypes-loading">
        <v-progress-circular indeterminate color="primary" size="28" />
      </div>

      <v-alert
        v-else-if="forbidden"
        type="warning"
        variant="tonal"
        density="compact"
        data-test="prototypes-forbidden"
      >
        Viewing face prototypes requires caregiver permissions.
      </v-alert>

      <v-alert
        v-else-if="error"
        type="error"
        variant="tonal"
        density="compact"
        data-test="prototypes-error"
      >
        {{ error }}
        <template #append>
          <v-btn size="small" variant="text" @click="load">Retry</v-btn>
        </template>
      </v-alert>

      <div
        v-else-if="!data || data.prototypes.length === 0"
        class="text-body-2 text-medium-emphasis py-4 text-center"
        data-test="prototypes-empty"
      >
        No face prototypes yet. Enroll reference photos or promote labeled captures from Face
        calibration.
      </div>

      <div v-else>
        <div class="d-flex flex-wrap ga-2 mb-4" data-test="bin-counts">
          <v-chip
            v-for="bin in poseBins"
            :key="bin"
            size="small"
            variant="tonal"
            :color="(data.counts_by_bin?.[bin] ?? 0) > 0 ? 'primary' : undefined"
          >
            {{ POSE_LABELS[bin] ?? bin }}: {{ data.counts_by_bin?.[bin] ?? 0 }}
          </v-chip>
        </div>

        <div
          v-for="group in groupedPrototypes"
          :key="group.bin"
          class="mb-4"
          :data-test="`pose-group-${group.bin}`"
        >
          <div class="text-caption font-weight-semibold text-medium-emphasis mb-2">
            {{ POSE_LABELS[group.bin] ?? group.bin }} ({{ group.items.length }})
          </div>
          <div class="prototype-grid">
            <div
              v-for="proto in group.items"
              :key="proto.prototype_id"
              class="prototype-tile"
              :data-test="`prototype-${proto.prototype_id}`"
            >
              <img
                v-if="proto.crop_url"
                :src="proto.crop_url"
                :alt="`${group.bin} prototype crop`"
                class="prototype-tile__crop"
              />
              <div v-else class="prototype-tile__placeholder">
                <v-icon size="28" color="medium-emphasis">mdi-account-box-outline</v-icon>
              </div>
              <div class="prototype-tile__meta">
                <div class="text-caption font-weight-medium">
                  {{ sourceLabel(proto.source) }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ proto.member_count }} sample{{ proto.member_count === 1 ? "" : "s" }}
                  <span v-if="proto.quality_score != null">
                    · Q {{ proto.quality_score.toFixed(2) }}
                  </span>
                </div>
                <div v-if="proto.approved_by" class="text-caption text-medium-emphasis">
                  By {{ proto.approved_by }}
                  <span v-if="proto.approved_at"> · {{ formatDateTime(proto.approved_at) }} </span>
                </div>
              </div>
              <v-btn
                size="x-small"
                variant="text"
                color="error"
                :disabled="acting"
                :data-test="`delete-prototype-${proto.prototype_id}`"
                @click="onDelete(proto)"
              >
                Remove
              </v-btn>
            </div>
          </div>
        </div>
      </div>
    </v-card-text>

    <v-dialog v-model="confirmDialog" max-width="420" persistent>
      <v-card rounded="xl">
        <v-card-text class="pt-6">{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">{{ cancelLabel }}</v-btn>
          <v-btn :color="confirmColor" variant="flat" data-test="confirm" @click="onConfirm">{{
            confirmLabel
          }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ApiError } from "@/services/http";
import {
  deletePersonPrototype,
  listPersonPrototypes,
  rebuildPersonPrototypes,
  type PersonPrototypesResponse,
  type PersonPrototypeView,
} from "@/services/modules/face_calibration";
import { useConfirm } from "@/composables/useConfirm.js";
import { useNotify } from "@/composables/useNotify.js";
import { formatDateTime } from "@/services/timezone.js";

const CANONICAL_POSE_BINS = ["frontal", "left", "right", "down"] as const;
const POSE_LABELS: Record<string, string> = {
  frontal: "Frontal",
  left: "Left",
  right: "Right",
  down: "Looking down",
};

const SOURCE_LABELS: Record<string, string> = {
  enrollment: "Enrolled photo",
  enrollment_photo: "Enrolled photo",
  promoted_capture: "Promoted capture",
  visitor_naming: "Named visitor",
};

const props = defineProps<{
  personId: string;
}>();

const { notify } = useNotify();
const {
  confirmDialog,
  confirmText,
  confirmLabel,
  cancelLabel,
  confirmColor,
  require: confirmRequire,
  onConfirm,
  onCancel,
} = useConfirm();

const data = ref<PersonPrototypesResponse | null>(null);
const loading = ref(false);
const acting = ref(false);
const forbidden = ref(false);
const error = ref("");

const poseBins = computed(() => {
  const extras = Object.keys(data.value?.counts_by_bin ?? {})
    .filter((bin) => !(CANONICAL_POSE_BINS as readonly string[]).includes(bin))
    .sort();
  return [...CANONICAL_POSE_BINS, ...extras];
});

const groupedPrototypes = computed(() => {
  if (!data.value) return [];
  return poseBins.value
    .map((bin) => ({
      bin,
      items: data.value!.prototypes.filter((p) => p.pose_bin === bin),
    }))
    .filter((group) => group.items.length > 0);
});

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

async function load() {
  loading.value = true;
  error.value = "";
  forbidden.value = false;
  try {
    data.value = await listPersonPrototypes(props.personId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) {
      forbidden.value = true;
      data.value = null;
    } else if (err instanceof ApiError && err.status === 404) {
      data.value = null;
    } else {
      error.value = errorText(err);
    }
  } finally {
    loading.value = false;
  }
}

async function onRebuild() {
  if (acting.value) return;
  acting.value = true;
  try {
    const res = await rebuildPersonPrototypes(props.personId);
    notify.success(`Rebuilt ${res.prototype_count} prototype(s).`);
    await load();
  } catch (err) {
    notify.error(`Could not rebuild prototypes: ${errorText(err)}`);
  } finally {
    acting.value = false;
  }
}

async function onDelete(proto: PersonPrototypeView) {
  if (acting.value) return;
  const pose = POSE_LABELS[proto.pose_bin] ?? proto.pose_bin;
  const ok = await confirmRequire(
    `Remove this ${pose.toLowerCase()} prototype (${proto.member_count} sample${proto.member_count === 1 ? "" : "s"})? Its underlying embedding will be deleted and calibrated recognition authority for this person will pause until the next calibration fit.`,
    { confirmText: "Remove", color: "error" },
  );
  if (!ok) return;
  acting.value = true;
  try {
    await deletePersonPrototype(props.personId, proto.prototype_id);
    notify.success("Prototype removed. Refit calibration to restore recognition authority.");
    await load();
  } catch (err) {
    notify.error(`Could not remove prototype: ${errorText(err)}`);
  } finally {
    acting.value = false;
  }
}

watch(
  () => props.personId,
  () => void load(),
);
onMounted(() => void load());
</script>

<style scoped>
.prototype-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.prototype-tile {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  border-radius: var(--cc-radius-md);
  background: var(--cc-surface-2);
  border: 1px solid var(--cc-divider);
}
.prototype-tile__crop,
.prototype-tile__placeholder {
  width: 100%;
  aspect-ratio: 1;
  border-radius: var(--cc-radius-sm);
  background: var(--cc-surface-3);
  object-fit: cover;
}
.prototype-tile__crop {
  image-rendering: pixelated;
}
.prototype-tile__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
}
.prototype-tile__meta {
  flex: 1;
}
</style>
