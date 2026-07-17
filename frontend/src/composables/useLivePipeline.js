/**
 * useLivePipeline — live pipeline execution feed (U5 W3).
 *
 * A thin acquire/release wrapper over the pipelineEvents store (M18). The store owns the
 * /ws/pipeline socket, so N mounted consumers now share one connection instead of opening one
 * each; this composable holds a reference for the calling component's lifetime and releases it
 * on unmount.
 *
 * Exposes:
 *   connectionState: "disconnected" | "connecting" | "open" | "error" | "closed"
 *   activeRuns:      array of PipelineRunEnvelope (seeded by REST, updated by WS events)
 *   ingestEvents:    array of PipelineExecutionEvent received over the socket
 *   error:           string | null (last connection error message)
 *
 * D5 / rule 15: connectionState is always explicit — the view never shows a
 * frozen-but-plausible DAG when the socket is not open.
 *
 * Rule 17: the socket is opened via openPipelineSocket() (never a raw socket with a
 * localStorage token in caller code).
 */

import { getCurrentInstance, onUnmounted } from "vue";
import { storeToRefs } from "pinia";

import { usePipelineEventsStore } from "@/stores/pipelineEvents";

export function useLivePipeline() {
  const store = usePipelineEventsStore();
  const { connectionState, activeRuns, ingestEvents, error } = storeToRefs(store);

  const release = store.connect();

  // Guarded: callers outside a component setup context (some specs) have no unmount hook to
  // bind, and onUnmounted would warn and never fire.
  if (getCurrentInstance()) onUnmounted(release);

  return {
    connectionState,
    activeRuns,
    ingestEvents,
    error,
    disconnect: release,
    refresh: store.refresh,
  };
}
