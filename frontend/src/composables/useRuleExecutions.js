import { ref, watch } from "vue";
import { api } from "@/services/api.js";
import { DATETIME_COLUMN_WIDTH, formatDateTime } from "@/services/timezone.js";

const EXEC_HEADERS = [
  { title: "ID", key: "id" },
  { title: "Status", key: "status" },
  { title: "Started", key: "started_at", width: DATETIME_COLUMN_WIDTH },
  { title: "Completed", key: "completed_at", width: DATETIME_COLUMN_WIDTH },
  { title: "Duration", key: "_duration" },
];

export function statusColor(status) {
  const map = {
    completed: "success",
    failed: "error",
    running: "info",
    waiting: "warning",
    cancelled: "grey",
  };
  return map[status] || "grey";
}

export function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return "-";
  const ms = new Date(endIso) - new Date(startIso);
  if (ms < 0) return "-";
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const rem = secs % 60;
  return rem > 0 ? `${mins}m ${rem}s` : `${mins}m`;
}

/** Recent-executions list for the rule detail view's Executions tab. */
export function useRuleExecutions(ruleId, tab, router) {
  const executions = ref([]);
  const execLoading = ref(false);

  async function loadExecutions() {
    execLoading.value = true;
    try {
      executions.value = await api.getWorkflows({ rule_id: ruleId.value, limit: 50 });
    } catch (e) {
      console.error("Failed to load executions:", e);
      executions.value = [];
    }
    execLoading.value = false;
  }

  function openExecution(execution) {
    const isLive = ["running", "waiting"].includes(execution.status);
    router.push({
      name: "admin-executions",
      query: {
        tab: isLive ? "live" : "history",
        rule_id: ruleId.value,
        execution: execution.id,
      },
    });
  }

  watch(tab, (val) => {
    if (val === "executions") loadExecutions();
  });

  return {
    executions,
    execLoading,
    execHeaders: EXEC_HEADERS,
    formatDate: formatDateTime,
    loadExecutions,
    openExecution,
  };
}
