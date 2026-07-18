import { ref, computed } from "vue";
import { household } from "@/services/household";
import { useCanvasZoom } from "@/composables/useCanvasZoom.js";

/**
 * Floor-plan image upload: file selection, the click-two-points / total-width
 * scale picker, and the optional crop-to-trim-margins workspace. Bundled into
 * one composable (rather than three) because the three clusters share mutable
 * state (uploadWidth/uploadHeight, the blob URL, the pre-crop File) tightly
 * enough that splitting them would mean threading that state back and forth.
 *
 * Deliberately NOT shared with the orchestrator: this state has no watch(mode)
 * entry-timing dependency and nothing outside the upload panel reads it, so it
 * is owned by (and lives and dies with) FloorPlanUploadPanel.vue. Switching
 * away from "upload" mode and back resets it -- an accepted, filed cost, not a
 * behavior this composable is trying to preserve across mode switches.
 *
 * `floorPlanUrl`, `fpWidth`, `fpHeight`, and `fpMpp` are read-only refs owned
 * by the parent (useFloorPlanCanvas), passed in so the scale picker can fall
 * back to the already-saved floor plan image, its dimensions, and pre-fill
 * the saved scale.
 */
export function useFloorPlanUpload(notify, floorPlanUrl, fpWidth, fpHeight, fpMpp, onSaved) {
  const uploading = ref(false);
  const uploadFile = ref(null);
  const uploadWidth = ref(null);
  const uploadHeight = ref(null);
  const uploadMpp = ref(null);
  const scaleMethod = ref("pickpoints");
  const SCALE_METHOD_OPTIONS = [
    { value: "pickpoints", label: "Two points", icon: "mdi-cursor-pointer" },
    { value: "realwidth", label: "Total width", icon: "mdi-ruler" },
  ];
  const uploadRealWidth = ref(null);

  // Method C: click-on-image scale picker.
  const scalePoints = ref([]); // up to 2 normalized [x, y] points
  const scaleMeasuredM = ref(null); // real-world distance in metres
  const scaleImgEl = ref(null);
  const scaleImgRect = ref(null);
  // C19 fix: this must be a ref, not a plain variable. scalePickerImageUrl below reads it
  // inside a computed(); a plain `let` is never tracked, so selecting a new file never
  // invalidated the computed's cache and the preview kept showing the previously-saved
  // floor plan. Confirmed via `git stash` that this bug predates the M21 refactor.
  const _uploadBlobUrl = ref(null); // blob URL lifecycle managed manually
  let _originalFile = null; // pre-crop File object, kept for reset (never read reactively)
  let _resizeObserver = null; // keeps scaleImgRect current on resize

  const scaleOuterRef = ref(null);
  const scaleZoom = useCanvasZoom();
  const cropOuterRef = ref(null);
  const cropZoom = useCanvasZoom();

  // Crop state — visual draw-to-crop bounding box on the image.
  // cropRect is normalised [0,1] relative to the image content area.
  const cropActive = ref(false);
  const cropRect = ref({ x: 0.05, y: 0.05, w: 0.9, h: 0.9 });
  // cropDrag: { type: 'draw'|'nw'|'ne'|'se'|'sw'|'move', startX, startY, startRect }
  const cropDrag = ref(null);
  const cropImgRef = ref(null); // ref for the crop preview <img>
  const cropImgRect = ref(null); // { width, height, offsetX, offsetY } like scaleImgRect

  // ── Scale picker computed ─────────────────────────────────────────────────
  // URL shown in the Method C image picker: prefer the newly selected file,
  // fall back to the already-saved floor plan.
  const scalePickerImageUrl = computed(() => _uploadBlobUrl.value || floorPlanUrl.value);

  // Pixel distance between the two scale points, measured in original image pixels.
  const scalePixelDistance = computed(() => {
    if (scalePoints.value.length < 2) return 0;
    const w = uploadWidth.value || fpWidth.value || (scaleImgEl.value?.naturalWidth ?? 0);
    const h = uploadHeight.value || fpHeight.value || (scaleImgEl.value?.naturalHeight ?? 0);
    if (!w || !h) return 0;
    const [p1, p2] = scalePoints.value;
    const dx = (p2[0] - p1[0]) * w;
    const dy = (p2[1] - p1[1]) * h;
    return Math.sqrt(dx * dx + dy * dy);
  });

  // Computed mpp from Method C.
  const scaleComputedMpp = computed(() => {
    if (!scaleMeasuredM.value || scalePixelDistance.value < 1) return null;
    return (scaleMeasuredM.value / scalePixelDistance.value).toFixed(6);
  });

  // ── Upload helpers ────────────────────────────────────────────────────────
  function onFileSelected(fileOrArray) {
    const file = Array.isArray(fileOrArray) ? fileOrArray[0] : fileOrArray;
    // Revoke previous blob URL.
    if (_uploadBlobUrl.value) {
      URL.revokeObjectURL(_uploadBlobUrl.value);
      _uploadBlobUrl.value = null;
    }
    // Reset state for the new image.
    scalePoints.value = [];
    scaleMeasuredM.value = null;
    scaleImgRect.value = null;
    cropActive.value = false;
    cropRect.value = { x: 0.05, y: 0.05, w: 0.9, h: 0.9 };
    if (!file) return;

    _originalFile = file;
    _uploadBlobUrl.value = URL.createObjectURL(file);
    // Read natural dimensions without a visible img element.
    const probe = new Image();
    probe.onload = () => {
      uploadWidth.value = probe.naturalWidth;
      uploadHeight.value = probe.naturalHeight;
      // Recompute mpp if real width was already set.
      if (uploadRealWidth.value && probe.naturalWidth) {
        uploadMpp.value = parseFloat((uploadRealWidth.value / probe.naturalWidth).toFixed(6));
      }
    };
    probe.src = _uploadBlobUrl.value;
  }

  function onScaleImageLoad() {
    if (!scaleImgEl.value) return;
    // Use offset* (pre-transform layout) so zoom/pan don't distort the overlay.
    const elW = scaleImgEl.value.offsetWidth;
    const elH = scaleImgEl.value.offsetHeight;
    const elLeft = scaleImgEl.value.offsetLeft;
    const elTop = scaleImgEl.value.offsetTop;
    const nw = uploadWidth.value || scaleImgEl.value.naturalWidth;
    const nh = uploadHeight.value || scaleImgEl.value.naturalHeight;
    // Populate upload fields from saved data when no file was selected.
    if (!uploadWidth.value && nw) uploadWidth.value = nw;
    if (!uploadHeight.value && nh) uploadHeight.value = nh;
    if (!uploadMpp.value && fpMpp.value) uploadMpp.value = fpMpp.value;
    if (!nw || !nh || !elW || !elH) {
      scaleImgRect.value = { width: elW, height: elH, offsetX: elLeft, offsetY: elTop };
      return;
    }
    // Compute the actual image content rect within the element accounting for
    // object-fit: contain letterboxing. Normalised scale-point coordinates and
    // the SVG overlay must use content-relative values so they align with what
    // the user actually sees.
    const imgAspect = nw / nh;
    const elAspect = elW / elH;
    let cw, ch, ox, oy;
    if (imgAspect > elAspect) {
      // image wider than element → letterbox top/bottom
      cw = elW;
      ch = elW / imgAspect;
      ox = 0;
      oy = (elH - ch) / 2;
    } else {
      // image taller than element → letterbox left/right
      ch = elH;
      cw = elH * imgAspect;
      ox = (elW - cw) / 2;
      oy = 0;
    }
    scaleImgRect.value = { width: cw, height: ch, offsetX: elLeft + ox, offsetY: elTop + oy };

    // Keep content rect current when the container resizes.
    if (!_resizeObserver) {
      _resizeObserver = new ResizeObserver(() => onScaleImageLoad());
      _resizeObserver.observe(scaleImgEl.value);
    }
  }

  function onScaleImageClick(e) {
    if (scalePoints.value.length >= 2 || !scaleImgEl.value) return;
    // Ignore when the user was panning (drag exceeded threshold).
    if (scaleZoom.state.didPan) {
      scaleZoom.state.didPan = false;
      return;
    }
    if (!scaleImgRect.value || !scaleOuterRef.value) return;
    const cr = scaleImgRect.value;
    const outerRect = scaleOuterRef.value.getBoundingClientRect();
    // Map through zoom/pan to get coordinates in the pre-transform space.
    const local = scaleZoom.containerToLocal(e.clientX - outerRect.left, e.clientY - outerRect.top);
    // Then normalise to [0,1] within the image content area.
    const x = (local.x - cr.offsetX) / cr.width;
    const y = (local.y - cr.offsetY) / cr.height;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    scalePoints.value = [
      ...scalePoints.value,
      [parseFloat(x.toFixed(4)), parseFloat(y.toFixed(4))],
    ];
  }

  /** Start a potential pan on mousedown of the scale picker inner area. */
  function onScalePickerMouseDown(e) {
    scaleZoom.actions.startPan(e);
  }

  function onScaleMeasuredChange() {
    if (scaleComputedMpp.value) {
      uploadMpp.value = parseFloat(scaleComputedMpp.value);
    }
  }

  function onRealWidthChange() {
    if (uploadRealWidth.value && uploadWidth.value) {
      uploadMpp.value = parseFloat((uploadRealWidth.value / uploadWidth.value).toFixed(6));
    }
  }

  // ── Crop ──────────────────────────────────────────────────────────────────

  /** Corner handle positions (normalised) for the crop rectangle. */
  const cropHandles = computed(() => {
    const r = cropRect.value;
    return [
      { corner: "nw", x: r.x, y: r.y, cursor: "nwse-resize" },
      { corner: "ne", x: r.x + r.w, y: r.y, cursor: "nesw-resize" },
      { corner: "se", x: r.x + r.w, y: r.y + r.h, cursor: "nwse-resize" },
      { corner: "sw", x: r.x, y: r.y + r.h, cursor: "nesw-resize" },
    ];
  });

  function onCropImgLoad() {
    if (!cropImgRef.value) return;
    const img = cropImgRef.value;
    // Use offset* (pre-transform layout) so zoom doesn't distort the overlay.
    const elW = img.offsetWidth;
    const elH = img.offsetHeight;
    const elLeft = img.offsetLeft;
    const elTop = img.offsetTop;
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    if (!nw || !nh || !elW || !elH) return;
    const naturalRatio = nw / nh;
    const elRatio = elW / elH;
    let cw, ch, offX, offY;
    if (naturalRatio > elRatio) {
      cw = elW;
      ch = elW / naturalRatio;
      offX = 0;
      offY = (elH - ch) / 2;
    } else {
      ch = elH;
      cw = elH * naturalRatio;
      offX = (elW - cw) / 2;
      offY = 0;
    }
    cropImgRect.value = { width: cw, height: ch, offsetX: elLeft + offX, offsetY: elTop + offY };
  }

  function startCropMode() {
    cropRect.value = { x: 0.05, y: 0.05, w: 0.9, h: 0.9 };
    cropActive.value = true;
  }

  function resetCrop() {
    cropRect.value = { x: 0.05, y: 0.05, w: 0.9, h: 0.9 };
  }

  /** Convert a mouse event on the crop container to normalised [0,1] coords. */
  function cropEventToNorm(e) {
    if (!cropImgRef.value || !cropImgRect.value || !cropOuterRef.value) return null;
    const cr = cropImgRect.value;
    const outerRect = cropOuterRef.value.getBoundingClientRect();
    // Map through zoom to get coordinates in the pre-transform space.
    const local = cropZoom.containerToLocal(e.clientX - outerRect.left, e.clientY - outerRect.top);
    const nx = (local.x - cr.offsetX) / cr.width;
    const ny = (local.y - cr.offsetY) / cr.height;
    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
    return { x: nx, y: ny };
  }

  /** Start drawing a new crop rectangle from scratch, or pan when outside the image. */
  function onCropMouseDown(e) {
    if (!cropActive.value) return;
    const pt = cropEventToNorm(e);
    if (!pt) {
      // Click is in the letterbox area outside the image — pan instead of draw.
      cropZoom.actions.startPan(e);
      return;
    }
    cropDrag.value = { type: "draw", startX: pt.x, startY: pt.y, startRect: { ...cropRect.value } };
    window.addEventListener("mousemove", onCropMouseMove);
    window.addEventListener("mouseup", onCropMouseUp);
    e.preventDefault();
  }

  /** Start dragging a corner handle. */
  function onCropHandleDown(corner, e) {
    const pt = cropEventToNorm(e);
    if (!pt) return;
    cropDrag.value = { type: corner, startX: pt.x, startY: pt.y, startRect: { ...cropRect.value } };
    window.addEventListener("mousemove", onCropMouseMove);
    window.addEventListener("mouseup", onCropMouseUp);
  }

  function onCropMouseMove(e) {
    if (!cropDrag.value || !cropImgRef.value || !cropImgRect.value) return;
    const pt = cropEventToNorm(e);
    if (!pt) return;
    const d = cropDrag.value;
    const dx = pt.x - d.startX;
    const dy = pt.y - d.startY;
    const sr = d.startRect;

    let nx = sr.x,
      ny = sr.y,
      nw = sr.w,
      nh = sr.h;

    if (d.type === "draw") {
      // Drag to define a new rectangle.
      nx = Math.min(d.startX, pt.x);
      ny = Math.min(d.startY, pt.y);
      nw = Math.abs(pt.x - d.startX);
      nh = Math.abs(pt.y - d.startY);
    } else if (d.type === "move") {
      nx = Math.max(0, Math.min(1 - sr.w, sr.x + dx));
      ny = Math.max(0, Math.min(1 - sr.h, sr.y + dy));
    } else {
      // Corner resize — adjust whichever edges the corner controls.
      if (d.type.includes("n")) {
        ny = Math.min(sr.y + sr.h - 0.01, sr.y + dy);
        nh = sr.y + sr.h - ny;
      }
      if (d.type.includes("s")) {
        nh = Math.max(0.01, sr.h + dy);
      }
      if (d.type.includes("w")) {
        nx = Math.min(sr.x + sr.w - 0.01, sr.x + dx);
        nw = sr.x + sr.w - nx;
      }
      if (d.type.includes("e")) {
        nw = Math.max(0.01, sr.w + dx);
      }
      // Clamp to image bounds.
      nx = Math.max(0, nx);
      ny = Math.max(0, ny);
      nw = Math.min(1 - nx, nw);
      nh = Math.min(1 - ny, nh);
    }

    // Enforce minimum size.
    const minPx = 10;
    const pw = uploadWidth.value || 1448;
    const ph = uploadHeight.value || 1086;
    if (nw * pw < minPx) nw = minPx / pw;
    if (nh * ph < minPx) nh = minPx / ph;

    cropRect.value = { x: nx, y: ny, w: nw, h: nh };
  }

  function onCropMouseUp() {
    cropDrag.value = null;
    window.removeEventListener("mousemove", onCropMouseMove);
    window.removeEventListener("mouseup", onCropMouseUp);
  }

  async function applyCrop() {
    if (!_originalFile || !uploadWidth.value || !uploadHeight.value) return;

    const r = cropRect.value;
    const x = Math.round(uploadWidth.value * r.x);
    const y = Math.round(uploadHeight.value * r.y);
    const w = Math.round(uploadWidth.value * r.w);
    const h = Math.round(uploadHeight.value * r.h);
    if (w < 10 || h < 10) return;

    // Canvas-crop the image.
    const img = await new Promise((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = reject;
      el.src = _uploadBlobUrl.value;
    });

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, x, y, w, h, 0, 0, w, h);

    const croppedBlob = await new Promise((resolve) =>
      canvas.toBlob(resolve, _originalFile.type, 0.95),
    );

    const croppedFile = new File([croppedBlob], _originalFile.name, { type: _originalFile.type });
    uploadFile.value = croppedFile;
    if (_uploadBlobUrl.value) URL.revokeObjectURL(_uploadBlobUrl.value);
    _uploadBlobUrl.value = URL.createObjectURL(croppedBlob);
    uploadWidth.value = w;
    uploadHeight.value = h;

    cropActive.value = false;
    cropImgRect.value = null;
    scalePoints.value = [];
    scaleMeasuredM.value = null;
    scaleImgRect.value = null;
  }

  // ── Upload ────────────────────────────────────────────────────────────────
  async function uploadFloorPlan() {
    uploading.value = true;
    try {
      const fd = new FormData();
      if (uploadFile.value) fd.append("file", uploadFile.value[0] ?? uploadFile.value);
      if (uploadWidth.value) fd.append("floor_plan_width", String(uploadWidth.value));
      if (uploadHeight.value) fd.append("floor_plan_height", String(uploadHeight.value));
      if (uploadMpp.value) fd.append("floor_meters_per_pixel", String(uploadMpp.value));
      const data = await household.postFloorPlan(fd);
      onSaved(data);
      notify("Floor plan saved");
      uploadFile.value = null;
    } catch (e) {
      notify(e.message, "error");
    } finally {
      uploading.value = false;
    }
  }

  function dispose() {
    if (_uploadBlobUrl.value) {
      URL.revokeObjectURL(_uploadBlobUrl.value);
      _uploadBlobUrl.value = null;
    }
    if (_resizeObserver) {
      _resizeObserver.disconnect();
      _resizeObserver = null;
    }
  }

  return {
    uploading,
    uploadFile,
    uploadWidth,
    uploadHeight,
    uploadMpp,
    scaleMethod,
    SCALE_METHOD_OPTIONS,
    uploadRealWidth,
    scalePoints,
    scaleMeasuredM,
    scaleImgEl,
    scaleImgRect,
    scaleOuterRef,
    scaleZoom,
    cropOuterRef,
    cropZoom,
    cropActive,
    cropRect,
    cropImgRef,
    cropImgRect,
    cropHandles,
    scalePickerImageUrl,
    scalePixelDistance,
    scaleComputedMpp,
    onFileSelected,
    onScaleImageLoad,
    onScaleImageClick,
    onScalePickerMouseDown,
    onScaleMeasuredChange,
    onRealWidthChange,
    onCropImgLoad,
    startCropMode,
    resetCrop,
    onCropMouseDown,
    onCropHandleDown,
    applyCrop,
    uploadFloorPlan,
    dispose,
  };
}
