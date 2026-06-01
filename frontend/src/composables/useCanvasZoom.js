import { reactive, ref, computed, onBeforeUnmount, getCurrentInstance } from "vue";

/**
 * Composable that adds mouse-wheel zoom and click-drag pan to a canvas/image area.
 *
 * Apply `state.transformStyle` to the inner content wrapper (the element that
 * contains both the <img> and its <svg> overlay).  The outer container must have
 * `overflow: hidden` and a defined height so the zoomed content is clipped.
 *
 * In click handlers that also serve as pan drag-start, check `state.didPan`
 * after mouseup — if true the user was dragging, not clicking.
 *
 * @param {Object} [options]
 * @param {number} [options.minZoom=0.2]
 * @param {number} [options.maxZoom=6]
 * @param {number} [options.wheelStep=0.08]  Fractional step per wheel tick
 * @param {number} [options.panThreshold=3]  Pixels to move before pan activates
 * @returns {{ state, containerToLocal, actions }}
 */
export function useCanvasZoom(options = {}) {
  const {
    minZoom = 0.2,
    maxZoom = 6,
    wheelStep = 0.08,
    panThreshold = 3,
  } = options;

  // ── state ───────────────────────────────────────────────────────────────
  const state = reactive({
    zoom: 1,
    panX: 0,
    panY: 0,

    /** True during an ongoing pan drag (post-threshold). */
    didPan: false,

    /** CSS transform string for the inner content wrapper. */
    transformStyle: computed(() =>
      `transform: translate(${state.panX}px, ${state.panY}px) scale(${state.zoom}); transform-origin: 0 0;`
    ),
  });

  // ── pan internals ───────────────────────────────────────────────────────
  let _panning = false;
  let _panStartClient = { x: 0, y: 0 };
  let _panStartOffset = { x: 0, y: 0 };

  // ── coordinate mapping ──────────────────────────────────────────────────
  /**
   * Convert a container-relative pixel coordinate into the local coordinate
   * system of the zoomed content (before the CSS transform is applied).
   *
   * @param {number} cx  container-relative x (e.g. clientX - containerRect.left)
   * @param {number} cy  container-relative y
   * @returns {{ x: number, y: number }}
   */
  function containerToLocal(cx, cy) {
    return {
      x: (cx - state.panX) / state.zoom,
      y: (cy - state.panY) / state.zoom,
    };
  }

  // ── actions ─────────────────────────────────────────────────────────────

  /**
   * Wheel handler — call on the outer container's @wheel.prevent.
   * Zooms toward the cursor position so the point under the mouse stays fixed.
   *
   * @param {WheelEvent} e
   */
  function onWheel(e) {
    const delta = e.deltaY > 0 ? -wheelStep : wheelStep;
    const newZoom = Math.max(minZoom, Math.min(maxZoom, state.zoom * (1 + delta)));
    if (newZoom === state.zoom) return;

    const rect = /** @type {HTMLElement} */ (e.currentTarget).getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const scale = newZoom / state.zoom;
    state.panX = mx - scale * (mx - state.panX);
    state.panY = my - scale * (my - state.panY);
    state.zoom = newZoom;
  }

  /**
   * Start a potential pan on mousedown.  Pan only activates after the mouse
   * has moved `panThreshold` pixels; a quick click won't trigger pan and
   * `state.didPan` stays false.  Use this when the same mousedown target
   * also handles click events (e.g. placing a vertex on an SVG overlay).
   *
   * @param {MouseEvent} e
   */
  function startPan(e) {
    if (e.button !== 0) return;
    _panStartClient = { x: e.clientX, y: e.clientY };
    _panStartOffset = { x: state.panX, y: state.panY };
    state.didPan = false;
    window.addEventListener("mousemove", _onPanCheck);
    window.addEventListener("mouseup", _endPan);
  }

  function _onPanCheck(e) {
    const dx = e.clientX - _panStartClient.x;
    const dy = e.clientY - _panStartClient.y;
    if (Math.abs(dx) > panThreshold || Math.abs(dy) > panThreshold) {
      // Threshold exceeded — activate real panning.
      _panning = true;
      state.didPan = true;
      window.removeEventListener("mousemove", _onPanCheck);
      window.addEventListener("mousemove", _onPanMove);
      // Apply the accumulated offset so the pan doesn't jump.
      state.panX = _panStartOffset.x + (e.clientX - _panStartClient.x);
      state.panY = _panStartOffset.y + (e.clientY - _panStartClient.y);
    }
  }

  function _onPanMove(e) {
    if (!_panning) return;
    state.panX = _panStartOffset.x + (e.clientX - _panStartClient.x);
    state.panY = _panStartOffset.y + (e.clientY - _panStartClient.y);
  }

  function _endPan() {
    _panning = false;
    window.removeEventListener("mousemove", _onPanCheck);
    window.removeEventListener("mousemove", _onPanMove);
    window.removeEventListener("mouseup", _endPan);
  }

  /** Zoom in by one step, centered on the container midpoint. */
  function zoomIn(containerEl) {
    const newZoom = Math.min(maxZoom, state.zoom * (1 + wheelStep * 2));
    if (!containerEl) { state.zoom = newZoom; return; }
    const rect = containerEl.getBoundingClientRect();
    const mx = rect.width / 2;
    const my = rect.height / 2;
    const scale = newZoom / state.zoom;
    state.panX = mx - scale * (mx - state.panX);
    state.panY = my - scale * (my - state.panY);
    state.zoom = newZoom;
  }

  /** Zoom out by one step, centered on the container midpoint. */
  function zoomOut(containerEl) {
    const newZoom = Math.max(minZoom, state.zoom / (1 + wheelStep * 2));
    if (!containerEl) { state.zoom = newZoom; return; }
    const rect = containerEl.getBoundingClientRect();
    const mx = rect.width / 2;
    const my = rect.height / 2;
    const scale = newZoom / state.zoom;
    state.panX = mx - scale * (mx - state.panX);
    state.panY = my - scale * (my - state.panY);
    state.zoom = newZoom;
  }

  /** Reset zoom and pan to defaults. */
  function reset() {
    state.zoom = 1;
    state.panX = 0;
    state.panY = 0;
  }

  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      _endPan();
    });
  }

  return {
    state,
    containerToLocal,
    actions: { onWheel, startPan, zoomIn, zoomOut, reset },
  };
}
