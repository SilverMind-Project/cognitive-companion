<template>
  <!-- Large split: card content (and, when editing, image slots) beside generation, layout, and tags -->
  <AppDialog
    :model-value="modelValue"
    size="lg"
    persistent
    icon="mdi-card-text-outline"
    :label="isEdit ? 'Edit' : 'Create New'"
    title="Info Card"
    :hint="
      isEdit
        ? 'Modify card content, manage image slots, and update tags.'
        : 'Generate content from a knowledge document, or fill in fields manually.'
    "
    :confirm-label="isEdit ? undefined : 'Create'"
    :confirm-loading="submitting"
    @cancel="close"
    @confirm="submit"
  >
    <template #aside>
      <v-card variant="tonal" class="mb-4 pa-3">
        <div class="text-subtitle-2 mb-2">
          {{ isEdit ? "Regenerate" : "Generate" }} from Knowledge Document
        </div>
        <LlmModelPicker
          v-model="generateModelId"
          :model-items="llmModelItems"
          label="LLM Model"
          :hint="
            isEdit ? 'Model used for regeneration' : 'Model used when generating from a document'
          "
          persistent-hint
          clearable
          class="mb-3"
        />
        <v-select
          v-model="form.document_id"
          :items="documents"
          item-title="title"
          item-value="id"
          label="Knowledge Document"
          :hint="`Source document for content ${isEdit ? 'regeneration' : 'generation'}`"
          clearable
          class="mb-2"
        />
        <v-btn
          color="secondary"
          variant="tonal"
          :loading="generating"
          :disabled="!form.document_id"
          block
          data-test="generate-card"
          @click="generate"
        >
          {{ isEdit ? "Regenerate" : "Generate" }}
        </v-btn>
      </v-card>
      <v-select
        v-model="form.layout_id"
        :items="layouts"
        item-title="display_name"
        item-value="id"
        label="Layout"
        :rules="isEdit ? [] : [(r) => !!r || 'Layout is required']"
        :class="{ 'mb-3': isEdit }"
      />
      <v-combobox v-model="form.tags" label="Tags" multiple chips closable-chips />
    </template>

    <v-text-field
      v-model="form.title"
      label="Title"
      :rules="isEdit ? [] : [(r) => !!r || 'Title is required']"
      :class="{ 'mb-3': isEdit }"
    />
    <v-textarea
      v-model="form.body_text"
      label="Body Text"
      :rows="isEdit ? 10 : 12"
      class="mb-3"
      data-test="card-body"
    />
    <VoiceInstructionField
      v-model="form.voice_instruction"
      resource-type="info_card"
      :document-id="form.document_id"
      :class="{ 'mb-3': isEdit }"
    />

    <InfoCardSlotsEditor
      v-if="isEdit && card"
      v-model:slots="slots"
      :card-id="card.id"
      :slot-defs="layoutSlots"
      :document-images="documentImages"
    />
  </AppDialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { createInfoCard, suggestInfoCard, updateInfoCard } from "@/services/modules/info_cards";
import { getKnowledgeDocument } from "@/services/modules/knowledge";
import { useNotify } from "@/composables/useNotify.js";
import AppDialog from "@/components/common/AppDialog.vue";
import LlmModelPicker from "@/components/common/LlmModelPicker.vue";
import InfoCardSlotsEditor from "@/components/knowledge/InfoCardSlotsEditor.vue";
import VoiceInstructionField from "@/components/knowledge/VoiceInstructionField.vue";

/**
 * Create or edit one info card. In edit mode ``card`` must be the full record
 * (GET /info-cards/{id}): list rows carry no body_text or voice_instruction, and a form
 * filled from one would save the card's text away.
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  mode: { type: String, default: "create", validator: (v) => ["create", "edit"].includes(v) },
  card: { type: Object, default: null },
  // Create mode: the document to start from (the document page's "Create info card").
  initialDocumentId: { type: Number, default: null },
  layouts: { type: Array, default: () => [] },
  documents: { type: Array, default: () => [] },
  llmModelItems: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:modelValue", "saved"]);
const { notify } = useNotify();

const isEdit = computed(() => props.mode === "edit");
const form = reactive(blankForm());
const generateModelId = ref("");
const generating = ref(false);
const submitting = ref(false);
const slots = ref([]);
const documentImages = ref([]);

const layoutSlots = computed(
  () => props.layouts.find((l) => l.id === form.layout_id)?.image_slots ?? [],
);

function blankForm() {
  return {
    title: "",
    body_text: "",
    layout_id: null,
    document_id: null,
    tags: [],
    voice_instruction: "",
  };
}

async function load() {
  Object.assign(form, blankForm());
  generateModelId.value = "";
  slots.value = [];
  documentImages.value = [];
  if (!isEdit.value) {
    form.document_id = props.initialDocumentId;
    return;
  }
  const card = props.card ?? {};
  form.title = card.title ?? "";
  form.body_text = card.body_text ?? "";
  form.layout_id = card.layout_id ?? null;
  form.document_id = card.document_id ?? null;
  form.tags = [...(card.tags ?? [])];
  form.voice_instruction = card.voice_instruction ?? "";
  slots.value = card.image_slots ?? [];
  if (form.document_id) {
    try {
      documentImages.value = (await getKnowledgeDocument(form.document_id)).images ?? [];
    } catch (_) {
      // "Pick from Document" stays hidden; uploads still work.
    }
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) load();
  },
  { immediate: true },
);

async function generate() {
  if (!form.document_id) {
    notify.warning("Select a knowledge document first.");
    return;
  }
  generating.value = true;
  try {
    const suggestion = await suggestInfoCard(form.document_id, generateModelId.value || undefined);
    if (suggestion.title) form.title = suggestion.title;
    if (suggestion.body_text) form.body_text = suggestion.body_text;
    // A new card takes the drafted voice instruction unless one was typed; an edited card
    // keeps the caregiver's.
    if (!isEdit.value && suggestion.voice_instruction && !form.voice_instruction) {
      form.voice_instruction = suggestion.voice_instruction;
    }
    notify.success(
      isEdit.value ? "Info card content regenerated." : "Info card draft generated from document.",
    );
  } catch (err) {
    notify.error(`Failed to ${isEdit.value ? "regenerate" : "generate"}: ` + (err.message || err));
  } finally {
    generating.value = false;
  }
}

function payload() {
  return {
    title: form.title,
    body_text: form.body_text,
    layout_id: form.layout_id,
    document_id: form.document_id || undefined,
    tags: form.tags,
    voice_instruction: form.voice_instruction,
  };
}

async function submit() {
  if (!isEdit.value && (!form.title || !form.layout_id)) {
    notify.warning("Title and Layout are required.");
    return;
  }
  if (isEdit.value && !props.card) return;
  submitting.value = true;
  try {
    if (isEdit.value) {
      await updateInfoCard(props.card.id, payload());
      notify.success("Info card updated.");
    } else {
      await createInfoCard(payload());
      notify.success("Info card created.");
    }
    emit("saved");
    close();
  } catch (err) {
    notify.error(`Failed to ${isEdit.value ? "update" : "create"}: ` + (err.message || err));
  } finally {
    submitting.value = false;
  }
}

function close() {
  emit("update:modelValue", false);
}

defineExpose({ form });
</script>
