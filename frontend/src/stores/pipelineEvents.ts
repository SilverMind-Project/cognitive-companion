/**
 * Live pipeline feed — one /ws/pipeline socket for the whole app (M18).
 *
 * `useLivePipeline` used to own a socket per calling component, so two mounted consumers meant
 * two connections and every event processed twice. The socket is a process-wide resource; this
 * store is its honest owner.
 *
 * Consumers acquire with `connect()`, which returns a release function. The socket opens on the
 * first acquire and closes on the last release, preserving the old behavior where navigating
 * away from the last live view drops the connection rather than holding it open forever.
 *
 * D5 / rule 15: `connectionState` is always explicit -- the view must never render a
 * frozen-but-plausible DAG while the socket is down.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { api, openPipelineSocket } from "@/services/api.js";

export type ConnectionState = "disconnected" | "connecting" | "open" | "error" | "closed";

const RECONNECT_DELAY_MS = 3000;

/**
 * Cap on the retained event feed.
 *
 * Per-component ownership bounded this array implicitly: it died with the component. A store
 * lives as long as the tab, so an uncapped feed is an unbounded leak on a long-lived kiosk. Both
 * consumers only ever filter it for display, so dropping the oldest events is invisible to them.
 */
export const MAX_INGEST_EVENTS = 500;

function edgeKey(source: string, sourceHandle: string = "main"): string {
  return `${source}:${sourceHandle || "main"}`;
}

function normalizeRun(run: any) {
  const activeEdges =
    run.active_edges instanceof Set ? run.active_edges : new Set(run.active_edges || []);
  return {
    ...run,
    nodes: (run.nodes || []).map((node: any) => ({
      ...node,
      status: node.status || "pending",
      elapsed_ms: node.elapsed_ms ?? null,
      output_port: node.output_port ?? null,
    })),
    edges: (run.edges || []).map((edge: any) => {
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

export const usePipelineEventsStore = defineStore("pipelineEvents", () => {
  const connectionState = ref<ConnectionState>("disconnected");
  const activeRuns = ref<any[]>([]);
  const ingestEvents = ref<any[]>([]);
  const error = ref<string | null>(null);

  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let consumers = 0;

  async function refresh(): Promise<void> {
    try {
      const runs = await api.getPipelineRuns({ status: "active" });
      activeRuns.value = (runs || []).map(normalizeRun);
    } catch (e: any) {
      error.value = e?.message || "Failed to load active runs";
    }
  }

  function handleEvent(data: any): void {
    const et = data.event_type;
    const id = data.execution_id;

    if (et === "pipeline_started") {
      if (!activeRuns.value.find((r) => r.execution_id === id)) {
        activeRuns.value = [
          ...activeRuns.value,
          normalizeRun({
            execution_id: id,
            rule_id: data.rule_id,
            rule_name: data.rule_name,
            status: "running",
            started_at: data.started_at,
            nodes: (data.steps || []).map((step: any) => ({
              id: step.id,
              label: step.label,
              step_type: step.step_type,
              status: "pending",
              elapsed_ms: null,
              output_port: null,
            })),
            edges: (data.edges || []).map((edge: any) => ({
              source: edge.source,
              sourceHandle: edge.source_handle || edge.sourceHandle || "main",
              target: edge.target,
              targetHandle: edge.target_handle || edge.targetHandle || "main",
              active: false,
            })),
            active_node_id: null,
            active_edges: new Set(),
          }),
        ];
      }
    } else if (
      et === "pipeline_completed" ||
      et === "pipeline_failed" ||
      et === "pipeline_cancelled"
    ) {
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
          nodes: r.nodes.map((n: any) =>
            n.id === data.step_id ? { ...n, status: "running" } : n,
          ),
        };
      });
    } else if (et === "step_completed") {
      activeRuns.value = activeRuns.value.map((r) => {
        if (r.execution_id !== id) return r;
        const outputPort = data.output_port || "main";
        const nextActiveEdges = new Set([
          ...(r.active_edges || []),
          edgeKey(data.step_id, outputPort),
        ]);
        return {
          ...r,
          nodes: r.nodes.map((n: any) =>
            n.id === data.step_id
              ? {
                  ...n,
                  status: data.status,
                  output_port: outputPort,
                  elapsed_ms: data.elapsed_ms ?? n.elapsed_ms ?? null,
                }
              : n,
          ),
          edges: r.edges.map((edge: any) => {
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

  function openSocket(): void {
    // A reconnect that lands after the last consumer left must not resurrect the socket.
    if (consumers === 0) return;

    connectionState.value = "connecting";
    error.value = null;

    ws = openPipelineSocket((data: any) => {
      const next = [...ingestEvents.value, data];
      ingestEvents.value =
        next.length > MAX_INGEST_EVENTS ? next.slice(next.length - MAX_INGEST_EVENTS) : next;
      handleEvent(data);
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
      // Reconnect only while someone is still listening. `consumers` -- not a sticky `closed`
      // flag -- is what distinguishes "the network dropped us" from "the last view unmounted".
      if (consumers > 0) {
        reconnectTimer = setTimeout(openSocket, RECONNECT_DELAY_MS);
      }
    };
  }

  function teardown(): void {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (ws) {
      // Drop the handler first: this close is deliberate, so it must not schedule a reconnect
      // or overwrite the state we are about to set.
      ws.onclose = null;
      ws.close();
      ws = null;
    }
    connectionState.value = "disconnected";
    activeRuns.value = [];
    ingestEvents.value = [];
    error.value = null;
  }

  /**
   * Acquire the live feed. Returns a release function; the socket closes when the last consumer
   * releases. Release is idempotent, so an unmount after an explicit release cannot drive the
   * count negative.
   */
  function connect(): () => void {
    consumers += 1;
    if (consumers === 1) {
      openSocket();
      void refresh();
    }

    let released = false;
    return function release() {
      if (released) return;
      released = true;
      consumers -= 1;
      if (consumers === 0) teardown();
    };
  }

  return {
    connectionState,
    activeRuns,
    ingestEvents,
    error,
    connect,
    refresh,
    // Test seam: the consumer count is not part of the public contract.
    _consumerCount: () => consumers,
  };
});
