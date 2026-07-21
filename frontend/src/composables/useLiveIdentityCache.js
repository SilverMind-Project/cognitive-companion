/**
 * Identity smoothing/merging for the CTS live view: fills in last-known identity for
 * detections that lack one this frame, and low-pass-filters pose keypoints across frames.
 *
 * Identity caches — three layers, consulted in order:
 *
 *  1. ph_id cache  (5 min TTL) — most stable; one GT per person per session.
 *  2. detection_id cache      (30 s TTL)  — covers same-detection identity drops.
 *  3. position cache         (5 s TTL)   — last resort when both IDs are empty
 *     (the ~2-frame window while BoT-SORT confirms a new local track before
 *     it gets a detection_id or is merged back into the GT).  Picks the cached
 *     entry whose bbox overlaps the current detection most.
 */

const PH_IDENTITY_TTL_MS = 300_000;
const DETECTION_IDENTITY_TTL_MS = 30_000;
const POSITION_IDENTITY_TTL_MS = 5_000;
const POSITION_IOU_MIN = 0.25; // require ≥25% bbox overlap

// Per-detection keypoint EMA smoothing to reduce frame-to-frame jitter.
// Each detection's 17 keypoints (x, y only) are blended with the previous
// frame's values at alpha=0.35 so the skeleton overlay moves smoothly.
const KEYPOINT_SMOOTH_ALPHA = 0.65;

function _cacheEntry(d, nowMs) {
  return {
    identity_id: d.identity_id,
    display_name: d.display_name,
    identity_confidence: d.identity_confidence,
    lastSeenMs: nowMs,
  };
}

function _bboxIoU(a, b) {
  const ix1 = Math.max(a.x_min, b.x_min),
    iy1 = Math.max(a.y_min, b.y_min);
  const ix2 = Math.min(a.x_max, b.x_max),
    iy2 = Math.min(a.y_max, b.y_max);
  if (ix2 <= ix1 || iy2 <= iy1) return 0;
  const inter = (ix2 - ix1) * (iy2 - iy1);
  const aA = (a.x_max - a.x_min) * (a.y_max - a.y_min);
  const bA = (b.x_max - b.x_min) * (b.y_max - b.y_min);
  return inter / (aA + bA - inter);
}

function _applyIdentity(d, entry, action, cameraId) {
  console.debug("[cts_live] identity_cache", {
    action,
    camera_id: cameraId,
    ph_id: d.ph_id || "",
    detection_id: d.detection_id || "",
    identity_id: entry.identity_id,
  });
  return {
    ...d,
    identity_id: entry.identity_id,
    display_name: entry.display_name,
    identity_confidence: entry.identity_confidence,
  };
}

/** Creates one independent set of identity/keypoint caches for a live view instance. */
export function useLiveIdentityCache() {
  const phIdentityCache = {}; // ph_id → {identity_id, display_name, identity_confidence, lastSeenMs}
  const detectionIdentityCache = {}; // detection_id      → {identity_id, display_name, identity_confidence, lastSeenMs}
  const positionIdentityCache = {}; // camera_id        → [{bbox, identity_id, display_name, identity_confidence, lastSeenMs}]
  const keypointSmoothState = {}; // { detection_id: [{x, y} x 17] }

  function mergeIdentityCache(detections, cameraId = "unknown") {
    if (!detections) return detections;
    const nowMs = Date.now();

    // --- Pass 1: populate caches from detections that already have an identity ---
    const freshPositions = [];
    for (const d of detections) {
      if (!d.identity_id) continue;
      const entry = _cacheEntry(d, nowMs);
      if (d.ph_id) phIdentityCache[d.ph_id] = entry;
      if (d.detection_id) detectionIdentityCache[d.detection_id] = entry;
      if (d.bbox) freshPositions.push({ bbox: d.bbox, ...entry });
    }
    if (freshPositions.length) positionIdentityCache[cameraId] = freshPositions;

    // --- Pass 2: fill identity for detections that lack one ---
    return detections.map((d) => {
      if (d.identity_id) return d;

      // 1. Global-track cache (most stable — session-lifetime key).
      if (d.ph_id) {
        const c = phIdentityCache[d.ph_id];
        if (c && nowMs - c.lastSeenMs <= PH_IDENTITY_TTL_MS)
          return _applyIdentity(d, c, "gt_cache_hit", cameraId);
      }

      // 2. Detection cache (covers same-detection brief identity drops).
      if (d.detection_id) {
        const c = detectionIdentityCache[d.detection_id];
        if (c && nowMs - c.lastSeenMs <= DETECTION_IDENTITY_TTL_MS)
          return _applyIdentity(d, c, "detection_cache_hit", cameraId);
      }

      // 3. Position cache — fires when both IDs are empty (new unconfirmed track).
      //    Pick the cached bbox with the highest IoU to this detection's bbox.
      if (d.bbox) {
        const recent = (positionIdentityCache[cameraId] || []).filter(
          (e) => nowMs - e.lastSeenMs <= POSITION_IDENTITY_TTL_MS,
        );
        let bestIoU = POSITION_IOU_MIN,
          bestEntry = null;
        for (const e of recent) {
          const iou = _bboxIoU(d.bbox, e.bbox);
          if (iou > bestIoU) {
            bestIoU = iou;
            bestEntry = e;
          }
        }
        if (bestEntry) return _applyIdentity(d, bestEntry, "position_cache_hit", cameraId);
      }

      console.debug("[cts_live] identity_cache", {
        action: "cache_miss",
        camera_id: cameraId,
        ph_id: d.ph_id || "",
        detection_id: d.detection_id || "",
      });
      return d;
    });
  }

  function smoothKeypoints(detections) {
    if (!detections) return detections;
    const now = Date.now();
    for (const d of detections) {
      const tid = d.detection_id;
      if (!tid || !d.pose_keypoints || d.pose_keypoints.length !== 17) continue;
      const prev = keypointSmoothState[tid];
      if (!prev || now - prev._ts > 2000) {
        // First sighting or >2s gap: initialise with current values.
        keypointSmoothState[tid] = {
          _ts: now,
          kps: d.pose_keypoints.map((kp) => ({ x: kp.x, y: kp.y })),
        };
        continue;
      }
      for (let i = 0; i < 17; i++) {
        const pk = prev.kps[i];
        const ck = d.pose_keypoints[i];
        if (!ck || !pk) continue;
        pk.x = pk.x + KEYPOINT_SMOOTH_ALPHA * (ck.x - pk.x);
        pk.y = pk.y + KEYPOINT_SMOOTH_ALPHA * (ck.y - pk.y);
        // Write smoothed values back to the detection for rendering.
        ck.x = pk.x;
        ck.y = pk.y;
      }
      prev._ts = now;
    }
    return detections;
  }

  // NOTE (pre-existing, preserved verbatim): neither of these two cleanup timers is ever
  // cleared. The original script-setup top-level `setInterval` calls had no teardown either;
  // this is a latent leak, not something an behavior-preserving refactor should fix. Filed
  // as a follow-up rather than patched here.
  setInterval(() => {
    const gtCutoff = Date.now() - PH_IDENTITY_TTL_MS;
    const tCutoff = Date.now() - DETECTION_IDENTITY_TTL_MS;
    for (const [k, v] of Object.entries(phIdentityCache)) {
      if (v.lastSeenMs < gtCutoff) delete phIdentityCache[k];
    }
    for (const [k, v] of Object.entries(detectionIdentityCache)) {
      if (v.lastSeenMs < tCutoff) delete detectionIdentityCache[k];
    }
    // Position cache entries are rebuilt fresh each frame — just clear stale cameras.
    for (const [k, v] of Object.entries(positionIdentityCache)) {
      if (
        !v.length ||
        Date.now() - Math.max(...v.map((e) => e.lastSeenMs)) > POSITION_IDENTITY_TTL_MS * 2
      )
        delete positionIdentityCache[k];
    }
  }, DETECTION_IDENTITY_TTL_MS);

  setInterval(() => {
    const cutoff = Date.now() - 30_000;
    for (const [tid, state] of Object.entries(keypointSmoothState)) {
      if (state._ts < cutoff) delete keypointSmoothState[tid];
    }
  }, 30_000);

  return { mergeIdentityCache, smoothKeypoints };
}
