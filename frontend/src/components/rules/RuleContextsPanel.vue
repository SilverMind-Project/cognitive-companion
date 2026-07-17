<template>
  <v-card>
    <v-card-text>
      <div class="d-flex align-center mb-3">
        <h4 class="text-subtitle-1">Context Filters</h4>
        <v-spacer />
        <v-btn
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-plus"
          @click="openCtxDialog"
        >
          Add Context
        </v-btn>
      </div>
      <v-list v-if="contexts?.length">
        <v-list-item v-for="ctx in contexts" :key="ctx.id">
          <template #prepend>
            <v-icon size="20" :color="ctxIcon(ctx.context_type).color" class="mr-3">
              {{ ctxIcon(ctx.context_type).icon }}
            </v-icon>
          </template>
          <v-list-item-title>
            <v-chip v-if="ctx.negate" size="small" color="warning" variant="tonal" class="mr-1"
              >NOT</v-chip
            >
            <v-chip size="small" color="info" variant="tonal" class="mr-2">{{
              ctx.context_type
            }}</v-chip>
            {{ ctxSummary(ctx) }}
          </v-list-item-title>
          <template #append>
            <v-btn
              icon="mdi-delete"
              size="x-small"
              variant="text"
              color="error"
              @click="deleteContext(ctx.id)"
            />
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="text-center text-grey py-4">
        No context filters. This rule applies everywhere.
      </div>
    </v-card-text>
  </v-card>

  <ContextFilterDialog
    v-model="ctxDialog"
    v-model:ctx-form="ctxForm"
    v-model:ctx-config-str="ctxConfigStr"
    :room-names="roomNames"
    :person-ids="personIds"
    @add="addContext"
  />
</template>

<script setup>
import { toRef } from "vue";
import ContextFilterDialog from "./ContextFilterDialog.vue";
import { useRuleContexts, ctxIcon, ctxSummary } from "@/composables/useRuleContexts.js";

const props = defineProps({
  ruleId: { type: Number, required: true },
  contexts: { type: Array, default: () => [] },
  roomNames: { type: Array, required: true },
  personIds: { type: Array, required: true },
});
const emit = defineEmits(["changed"]);

const ruleId = toRef(props, "ruleId");
const { ctxDialog, ctxForm, ctxConfigStr, openCtxDialog, addContext, deleteContext } =
  useRuleContexts(ruleId, { onChanged: () => emit("changed") });
</script>
