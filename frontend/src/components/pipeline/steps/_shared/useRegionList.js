// Shared rect-region list management for pipeline step config components
// (image_crop, region_presence). Interactive drag/resize/ratio-clamping
// lives in ImageCropCanvas.vue via composables/bboxGeometry.js; this module
// covers list-level operations only: add/remove a region row, generic field
// updates, id validation against the backend's `^[a-z][a-z0-9_]*$` pattern
// (config_schema in image_crop.py / region_presence.py), and a
// human-readable ratio summary. Both config components consume this so
// region-list editing never forks into two implementations.

const ID_PATTERN = /^[a-z][a-z0-9_]*$/;

export function isValidRegionId(id) {
  return typeof id === "string" && ID_PATTERN.test(id);
}

export function addRectRegion(regions) {
  const idx = (regions || []).length + 1;
  return [
    ...(regions || []),
    {
      id: `region_${idx}`,
      name: `Region ${idx}`,
      x: 0.1,
      y: 0.1,
      width: 0.3,
      height: 0.3,
    },
  ];
}

export function deleteRegion(regions, index) {
  const next = [...(regions || [])];
  next.splice(index, 1);
  return next;
}

export function updateRegionField(regions, index, field, value) {
  const next = [...(regions || [])];
  next[index] = { ...next[index], [field]: value };
  return next;
}

function toPercent(ratio) {
  if (ratio == null) return 0;
  return Math.round(ratio * 100);
}

export function rectRegionSummary(region) {
  return `${toPercent(region.width)}% wide x ${toPercent(region.height)}% tall, at (${toPercent(region.x)}%, ${toPercent(region.y)}%)`;
}
