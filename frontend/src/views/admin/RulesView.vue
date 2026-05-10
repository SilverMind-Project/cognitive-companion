<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div>
        <h2 class="text-h4 font-weight-bold tracking-tight">Rules</h2>
        <div class="text-body-2 text-medium-emphasis mt-1">Triggers, contexts, and pipelines that drive the system.</div>
      </div>
      <v-spacer />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="createDialog = true">New Rule</v-btn>
    </div>

    <v-card class="glass-card">
      <v-data-table
        :headers="headers"
        :items="rules"
        :loading="loading"
        item-value="id"
        @click:row="(_, { item }) => $router.push(`/admin/rules/${item.id}`)"
        hover
      >
        <template #item.enabled="{ item }">
          <v-chip :color="item.enabled ? 'success' : 'grey'" size="small">
            {{ item.enabled ? "Active" : "Disabled" }}
          </v-chip>
        </template>
        <template #item.trigger_type="{ item }">
          <v-chip size="small" variant="outlined">{{ item.trigger_type }}</v-chip>
        </template>
        <template #item.actions="{ item }">
          <v-btn
            icon="mdi-delete"
            size="small"
            variant="text"
            color="error"
            @click.stop="deleteRule(item.id)"
          />
        </template>
        <template #no-data>
          <div class="pa-6 text-center">
            <v-card flat>
              <v-card-text class="text-grey text-h6">No rules yet</v-card-text>
              <v-card-text class="text-grey">Create automation rules to detect events and trigger actions.</v-card-text>
            </v-card>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create Dialog: minimal entry point. Trigger type and other settings are configured on the rule detail page. -->
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
          <v-textarea v-model="createForm.description" label="Description" variant="outlined" rows="2" />
        </v-card-text>
        <DialogFooter
          hint="Rules define automated workflows triggered by sensors, schedules, or events."
          confirm-label="Create"
          @cancel="createDialog = false"
          @confirm="createRule"
        />
      </v-card>
    </v-dialog>
    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>

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

const { snack, snackText, snackColor, notify } = useNotify();
const { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel } = useConfirm();

const router = useRouter();
const rules = ref([]);
const loading = ref(false);
const createDialog = ref(false);
const createForm = ref({ name: "", description: "" });

const headers = [
  { title: "Name", key: "name" },
  { title: "Status", key: "enabled" },
  { title: "Trigger", key: "trigger_type" },
  { title: "Cron", key: "schedule_cron" },
  { title: "Cool-off", key: "cool_off_minutes" },
  { title: "Max/Day", key: "max_daily_triggers" },
  { title: "", key: "actions", sortable: false, width: 60 },
];

async function loadRules() {
  loading.value = true;
  try {
    rules.value = await api.getRules();
  } catch (e) {
    console.error("Failed to load rules:", e);
    rules.value = [];
  }
  loading.value = false;
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

async function deleteRule(id) {
  if (!await showConfirm("Delete Rule", "Delete this rule?")) return;
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
