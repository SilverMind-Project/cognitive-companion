import { computed, reactive } from "vue";
import { useCanvasZoom } from "@/composables/useCanvasZoom.js";

const VALID_SPACES = new Set(["normalized", "ratio", "natural", "metres"]);

function assertFiniteNumber(value, label) {
  if (!Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
}

function clamp01(value) {
  assertFiniteNumber(value, "coordinate");
  return Math.max(0, Math.min(1, value));
}

function roundCoord(value) {
  return Number(value.toFixed(6));
}

export function calculateContentRect({
  naturalWidth,
  naturalHeight,
  boxWidth,
  boxHeight,
  offsetX = 0,
  offsetY = 0,
}) {
  assertFiniteNumber(naturalWidth, "naturalWidth");
  assertFiniteNumber(naturalHeight, "naturalHeight");
  assertFiniteNumber(boxWidth, "boxWidth");
  assertFiniteNumber(boxHeight, "boxHeight");

  if (naturalWidth <= 0 || naturalHeight <= 0 || boxWidth <= 0 || boxHeight <= 0) {
    return {
      naturalWidth,
      naturalHeight,
      width: 0,
      height: 0,
      offsetX,
      offsetY,
    };
  }

  const naturalRatio = naturalWidth / naturalHeight;
  const boxRatio = boxWidth / boxHeight;

  if (naturalRatio > boxRatio) {
    const contentHeight = boxWidth / naturalRatio;
    return {
      naturalWidth,
      naturalHeight,
      width: boxWidth,
      height: contentHeight,
      offsetX,
      offsetY: offsetY + (boxHeight - contentHeight) / 2,
    };
  }

  const contentWidth = boxHeight * naturalRatio;
  return {
    naturalWidth,
    naturalHeight,
    width: contentWidth,
    height: boxHeight,
    offsetX: offsetX + (boxWidth - contentWidth) / 2,
    offsetY,
  };
}

function requireSpace(space) {
  if (!VALID_SPACES.has(space)) {
    throw new Error(`Unsupported spatial coordinate space: ${space}`);
  }
}

function requireDimensions({ naturalWidth, naturalHeight }, space) {
  if (space === "normalized" || space === "ratio") return;
  if (
    !Number.isFinite(naturalWidth) ||
    naturalWidth <= 0 ||
    !Number.isFinite(naturalHeight) ||
    naturalHeight <= 0
  ) {
    throw new Error(`${space} coordinate conversion requires naturalWidth and naturalHeight`);
  }
}

function requireMpp(mpp) {
  if (!Number.isFinite(mpp) || mpp <= 0) {
    throw new Error("metres coordinate conversion requires a positive mpp");
  }
}

function normalizedPointToSpace(point, space, options = {}) {
  requireSpace(space);
  requireDimensions(options, space);
  const [x, y] = point;

  if (space === "normalized" || space === "ratio") return [roundCoord(x), roundCoord(y)];
  if (space === "natural")
    return [roundCoord(x * options.naturalWidth), roundCoord(y * options.naturalHeight)];

  requireMpp(options.mpp);
  return [
    roundCoord(x * options.naturalWidth * options.mpp),
    roundCoord(y * options.naturalHeight * options.mpp),
  ];
}

function spacePointToNormalized(point, space, options = {}) {
  requireSpace(space);
  requireDimensions(options, space);
  const [x, y] = point;

  if (space === "normalized" || space === "ratio")
    return [roundCoord(clamp01(x)), roundCoord(clamp01(y))];
  if (space === "natural")
    return [
      roundCoord(clamp01(x / options.naturalWidth)),
      roundCoord(clamp01(y / options.naturalHeight)),
    ];

  requireMpp(options.mpp);
  return [
    roundCoord(clamp01(x / (options.naturalWidth * options.mpp))),
    roundCoord(clamp01(y / (options.naturalHeight * options.mpp))),
  ];
}

function convertRect(rect, pointConverter) {
  const p1 = pointConverter([rect.x, rect.y]);
  const p2 = pointConverter([rect.x + rect.w, rect.y + rect.h]);
  return {
    ...rect,
    x: roundCoord(Math.min(p1[0], p2[0])),
    y: roundCoord(Math.min(p1[1], p2[1])),
    w: roundCoord(Math.abs(p2[0] - p1[0])),
    h: roundCoord(Math.abs(p2[1] - p1[1])),
  };
}

export function convertShapeToSpace(shape, space, options = {}) {
  const convert = (point) => normalizedPointToSpace(point, space, options);
  if (shape.type === "rect") return convertRect(shape, convert);
  if (shape.type === "point") return { ...shape, point: convert(shape.point) };
  return { ...shape, points: (shape.points ?? []).map(convert) };
}

export function convertShapeFromSpace(shape, space, options = {}) {
  const convert = (point) => spacePointToNormalized(point, space, options);
  if (shape.type === "rect") return convertRect(shape, convert);
  if (shape.type === "point") return { ...shape, point: convert(shape.point) };
  return { ...shape, points: (shape.points ?? []).map(convert) };
}

export function useSpatialCanvas(options = {}) {
  const {
    naturalWidth = 0,
    naturalHeight = 0,
    coordSpace = "normalized",
    mpp = null,
    zoomOptions = {},
  } = options;

  const state = reactive({
    naturalWidth,
    naturalHeight,
    viewportWidth: 0,
    viewportHeight: 0,
    viewportOffsetX: 0,
    viewportOffsetY: 0,
  });

  const zoom = useCanvasZoom(zoomOptions);

  const contentRect = computed(() =>
    calculateContentRect({
      naturalWidth: state.naturalWidth,
      naturalHeight: state.naturalHeight,
      boxWidth: state.viewportWidth,
      boxHeight: state.viewportHeight,
      offsetX: state.viewportOffsetX,
      offsetY: state.viewportOffsetY,
    }),
  );

  function adapterOptions() {
    return {
      naturalWidth: state.naturalWidth,
      naturalHeight: state.naturalHeight,
      mpp,
    };
  }

  function setViewport({
    width,
    height,
    offsetX = 0,
    offsetY = 0,
    imageNaturalWidth,
    imageNaturalHeight,
  }) {
    assertFiniteNumber(width, "viewport width");
    assertFiniteNumber(height, "viewport height");
    state.viewportWidth = Math.max(0, width);
    state.viewportHeight = Math.max(0, height);
    state.viewportOffsetX = offsetX;
    state.viewportOffsetY = offsetY;
    if (imageNaturalWidth != null) state.naturalWidth = imageNaturalWidth;
    if (imageNaturalHeight != null) state.naturalHeight = imageNaturalHeight;
  }

  function syncFromImageElement(imgEl) {
    if (!imgEl) return;
    setViewport({
      width: imgEl.offsetWidth,
      height: imgEl.offsetHeight,
      offsetX: imgEl.offsetLeft,
      offsetY: imgEl.offsetTop,
      imageNaturalWidth: imgEl.naturalWidth || state.naturalWidth,
      imageNaturalHeight: imgEl.naturalHeight || state.naturalHeight,
    });
  }

  function toNormalized(point, source = "container") {
    const rect = contentRect.value;
    if (rect.width <= 0 || rect.height <= 0) {
      throw new Error("Cannot map spatial point before contentRect has non-zero dimensions");
    }

    const local = source === "container" ? zoom.containerToLocal(point.x, point.y) : point;

    return [
      roundCoord(clamp01((local.x - rect.offsetX) / rect.width)),
      roundCoord(clamp01((local.y - rect.offsetY) / rect.height)),
    ];
  }

  function fromNormalized(point, target = "content") {
    const rect = contentRect.value;
    const x = roundCoord(point[0] * rect.width);
    const y = roundCoord(point[1] * rect.height);
    if (target === "content") return { x, y };
    return {
      x: roundCoord(x + rect.offsetX),
      y: roundCoord(y + rect.offsetY),
    };
  }

  function toEmit(shape, space = coordSpace) {
    return convertShapeToSpace(shape, space, adapterOptions());
  }

  function fromEmit(shape, space = coordSpace) {
    return convertShapeFromSpace(shape, space, adapterOptions());
  }

  return {
    state,
    contentRect,
    toNormalized,
    fromNormalized,
    toEmit,
    fromEmit,
    zoom,
    actions: {
      setViewport,
      syncFromImageElement,
    },
  };
}
