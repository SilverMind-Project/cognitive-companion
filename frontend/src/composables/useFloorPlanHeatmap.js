import { ref, computed, watch } from "vue";
import { useCanvasZoom } from "@/composables/useCanvasZoom.js";
import { useHeatmap } from "@/composables/useHeatmap.js";
import { api } from "@/services/api.js";
import { getAppTimezone, localDateToUTCISO } from "@/services/timezone.js";

/**
 * Heatmap-mode filters, presets, and bin projection. Owned by the
 * orchestrator: `watch(mode)` lazy-loads the person list on first entry into
 * heatmap mode, which must see the live -> heatmap transition (see
 * useFloorPlanCoverage for why that rules out panel-local ownership).
 */
export function useFloorPlanHeatmap(mode, fpWidth, fpHeight, fpMpp, canvasW, canvasH) {
  const heatmapZoom = useCanvasZoom({ maxZoom: 5, minZoom: 0.3 });
  const heatmapPersonId = ref(null);
  const heatmapPersons = ref([]);
  const { state: heatmapState, actions: heatmapActions } = useHeatmap();

  // App timezone label for the time-of-day controls (all stored data is UTC; the
  // filter is applied in local wall-clock time on the backend).
  const appTzLabel = computed(() => getAppTimezone());

  // ── Date-range filter ──────────────────────────────────────────────────────
  // Presets are absolute rolling windows; "custom" reveals local calendar pickers.
  const DATE_PRESETS = [
    { key: "last_24h", label: "24h", hours: 24 },
    { key: "last_7d", label: "7d", hours: 24 * 7 },
    { key: "last_14d", label: "14d", hours: 24 * 14 },
    { key: "last_30d", label: "30d", hours: 24 * 30 },
    { key: "custom", label: "Custom", hours: null },
  ];
  const heatmapDatePreset = ref("last_7d");
  const heatmapStartDate = ref(""); // "YYYY-MM-DD", custom range only
  const heatmapEndDate = ref(""); // "YYYY-MM-DD", custom range only

  // ── Time-of-day filter ─────────────────────────────────────────────────────
  // Minutes since LOCAL midnight. When start > end the window wraps past midnight
  // (e.g. Night 21:00-06:00). Ranges align with dementia behaviour indicators
  // (sundowning agitation late afternoon/evening, overnight wandering).
  const TIME_PRESETS = [
    { key: "all", label: "All Day", start: null, end: null },
    { key: "morning", label: "Morning", start: 6 * 60, end: 12 * 60 }, // 06:00-12:00
    { key: "afternoon", label: "Afternoon", start: 12 * 60, end: 17 * 60 }, // 12:00-17:00
    { key: "sundowning", label: "Sundowning", start: 16 * 60, end: 20 * 60 }, // 16:00-20:00
    { key: "evening", label: "Evening", start: 17 * 60, end: 21 * 60 }, // 17:00-21:00
    { key: "night", label: "Night", start: 21 * 60, end: 6 * 60 }, // 21:00-06:00 (wraps)
    { key: "custom", label: "Custom", start: null, end: null },
  ];
  const heatmapTimePreset = ref("all");
  const heatmapStartTime = ref("21:00"); // "HH:MM" local, custom only
  const heatmapEndTime = ref("06:00"); // "HH:MM" local, custom only

  // Custom date range needs both endpoints; custom time needs both times.
  const heatmapRangeReady = computed(() => {
    if (heatmapDatePreset.value === "custom") {
      return !!heatmapStartDate.value && !!heatmapEndDate.value;
    }
    return true;
  });
  const heatmapTimeReady = computed(() => {
    if (heatmapTimePreset.value === "custom") {
      return !!heatmapStartTime.value && !!heatmapEndTime.value;
    }
    return true;
  });

  // Format minutes-since-local-midnight as a friendly 12-hour clock (e.g. 360 ->
  // "6:00 AM"). Pure arithmetic so it stays independent of any Date/locale API.
  function _formatMinutes(min) {
    const h24 = Math.floor(min / 60) % 24;
    const m = min % 60;
    const period = h24 < 12 ? "AM" : "PM";
    const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
    return `${h12}:${String(m).padStart(2, "0")} ${period}`;
  }

  // Human-readable description of the selected preset's time window, so it is
  // obvious what e.g. "Morning" or "Sundowning" actually covers.
  const heatmapTimeWindowLabel = computed(() => {
    const preset = TIME_PRESETS.find((p) => p.key === heatmapTimePreset.value);
    if (!preset || preset.start == null || preset.end == null) return "All times of day";
    const wraps = preset.start > preset.end;
    return `${_formatMinutes(preset.start)} – ${_formatMinutes(preset.end)}${wraps ? " (overnight)" : ""}`;
  });

  // ── Heatmap computed + actions ────────────────────────────────────────────
  const mappedHeatmapBins = computed(() => {
    const bins = heatmapState.data?.bins;
    if (!bins?.length) return [];
    const width = fpWidth.value;
    const height = fpHeight.value;
    const mpp = fpMpp.value;
    if (!width || !height || !mpp) return [];
    const maxWeight = bins.reduce((m, b) => Math.max(m, b.weight), 1);
    const binSizePx = (0.5 / (width * mpp)) * canvasW.value;
    return bins.map((bin) => ({
      key: `${bin.x_m}_${bin.y_m}`,
      canvasX: (bin.x_m / (width * mpp)) * canvasW.value,
      canvasY: (bin.y_m / (height * mpp)) * canvasH.value,
      canvasSize: binSizePx,
      opacity: 0.2 + 0.8 * (bin.weight / maxWeight),
    }));
  });

  // Parse "HH:MM" into minutes since midnight.
  function _timeStrToMinutes(t) {
    const [h, m] = t.split(":").map((v) => parseInt(v, 10));
    if (Number.isNaN(h) || Number.isNaN(m)) return null;
    return h * 60 + m;
  }

  // Advance a "YYYY-MM-DD" calendar date by one day (pure UTC arithmetic, so the
  // browser timezone never shifts the date).
  function _nextCalendarDay(dateStr) {
    const [y, mo, d] = dateStr.split("-").map((v) => parseInt(v, 10));
    const dt = new Date(Date.UTC(y, mo - 1, d));
    dt.setUTCDate(dt.getUTCDate() + 1);
    return dt.toISOString().slice(0, 10);
  }

  // Resolve the absolute UTC [start, end) window from the date-range selection.
  function _resolveDateWindow() {
    if (heatmapDatePreset.value === "custom") {
      // Local calendar day boundaries -> UTC. End is exclusive start-of-next-day
      // so the whole "To" day is included.
      return {
        start: localDateToUTCISO(heatmapStartDate.value, "00:00"),
        end: localDateToUTCISO(_nextCalendarDay(heatmapEndDate.value), "00:00"),
      };
    }
    const preset = DATE_PRESETS.find((p) => p.key === heatmapDatePreset.value);
    const now = Date.now();
    return {
      start: new Date(now - preset.hours * 3600_000).toISOString(),
      end: new Date(now).toISOString(),
    };
  }

  // Resolve the local time-of-day window in minutes (both null = all day).
  function _resolveTimeWindow() {
    if (heatmapTimePreset.value === "custom") {
      return {
        start: _timeStrToMinutes(heatmapStartTime.value),
        end: _timeStrToMinutes(heatmapEndTime.value),
      };
    }
    const preset = TIME_PRESETS.find((p) => p.key === heatmapTimePreset.value);
    return { start: preset.start, end: preset.end };
  }

  async function runHeatmap() {
    if (!heatmapPersonId.value || !heatmapRangeReady.value || !heatmapTimeReady.value) return;
    const window = _resolveDateWindow();
    if (!window.start || !window.end) return;
    const time = _resolveTimeWindow();
    await heatmapActions.fetchHeatmap(
      heatmapPersonId.value,
      window.start,
      window.end,
      time.start,
      time.end,
    );
  }

  function onHeatmapMouseDown(e) {
    heatmapZoom.actions.startPan(e);
  }

  watch(
    () => mode.value,
    async (newMode) => {
      if (newMode === "heatmap" && heatmapPersons.value.length === 0) {
        try {
          heatmapPersons.value = await api.getPersons();
        } catch {
          // non-critical; user sees empty dropdown
        }
      }
    },
  );

  return {
    heatmapZoom,
    heatmapPersonId,
    heatmapPersons,
    heatmapState,
    appTzLabel,
    DATE_PRESETS,
    heatmapDatePreset,
    heatmapStartDate,
    heatmapEndDate,
    TIME_PRESETS,
    heatmapTimePreset,
    heatmapStartTime,
    heatmapEndTime,
    heatmapRangeReady,
    heatmapTimeReady,
    heatmapTimeWindowLabel,
    mappedHeatmapBins,
    runHeatmap,
    onHeatmapMouseDown,
  };
}
