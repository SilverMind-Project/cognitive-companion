<template>
  <div class="cc-chart-wrapper">
    <div v-if="error" class="cc-chart-state">
      <v-alert type="error" variant="tonal" density="compact" class="ma-2">
        {{ error }}
      </v-alert>
    </div>
    <div v-else-if="loading" class="cc-chart-state">
      <v-skeleton-loader type="image" height="200" />
    </div>
    <div v-else-if="isEmpty" class="cc-chart-state">
      <slot name="empty">
        <div class="pa-6 text-center text-medium-emphasis">No pipeline data yet</div>
      </slot>
    </div>
    <v-chart
      v-else
      :option="chartOption"
      autoresize
      style="width: 100%; height: 100%; min-height: 200px"
    />
  </div>
</template>

<script setup>
import { computed } from "vue";
import dagre from "@dagrejs/dagre";
import VChart from "vue-echarts";
import "@/components/charts/echarts.js";
import { useChartTheme } from "@/composables/useChartTheme.js";

const props = defineProps({
  /**
   * DAG nodes: [{ id: string, label: string, status: 'pending'|'running'|'succeeded'|'failed'|'skipped' }]
   */
  nodes: {
    type: Array,
    default: () => [],
  },
  /** DAG edges: [{ source: string, target: string }] — IDs referencing nodes.id */
  edges: {
    type: Array,
    default: () => [],
  },
  /** ID of the currently active (running) node; drives the pulse highlight. */
  activeNodeId: {
    type: String,
    default: null,
  },
  activeEdges: {
    type: Object,
    default: () => new Set(),
  },
  nodeTimings: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: null,
  },
});

const { chartTheme } = useChartTheme();

const isEmpty = computed(() => !props.nodes?.length);

function _computePositions(nodes, edges) {
  if (!nodes.length) return {};
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120 });
  for (const node of nodes) {
    graph.setNode(node.id, { width: 120, height: 48 });
  }
  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target);
  }
  dagre.layout(graph);
  return Object.fromEntries(
    nodes.map((node) => {
      const position = graph.node(node.id) || { x: 0, y: 0 };
      return [node.id, { x: position.x, y: position.y }];
    }),
  );
}

function nodeColor(status, id, th) {
  if (id === props.activeNodeId || status === "running") return th._severity.running;
  const map = {
    succeeded: th._severity.succeeded,
    failed: th._severity.failed,
    skipped: th._severity.skipped,
    pending: th._severity.pending,
  };
  return map[status] ?? th._severity.pending;
}

const chartOption = computed(() => {
  const th = chartTheme.value;
  const positions = _computePositions(props.nodes, props.edges);

  const graphNodes = props.nodes.map((n) => ({
    id: n.id,
    name: n.label ?? n.id,
    x: positions[n.id]?.x ?? 0,
    y: positions[n.id]?.y ?? 0,
    symbolSize: n.id === props.activeNodeId || n.status === "running" ? 24 : 16,
    itemStyle: {
      color: nodeColor(n.status, n.id, th),
      borderColor: th.grid.borderColor,
      borderWidth: 1,
    },
    label: {
      show: true,
      color: th.textStyle.color,
      fontSize: 11,
    },
    // Carry status as a custom field for testing
    _status: n.status,
  }));

  const graphEdges = props.edges.map((e) => {
    const sourceHandle = e.sourceHandle || e.source_handle || "main";
    const isActive = props.activeEdges?.has?.(`${e.source}:${sourceHandle}`);
    return {
      source: e.source,
      target: e.target,
      lineStyle: {
        color: isActive ? th._severity.succeeded : th.xAxis.axisLine.lineStyle.color,
        width: isActive ? 3 : 1.5,
        curveness: 0.1,
      },
      label: {
        show: Boolean(sourceHandle && sourceHandle !== "main"),
        formatter: sourceHandle || "",
        color: th.textStyle.color,
        fontSize: 10,
      },
    };
  });

  return {
    backgroundColor: "transparent",
    textStyle: th.textStyle,
    tooltip: {
      ...th.tooltip,
      formatter: (p) => {
        if (p.dataType === "node") {
          const timing = props.nodeTimings?.[p.data.id];
          const timingStr = timing != null ? `<br/>${(timing / 1000).toFixed(1)}s` : "";
          return `${p.name}<br/>Status: ${p.data._status ?? "unknown"}${timingStr}`;
        }
        return "";
      },
    },
    series: [
      {
        type: "graph",
        layout: "none",
        data: graphNodes,
        edges: graphEdges,
        roam: true,
        lineStyle: { opacity: 0.7 },
        emphasis: {
          focus: "adjacency",
          itemStyle: { shadowBlur: 12 },
        },
      },
    ],
  };
});

defineExpose({ chartOption, isEmpty, nodeColor });
</script>

<style scoped>
.cc-chart-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.cc-chart-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}
</style>
