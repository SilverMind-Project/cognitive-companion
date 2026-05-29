/**
 * useLivePipeline — live pipeline execution feed (U5 W3).
 *
 * Manages the /ws/pipeline WebSocket lifecycle and exposes:
 *   connectionState: "connecting" | "open" | "error" | "closed"
 *   activeRuns:      array of PipelineRunEnvelope (seeded by REST, updated by WS events)
 *   ingestEvents:    array of PipelineExecutionEvent received over the socket
 *   error:           string | null (last connection error message)
 *
 * D5 / rule 15: connectionState is always explicit — the view never shows a
 * frozen-but-plausible DAG when the socket is not open.
 *
 * Rule 17: uses openPipelineSocket() from api.js (never opens a raw socket
 * with a localStorage token in caller code).
 */

import { ref, onUnmounted } from "vue";
import { openPipelineSocket } from "@/services/api.js";
import { api } from "@/services/api.js";

export function useLivePipeline() {
  const connectionState = ref("disconnected");
  const activeRuns = ref([]);
  const ingestEvents = ref([]);
  const error = ref(null);

  let ws = null;
  let reconnectTimer = null;
  let closed = false;

  // Seed active runs from the REST endpoint.
  async function fetchActiveRuns() {
    try {
      const runs = await api.getPipelineRuns({ status: "active" });
      activeRuns.value = runs || [];
    } catch (e) {
      error.value = e?.message || "Failed to load active runs";
    }
  }

  function _handleEvent(data) {
    const et = data.event_type;
    const id = data.execution_id;

    if (et === "pipeline_started") {
      // Add a placeholder if not already present.
      if (!activeRuns.value.find((r) => r.execution_id === id)) {
        activeRuns.value = [
          ...activeRuns.value,
          {
            execution_id: id,
            rule_id: data.rule_id,
            rule_name: data.rule_name,
            status: "running",
            started_at: data.started_at,
            nodes: [],
            edges: [],
          },
        ];
      }
    } else if (et === "pipeline_completed" || et === "pipeline_failed" || et === "pipeline_cancelled") {
      // Remove from active runs; it is now terminal.
      activeRuns.value = activeRuns.value.filter((r) => r.execution_id !== id);
    } else if (et === "pipeline_waiting") {
      activeRuns.value = activeRuns.value.map((r) =>
        r.execution_id === id ? { ...r, status: "waiting" } : r,
      );
    } else if (et === "step_started") {
      activeRuns.value = activeRuns.value.map((r) => {
        if (r.execution_id !== id) return r;
        return {
          ...r,
          nodes: r.nodes.map((n) =>
            n.id === data.step_id ? { ...n, status: "running" } : n,
          ),
        };
      });
    } else if (et === "step_completed") {
      activeRuns.value = activeRuns.value.map((r) => {
        if (r.execution_id !== id) return r;
        return {
          ...r,
          nodes: r.nodes.map((n) =>
            n.id === data.step_id ? { ...n, status: data.status } : n,
          ),
        };
      });
    }
  }

  function connect() {
    if (closed) return;
    connectionState.value = "connecting";
    error.value = null;

    ws = openPipelineSocket((data) => {
      ingestEvents.value = [...ingestEvents.value, data];
      _handleEvent(data);
    });

    ws.onopen = () => {
      connectionState.value = "open";
    };

    ws.onerror = () => {
      connectionState.value = "error";
      error.value = "Stream interrupted";
    };

    ws.onclose = () => {
      connectionState.value = "closed";
      ws = null;
      if (!closed) {
        reconnectTimer = setTimeout(connect, 3000);
      }
    };
  }

  function disconnect() {
    closed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) ws.close();
    ws = null;
  }

  onUnmounted(disconnect);

  fetchActiveRuns();
  connect();

  return {
    connectionState,
    activeRuns,
    ingestEvents,
    error,
    disconnect,
    refresh: fetchActiveRuns,
  };
}
