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
      activeRuns.value = (runs || []).map(normalizeRun);
    } catch (e) {
      error.value = e?.message || "Failed to load active runs";
    }
  }

  function edgeKey(source, sourceHandle = "main") {
    return `${source}:${sourceHandle || "main"}`;
  }

  function normalizeRun(run) {
    const activeEdges = run.active_edges instanceof Set
      ? run.active_edges
      : new Set(run.active_edges || []);
    return {
      ...run,
      nodes: (run.nodes || []).map((node) => ({
        ...node,
        status: node.status || "pending",
        elapsed_ms: node.elapsed_ms ?? null,
        output_port: node.output_port ?? null,
      })),
      edges: (run.edges || []).map((edge) => {
        const sourceHandle = edge.sourceHandle || edge.source_handle || "main";
        return {
          ...edge,
          sourceHandle,
          targetHandle: edge.targetHandle || edge.target_handle || "main",
          active: activeEdges.has(edgeKey(edge.source, sourceHandle)),
        };
      }),
      active_node_id: run.active_node_id ?? null,
      active_edges: activeEdges,
    };
  }

  function _handleEvent(data) {
    const et = data.event_type;
    const id = data.execution_id;

    if (et === "pipeline_started") {
      // Add a placeholder if not already present.
      if (!activeRuns.value.find((r) => r.execution_id === id)) {
        const activeEdges = new Set();
        activeRuns.value = [
          ...activeRuns.value,
          normalizeRun({
            execution_id: id,
            rule_id: data.rule_id,
            rule_name: data.rule_name,
            status: "running",
            started_at: data.started_at,
            nodes: (data.steps || []).map((step) => ({
              id: step.id,
              label: step.label,
              step_type: step.step_type,
              status: "pending",
              elapsed_ms: null,
              output_port: null,
            })),
            edges: (data.edges || []).map((edge) => ({
              source: edge.source,
              sourceHandle: edge.source_handle || edge.sourceHandle || "main",
              target: edge.target,
              targetHandle: edge.target_handle || edge.targetHandle || "main",
              active: false,
            })),
            active_node_id: null,
            active_edges: activeEdges,
          }),
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
          active_node_id: data.step_id,
          nodes: r.nodes.map((n) =>
            n.id === data.step_id ? { ...n, status: "running" } : n,
          ),
        };
      });
    } else if (et === "step_completed") {
      activeRuns.value = activeRuns.value.map((r) => {
        if (r.execution_id !== id) return r;
        const outputPort = data.output_port || "main";
        const nextActiveEdges = new Set([...(r.active_edges || []), edgeKey(data.step_id, outputPort)]);
        return {
          ...r,
          nodes: r.nodes.map((n) =>
            n.id === data.step_id
              ? {
                  ...n,
                  status: data.status,
                  output_port: outputPort,
                  elapsed_ms: data.elapsed_ms ?? n.elapsed_ms ?? null,
                }
              : n,
          ),
          edges: r.edges.map((edge) => {
            const sourceHandle = edge.sourceHandle || edge.source_handle || "main";
            return {
              ...edge,
              sourceHandle,
              active: nextActiveEdges.has(edgeKey(edge.source, sourceHandle)),
            };
          }),
          active_edges: nextActiveEdges,
          active_node_id: null,
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
