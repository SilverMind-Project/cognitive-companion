import { ref, shallowRef, computed, watch } from "vue";
import { identityColor } from "@/composables/useIdentityColor";
import { roomForCanvasPoint } from "@/composables/useFloorPlanProjection";
import { useCanvasZoom } from "@/composables/useCanvasZoom.js";
import { useWorldSnapshot } from "@/composables/useWorldSnapshot";

/**
 * Live-mode PH world snapshot: floor-projected markers, rAF-interpolated
 * smoothing, the active-persons sidebar list, and connection status. Bundled
 * as one composable because the interpolation loop, the marker projection,
 * and the derived sidebar data all read the same worldPhs stream and were a
 * single cohesive unit in the pre-extraction script.
 *
 * `fpWidth`/`fpHeight`/`fpMpp`/`canvasW`/`canvasH` (useFloorPlanCanvas) and
 * `rooms` (useFloorPlanRooms) are read-only refs owned by the orchestrator.
 */
export function useLiveWorldMarkers(fpWidth, fpHeight, fpMpp, canvasW, canvasH, rooms, router, maraudersState) {
  // liveZoom.state/actions are passed down to LiveFloorCanvas.vue, which owns
  // the actual container template ref locally (DOM refs must live in the SFC
  // that renders the ref="..." markup).
  const liveZoom = useCanvasZoom({ maxZoom: 5, minZoom: 0.3 });

  // N4: world snapshot (PH-driven floor plan markers)
  // WS lifecycle is managed inside useWorldSnapshot.
  const {
    phs: worldPhs,
    inferredRooms: worldInferredRooms,
    lastUpdate: worldLastUpdate,
    isStale: worldIsStale,
    wsStatus: worldWsStatus,
    trailBuffers,
  } = useWorldSnapshot();

  // Compute floor positions for world snapshot PHs
  const worldPhMarkers = computed(() => {
    const fp = {
      width: fpWidth.value,
      height: fpHeight.value,
      mpp: fpMpp.value,
      canvasW: canvasW.value,
      canvasH: canvasH.value,
    };
    const floorPlanReady = fp.width && fp.height && fp.mpp;
    if (!floorPlanReady) return [];
    return worldPhs.value
      .filter((ph) => !ph.uncalibrated)
      .map((ph) => {
        const [fx, fy] = ph.floor_xy_m || [0, 0];
        const x = (fx / (fp.width * fp.mpp)) * fp.canvasW;
        const y = (fy / (fp.height * fp.mpp)) * fp.canvasH;
        if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
        return {
          ph,
          x,
          y,
          color: ph.identity_color || identityColor(ph.identity_id || ph.ph_id),
          roomName: ph.room_name || roomForCanvasPoint(x, y, fp.canvasW, fp.canvasH, rooms.value),
        };
      })
      .filter(Boolean);
  });

  // Uncalibrated PH count for warning chip
  const uncalibratedPhCount = computed(() => worldPhs.value.filter((ph) => ph.uncalibrated).length);

  // ── Live floor plan interaction ────────────────────────────────────────────
  function onLiveZoomMouseDown(e) {
    liveZoom.actions.startPan(e);
  }

  function onPhClick(ph) {
    // Suppress navigation if the mousedown was actually a pan drag.
    if (liveZoom.state.didPan) {
      liveZoom.state.didPan = false;
      return;
    }
    router.push({ name: "CTSPeople", query: { ph_id: ph.ph_id || "" } });
  }

  // ── Smooth marker interpolation ───────────────────────────────────────────
  // The backend pushes cts_world_snapshot at ≤5 Hz (200 ms debounce). Without
  // interpolation each update causes an instantaneous position jump. A cubic
  // ease-out lerp over LERP_MS makes movement look continuous.
  //
  // Implementation notes:
  //   - LERP_MS < update interval so the tween finishes before the next arrives.
  //   - On each new snapshot the rAF is cancelled; the in-flight position becomes
  //     the new start point, so rapid updates never cause a jump to old coords.
  //   - New PHs have no prior position: they snap directly to their first location.
  //   - The loop stops itself once t ≥ 1, so idle scenes waste no rAF budget.

  const LERP_MS = 160; // ms — safely below the 200 ms backend debounce

  // ph_id → { x0, y0, x1, y1 } (start and target in SVG user units)
  const _interpState = new Map();
  const smoothedMarkers = shallowRef([]);
  let _rafId = null;
  let _animStart = 0;
  let _animTargets = /** @type {typeof worldPhMarkers.value | null} */ (null);

  // ── MARAUDERS M4 (separable) ────────────────────────────────────────────
  // Footprint fade clock — updated each rAF frame so MaraudersFloorMarkers can
  // compute opacity without running its own animation loop. Uses the Date.now()
  // epoch to match the trail-buffer timestamps in useWorldSnapshot (rAF's `now`
  // is performance.now(), a different epoch — do not use it here). To remove
  // marauders mode, delete this ref, the `keepForFootprints` lines in _lerp, and
  // the maraudersState watch below; the base interpolation loop is untouched.
  const footprintNow = ref(Date.now());

  function _cubicEaseOut(t) {
    return 1 - (1 - t) ** 3;
  }

  function _lerp(now) {
    const t = Math.min(1, (now - _animStart) / LERP_MS);
    const e = _cubicEaseOut(t);

    smoothedMarkers.value = (_animTargets ?? []).map((m) => {
      const id = m.ph.ph_id ?? m.ph.identity_id;
      const s = _interpState.get(id);
      if (!s || (s.x0 === s.x1 && s.y0 === s.y1)) return m;
      const x = s.x0 + (s.x1 - s.x0) * e;
      const y = s.y0 + (s.y1 - s.y0) * e;
      if (t >= 1) _interpState.set(id, { x0: x, y0: y, x1: x, y1: y });
      return { ...m, x, y };
    });

    // MARAUDERS M4 (separable): keep looping while footprints need continuous
    // opacity fade, and advance the fade clock. Static reduced-motion mode does
    // not need a 60fps loop. Without marauders, `keepForFootprints` is always
    // false and the loop behaves exactly as the base interpolation tween.
    const keepForFootprints = maraudersState.enabled && !maraudersState.reducedMotion;
    if (keepForFootprints) footprintNow.value = Date.now();

    if (t < 1 || keepForFootprints) {
      _rafId = requestAnimationFrame(_lerp);
    } else {
      _rafId = null;
      _animTargets = null;
    }
  }

  watch(
    worldPhMarkers,
    (newMarkers) => {
      if (_rafId !== null) {
        cancelAnimationFrame(_rafId);
        _rafId = null;
      }

      // Capture current in-flight positions as the new start so we never jump.
      for (const m of newMarkers) {
        const id = m.ph.ph_id ?? m.ph.identity_id;
        const prev = _interpState.get(id);
        // If no previous: snap (x0 === x1 — no lerp needed, _lerp returns m directly).
        _interpState.set(id, {
          x0: prev
            ? (smoothedMarkers.value.find((s) => (s.ph.ph_id ?? s.ph.identity_id) === id)?.x ?? m.x)
            : m.x,
          y0: prev
            ? (smoothedMarkers.value.find((s) => (s.ph.ph_id ?? s.ph.identity_id) === id)?.y ?? m.y)
            : m.y,
          x1: m.x,
          y1: m.y,
        });
      }

      // Remove state for PHs that have left the scene.
      const activeIds = new Set(newMarkers.map((m) => m.ph.ph_id ?? m.ph.identity_id));
      for (const id of _interpState.keys()) {
        if (!activeIds.has(id)) _interpState.delete(id);
      }

      _animTargets = newMarkers;
      _animStart = performance.now();
      _rafId = requestAnimationFrame(_lerp);
    },
    { immediate: true },
  );

  // MARAUDERS M4 (separable): restart the rAF loop when marauders mode is toggled
  // ON while the tween is idle (no snapshot arrived recently), so footstep fade
  // starts immediately. Safe to delete with the rest of the marauders additions.
  watch(
    () => maraudersState.enabled,
    (on) => {
      if (on && !maraudersState.reducedMotion && _rafId === null) {
        _animStart = performance.now();
        _rafId = requestAnimationFrame(_lerp);
      }
    },
  );

  // ── Computed ──────────────────────────────────────────────────────────────
  const worldMarkerByPhId = computed(() => {
    const byId = new Map();
    for (const marker of worldPhMarkers.value) {
      if (marker.ph?.ph_id) byId.set(marker.ph.ph_id, marker);
    }
    return byId;
  });

  const activePersons = computed(() => {
    return worldPhs.value
      .filter((ph) => ph.identity_id && ph.last_observed_at)
      .map((ph) => ({
        gtId: ph.ph_id,
        displayName: ph.identity_id || "UNKNOWN",
        color: identityColor(ph.identity_id || ph.ph_id),
        calibrated: !ph.uncalibrated,
        confidence: ph.posterior_top_prob ?? 0,
        lastSeen: new Date(ph.last_observed_at).getTime(),
        roomName: ph.room_name || worldMarkerByPhId.value.get(ph.ph_id)?.roomName || null,
        posture: ph.posture && ph.posture !== "unknown" ? ph.posture : null,
      }))
      .sort((a, b) => b.lastSeen - a.lastSeen);
  });

  const worldStatusLabel = computed(() => {
    if (worldWsStatus.value === "connecting") return "Connecting";
    if (worldWsStatus.value === "error" || worldWsStatus.value === "closed") return "Disconnected";
    return worldIsStale.value ? "Stale" : "Live";
  });

  const worldStatusColor = computed(() => {
    if (worldWsStatus.value === "error" || worldWsStatus.value === "closed") return "error";
    if (worldWsStatus.value === "connecting" || worldIsStale.value) return "warning";
    return "success";
  });

  const worldStatusIcon = computed(() => {
    if (worldWsStatus.value === "error" || worldWsStatus.value === "closed") return "mdi-wifi-off";
    if (worldWsStatus.value === "connecting") return "mdi-wifi-strength-1";
    return worldIsStale.value ? "mdi-clock-alert-outline" : "mdi-broadcast";
  });

  const worldWsStatusLabel = computed(() => {
    switch (worldWsStatus.value) {
      case "open":
        return "WebSocket connected";
      case "connecting":
        return "WebSocket connecting";
      case "error":
        return "WebSocket error";
      case "closed":
        return "WebSocket reconnecting";
      default:
        return "WebSocket disconnected";
    }
  });

  function dispose() {
    if (_rafId !== null) {
      cancelAnimationFrame(_rafId);
      _rafId = null;
    }
  }

  return {
    liveZoom,
    worldPhs,
    worldInferredRooms,
    worldLastUpdate,
    worldIsStale,
    worldWsStatus,
    trailBuffers,
    worldPhMarkers,
    uncalibratedPhCount,
    smoothedMarkers,
    footprintNow,
    activePersons,
    worldStatusLabel,
    worldStatusColor,
    worldStatusIcon,
    worldWsStatusLabel,
    onLiveZoomMouseDown,
    onPhClick,
    dispose,
  };
}
