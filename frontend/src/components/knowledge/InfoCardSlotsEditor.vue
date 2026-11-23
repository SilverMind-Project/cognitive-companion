<template>
  <v-card v-if="slotDefs.length > 0" variant="tonal" class="mb-3 pa-3">
    <div class="text-subtitle-2 mb-3">Image Slots</div>
    <div v-for="(slotDef, idx) in slotDefs" :key="idx" class="mb-3">
      <div class="text-caption mb-1">Slot {{ idx }}: {{ slotDef.slot_id }}</div>
      <div class="d-flex align-center ga-2 flex-wrap">
        <v-sheet v-if="preview(idx)" width="80" height="60" class="rounded-lg overflow-hidden">
          <v-img :src="preview(idx)" height="60" cover />
        </v-sheet>
        <v-sheet
          v-else
          width="80"
          height="60"
          class="rounded-lg bg-surface-variant d-flex align-center justify-center"
        >
          <v-icon size="24" color="var(--cc-text-3)">mdi-image-outline</v-icon>
        </v-sheet>

        <v-btn size="small" variant="tonal" prepend-icon="mdi-image-plus" @click="chooseFile(idx)">
          {{ fileNames[idx] || "Choose" }}
        </v-btn>
        <v-btn
          v-if="files[idx]"
          size="small"
          color="primary"
          variant="tonal"
          :loading="busy[idx]"
          @click="upload(idx)"
        >
          Save
        </v-btn>

        <v-btn
          v-if="documentImages.length > 0"
          size="small"
          variant="tonal"
          @click="pickerIdx = pickerIdx === idx ? -1 : idx"
        >
          Pick from Document
        </v-btn>

        <v-btn
          v-if="preview(idx)"
          size="small"
          color="error"
          variant="text"
          icon="mdi-delete"
          :loading="busy[idx]"
          @click="clear(idx)"
        />
      </div>

      <div v-if="pickerIdx === idx" class="d-flex ga-2 flex-wrap mt-2">
        <v-img
          v-for="docImg in documentImages"
          :key="docImg.id"
          :src="docImg.presigned_url"
          width="80"
          height="60"
          cover
          class="rounded-lg"
          style="cursor: pointer; border: 2px solid transparent"
          @click="
            pick(idx, docImg.id);
            pickerIdx = -1;
          "
        />
      </div>
    </div>

    <input ref="fileInput" type="file" accept="image/*" hidden @change="onFilePicked" />
  </v-card>
</template>

<script setup>
import { reactive, ref } from "vue";
import { deleteInfoCardSlot, getInfoCard, setInfoCardSlot } from "@/services/modules/info_cards";
import { useNotify } from "@/composables/useNotify.js";

/**
 * Image slots of a saved info card. Each change is saved at once (slots are not part of the
 * card dialog's Save), then the card's stored slots are re-read and emitted.
 */
const props = defineProps({
  cardId: { type: Number, required: true },
  // The layout's slot definitions, in slot-index order.
  slotDefs: { type: Array, default: () => [] },
  // The card's stored image slots ({slot_index, variants}).
  slots: { type: Array, default: () => [] },
  // Images of the card's source document, offered by "Pick from Document".
  documentImages: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:slots"]);
const { notify } = useNotify();

const files = reactive({});
const fileNames = reactive({});
const busy = reactive({});
const pickerIdx = ref(-1);
const fileInput = ref(null);
let fileTargetIdx = -1;

function preview(slotIndex) {
  const slot = props.slots.find((s) => s.slot_index === slotIndex);
  return slot?.variants?.pwa?.presigned_url || null;
}

function chooseFile(idx) {
  fileTargetIdx = idx;
  fileInput.value?.click();
}

function onFilePicked(e) {
  const file = e.target.files?.[0];
  if (fileTargetIdx >= 0 && file) {
    files[fileTargetIdx] = file;
    fileNames[fileTargetIdx] = file.name;
  }
  e.target.value = "";
  fileTargetIdx = -1;
}

async function change(slotIndex, request, done, failed) {
  busy[slotIndex] = true;
  try {
    await request();
    notify.success(done);
    const full = await getInfoCard(props.cardId);
    emit("update:slots", full.image_slots ?? []);
    return true;
  } catch (err) {
    notify.error(`${failed}: ` + (err.message || err));
    return false;
  } finally {
    busy[slotIndex] = false;
  }
}

async function upload(slotIndex) {
  const file = files[slotIndex];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const saved = await change(
    slotIndex,
    () => setInfoCardSlot(props.cardId, slotIndex, fd),
    "Slot image updated.",
    "Failed to upload slot image",
  );
  if (saved) delete files[slotIndex];
}

function pick(slotIndex, sourceImageId) {
  const fd = new FormData();
  fd.append("source_image_id", String(sourceImageId));
  return change(
    slotIndex,
    () => setInfoCardSlot(props.cardId, slotIndex, fd),
    "Slot image set from document.",
    "Failed to set slot image",
  );
}

function clear(slotIndex) {
  return change(
    slotIndex,
    () => deleteInfoCardSlot(props.cardId, slotIndex),
    "Slot image cleared.",
    "Failed to clear slot image",
  );
}
</script>
