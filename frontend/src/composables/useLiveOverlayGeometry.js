// Scale SVG elements by both native frame size and selected layout. SVG text
// lives in viewBox units, so a 1920px frame rendered in a 4-up tile needs much
// larger user-space font values than the same frame rendered full width.
const TILE_ESTIMATE_PX = {
  1: 960,
  4: 520,
  9: 340,
  16: 260,
};

/** Per-tile SVG overlay sizing, parameterized by the live view's current layout (1/4/9/16). */
export function useLiveOverlayGeometry(layoutRef) {
  function tileEstimatePx() {
    return TILE_ESTIMATE_PX[layoutRef.value] || 520;
  }

  function overlayUnits(cam, cssPx) {
    return Math.round(cssPx * ((cam?.frame_width || 1920) / tileEstimatePx()));
  }

  function labelFontSize(cam) {
    const targetPx = layoutRef.value === 1 ? 13 : layoutRef.value === 4 ? 11 : 10;
    return overlayUnits(cam, targetPx);
  }
  function smallFontSize(cam) {
    const targetPx = layoutRef.value === 1 ? 11 : layoutRef.value === 4 ? 10 : 9;
    return overlayUnits(cam, targetPx);
  }
  // Halo stroke-width: ~20% of the label font-size, minimum 2 SVG units.
  // Keeps the dark outline proportional regardless of layout or frame resolution.
  // ~15% of font-size keeps the halo thin — just enough separation without
  // distorting letter shapes (industry cartographic standard).
  function labelHaloStroke(cam) {
    return Math.max(2, Math.round(labelFontSize(cam) * 0.15));
  }
  function overlayStroke(cam, multiplier = 1) {
    const targetPx = layoutRef.value === 1 ? 1.45 : layoutRef.value === 4 ? 1.25 : 1.1;
    return Math.max(1, overlayUnits(cam, targetPx * multiplier));
  }
  function badgeRadius(cam) {
    const targetPx = layoutRef.value === 1 ? 11 : layoutRef.value === 4 ? 10 : 9;
    return overlayUnits(cam, targetPx);
  }
  function evidenceBarY(cam, row) {
    const pad = evidencePad(cam);
    const textBand = Math.round(evidenceFontSize(cam) * 1.35);
    const gap = Math.max(2, Math.round(evidenceBarHeight(cam) * 0.55));
    return pad + textBand + row * (evidenceBarHeight(cam) + gap);
  }
  function evidenceBarHeight(cam) {
    const targetPx = layoutRef.value === 1 ? 4 : layoutRef.value === 4 ? 4 : 3.5;
    return Math.max(2, overlayUnits(cam, targetPx));
  }
  function evidencePillWidth(cam) {
    const targetPx =
      layoutRef.value === 1 ? 92 : layoutRef.value === 4 ? 84 : layoutRef.value === 9 ? 76 : 70;
    return overlayUnits(cam, targetPx);
  }
  function evidencePillHeight(cam) {
    const targetPx = layoutRef.value === 1 ? 32 : layoutRef.value === 4 ? 30 : 28;
    return overlayUnits(cam, targetPx);
  }
  function evidencePad(cam) {
    return overlayUnits(cam, layoutRef.value === 1 ? 5 : 4.5);
  }
  function evidenceFontSize(cam) {
    const targetPx = layoutRef.value === 1 ? 11 : layoutRef.value === 4 ? 10 : 9;
    return overlayUnits(cam, targetPx);
  }
  function evidenceTextY(cam) {
    return Math.round(evidencePad(cam) + evidenceFontSize(cam) * 0.62);
  }
  function evidencePillX(det, cam) {
    const pad = overlayUnits(cam, 4);
    return Math.max(pad, (det.bbox.x_max || 0) - evidencePillWidth(cam) - pad);
  }
  function evidencePillY(det, cam) {
    const outsideY = (det.bbox.y_min || 0) - evidencePillHeight(cam) - overlayUnits(cam, 3);
    if (outsideY >= overlayUnits(cam, 2)) return outsideY;
    return (det.bbox.y_max || 0) + overlayUnits(cam, 3);
  }
  function evidenceBarTrackWidth(cam) {
    return Math.max(1, evidencePillWidth(cam) - evidencePad(cam) * 2);
  }
  function evidenceBarWidth(det, cam, key) {
    const prob = Math.max(0, Math.min(1, Number(det.evidence?.[key] || 0)));
    return Math.round(evidenceBarTrackWidth(cam) * prob);
  }
  function evidenceLabel(det) {
    const pct = Math.round(Math.max(0, Math.min(1, det.evidence?.top_prob || 0)) * 100);
    return det.evidence?.face_anchor_used ? `face ${pct}%` : `${pct}% match`;
  }
  function evidenceTooltip(det) {
    const top = Math.round(Math.max(0, Math.min(1, det.evidence?.top_prob || 0)) * 100);
    const second = Math.round(Math.max(0, Math.min(1, det.evidence?.top2_prob || 0)) * 100);
    const source = det.evidence?.face_anchor_used ? "face anchor" : "re-id";
    return `Evidence: ${top}% top match, ${second}% second match (${source})`;
  }
  function labelOffsetY(cam) {
    return Math.round(labelFontSize(cam) * 0.92);
  }
  function labelOffsetX(cam) {
    return Math.round(labelFontSize(cam) * 0.22);
  }
  function crownOffsetY(cam) {
    return Math.round(labelFontSize(cam) * 1.0);
  }

  function postureLabelY(det, cam) {
    const fs = labelFontSize(cam);
    const yOff = labelOffsetY(cam) + fs + 4;
    return (det.bbox.y_min || 0) + yOff;
  }

  function poseX(det, keypointIdx) {
    const kp = det.pose_keypoints[keypointIdx];
    if (!kp) return 0;
    const bw = (det.bbox.x_max || 0) - (det.bbox.x_min || 0);
    return (det.bbox.x_min || 0) + kp.x * bw;
  }

  function poseY(det, keypointIdx) {
    const kp = det.pose_keypoints[keypointIdx];
    if (!kp) return 0;
    const bh = (det.bbox.y_max || 0) - (det.bbox.y_min || 0);
    return (det.bbox.y_min || 0) + kp.y * bh;
  }

  function trailPoints(det, cam) {
    if (!det.trail || !cam) return "";
    const fw = cam.frame_width || 1920;
    const fh = cam.frame_height || 1080;
    return det.trail.map((t) => `${t.x * fw},${t.y * fh}`).join(" ");
  }

  return {
    labelFontSize,
    smallFontSize,
    labelHaloStroke,
    overlayStroke,
    badgeRadius,
    evidenceBarY,
    evidenceBarHeight,
    evidencePillWidth,
    evidencePillHeight,
    evidencePad,
    evidenceFontSize,
    evidenceTextY,
    evidencePillX,
    evidencePillY,
    evidenceBarWidth,
    evidenceLabel,
    evidenceTooltip,
    labelOffsetX,
    labelOffsetY,
    crownOffsetY,
    postureLabelY,
    poseX,
    poseY,
    trailPoints,
  };
}
