<template>
  <div>
    <div class="d-flex align-center flex-wrap ga-3 mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Rules</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">
          Triggers, contexts, and pipelines that drive the system.
        </div>
      </div>
      <v-spacer />
      <div class="d-flex ga-2 mr-2">
        <v-btn
          v-for="opt in periodOptions"
          :key="opt.value"
          size="small"
          :variant="executionPeriod === opt.value ? 'flat' : 'outlined'"
          :color="executionPeriod === opt.value ? 'primary' : undefined"
          @click="executionPeriod = opt.value"
          >{{ opt.label }}</v-btn
        >
      </div>
      <v-btn variant="text" prepend-icon="mdi-import" @click="showImportDialog = true"
        >Import</v-btn
      >
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="createDialog = true"
        >New Rule</v-btn
      >
    </div>

    <v-card class="glass-card">
      <v-data-table :headers="headers" :items="rules" :loading="loading" item-value="id" hover>
        <template #item.enabled="{ item }">
          <v-switch
            :model-value="item.enabled"
            color="success"
            density="compact"
            hide-details
            @click.stop
            @update:model-value="toggleEnabled(item)"
          />
        </template>
        <template #item.trigger_types="{ item }">
          <div class="d-flex flex-wrap ga-1">
            <v-chip v-for="t in item.trigger_types" :key="t" size="x-small" variant="outlined">{{
              t
            }}</v-chip>
          </div>
        </template>
        <template #item.execution_counts="{ item }">
          <span class="text-body-2">
            {{ item.execution_counts?.[executionPeriod] ?? 0 }}
          </span>
        </template>
        <template #item.actions="{ item }">
          <div class="d-flex align-center">
            <v-btn
              icon="mdi-pencil"
              size="small"
              variant="text"
              color="primary"
              title="Edit rule"
              @click.stop="$router.push(`/admin/rules/${item.id}`)"
            />
            <v-btn
              icon="mdi-history"
              size="small"
              variant="text"
              color="secondary"
              title="Execution history"
              @click.stop="$router.push(`/admin/rules/${item.id}?tab=executions`)"
            />
            <v-btn
              icon="mdi-delete"
              size="small"
              variant="text"
              color="error"
              title="Delete rule"
              @click.stop="deleteRule(item.id)"
            />
          </div>
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No rules yet</v-card-text>
              <v-card-text class="text-grey"
                >Create automation rules to detect events and trigger actions.</v-card-text
              >
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create Dialog -->
    <v-dialog v-model="createDialog" max-width="500" persistent>
      <v-card>
        <DialogHeader
          icon="mdi-automation"
          label="Create New"
          title="Rule"
          @close="createDialog = false"
        />
        <v-card-text>
          <v-text-field v-model="createForm.name" label="Name" variant="outlined" class="mb-3" />
          <v-textarea
            v-model="createForm.description"
            label="Description"
            variant="outlined"
            rows="2"
          />
        </v-card-text>
        <DialogFooter
          hint="Rules define automated workflows triggered by sensors, schedules, or events."
          confirm-label="Create"
          @cancel="createDialog = false"
          @confirm="createRule"
        />
      </v-card>
    </v-dialog>

    <ImportRuleDialog v-model="showImportDialog" @imported="onRuleImported" />

    <v-dialog v-model="confirmDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title>{{ confirmTitle }}</v-card-title>
        <v-card-text>{{ confirmText }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="onCancel">Cancel</v-btn>
          <v-btn color="error" @click="onConfirm">Confirm</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "../../services/api.js";
import { useNotify } from "../../composables/useNotify.js";
import { useConfirm } from "../../composables/useConfirm.js";
import DialogHeader from "../../components/common/DialogHeader.vue";
import DialogFooter from "../../components/common/DialogFooter.vue";
import ImportRuleDialog from "../../components/pipeline/ImportRuleDialog.vue";

const { notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();

const router = useRouter();
const rules = ref([]);
const loading = ref(false);
const createDialog = ref(false);
const createForm = ref({ name: "", description: "" });
const showImportDialog = ref(false);
const executionPeriod = ref("last_1h");
const periodOptions = [
  { value: "last_15m", label: "15m" },
  { value: "last_1h", label: "1h" },
  { value: "last_24h", label: "24h" },
  { value: "last_30d", label: "30d" },
];

function onRuleImported() {
  showImportDialog.value = false;
  loadRules();
}

const headers = [
  { title: "Name", key: "name" },
  { title: "Triggers", key: "trigger_types", width: 130 },
  { title: "Cool-off", key: "cool_off_minutes", width: 110 },
  { title: "Max/Day", key: "max_daily_triggers", width: 110 },
  { title: "Executions", key: "execution_counts", width: 110 },
  { title: "Active", key: "enabled", width: 80 },
  { title: "Actions", key: "actions", sortable: false, width: 130 },
];

async function loadRules() {
  loading.value = true;
  try {
    rules.value = await api.getRules();
  } catch (e) {
    notify(e.message || "Failed to load rules", "error");
    rules.value = [];
  } finally {
    loading.value = false;
  }
}

async function createRule() {
  try {
    const rule = await api.createRule(createForm.value);
    createDialog.value = false;
    router.push(`/admin/rules/${rule.id}`);
  } catch (e) {
    notify(e.message, "error");
  }
}

async function toggleEnabled(item) {
  try {
    await api.updateRule(item.id, { enabled: !item.enabled });
    item.enabled = !item.enabled;
    notify.success(`Rule ${item.enabled ? "enabled" : "disabled"}.`);
  } catch (e) {
    notify.error(e.message || "Failed to update rule.");
  }
}

async function deleteRule(id) {
  if (!(await showConfirm("Delete Rule", "Delete this rule?"))) return;
  try {
    await api.deleteRule(id);
    await loadRules();
  } catch (e) {
    notify(e.message, "error");
  }
}

onMounted(loadRules);
</script>

<style scoped>
.tracking-tight {
  letter-spacing: -0.018em;
}
</style>
