/**
 * Central ECharts registration module.
 *
 * All chart components import this file as a side-effect so `use()` is called
 * exactly once per module load. Only the series and components actually used
 * by the U3 chart library are registered — this keeps the bundle lean.
 *
 * Rule 14: no full `echarts` bundle import. Every import must come from a
 * subpath so tree-shaking eliminates unused code.
 */
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import {
  LineChart,
  BarChart,
  HeatmapChart,
  ScatterChart,
  GaugeChart,
  GraphChart,
} from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  VisualMapComponent,
  DataZoomComponent,
  TitleComponent,
} from "echarts/components";

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  HeatmapChart,
  ScatterChart,
  GaugeChart,
  GraphChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  VisualMapComponent,
  DataZoomComponent,
  TitleComponent,
]);
