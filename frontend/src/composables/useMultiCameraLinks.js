import { computed } from "vue";
import { identityColor } from "@/composables/useIdentityColor.js";

/**
 * Cross-camera person detection derived from the live camera state: which identities are
 * seen on 2+ cameras right now, and the per-tile helpers (color, link badges) that follow
 * from that.
 */
export function useMultiCameraLinks(cameras) {
  // Cross-camera person detection: identity_id → Set of camera_ids where seen.
  const identityCameraMap = computed(() => {
    const map = new Map(); // identity_id → Set<camera_id>
    for (const [cameraId, cam] of Object.entries(cameras.value)) {
      for (const det of cam.detections || []) {
        const id = det.identity_id;
        if (!id) continue;
        if (!map.has(id)) map.set(id, new Set());
        map.get(id).add(cameraId);
      }
    }
    return map;
  });

  // List of identities seen on 2+ cameras, sorted by camera count desc.
  const multiCameraIdentities = computed(() => {
    const result = [];
    for (const [id, cams] of identityCameraMap.value.entries()) {
      if (cams.size >= 2) {
        result.push({ identity_id: id, cameraCount: cams.size, color: identityColor(id) });
      }
    }
    return result.sort((a, b) => b.cameraCount - a.cameraCount);
  });

  function isMultiCamera(det) {
    if (!det.identity_id) return false;
    const cams = identityCameraMap.value.get(det.identity_id);
    return cams ? cams.size >= 2 : false;
  }

  function multiCameraCount(det) {
    if (!det.identity_id) return 0;
    return identityCameraMap.value.get(det.identity_id)?.size ?? 0;
  }

  function multiCameraTooltip(det) {
    if (!det.identity_id) return "";
    const cams = identityCameraMap.value.get(det.identity_id);
    if (!cams) return "";
    return `Seen on: ${[...cams].join(", ")}`;
  }

  function bboxColor(det) {
    if (!det.identity_id) return "var(--cc-warning)";
    return isMultiCamera(det) ? identityColor(det.identity_id) : "var(--cc-success)";
  }

  // Returns the dominant multi-camera identity color for a camera tile, or null.
  // "Dominant" = most cameras, tie-broken by identity_confidence.
  function tileDominantLinkColor(cameraId) {
    if (!cameraId) return null;
    const cam = cameras.value[cameraId];
    if (!cam?.detections?.length) return null;
    let best = null;
    let bestScore = -1;
    for (const det of cam.detections) {
      if (!det.identity_id) continue;
      const cams = identityCameraMap.value.get(det.identity_id);
      if (!cams || cams.size < 2) continue;
      const score = cams.size + (det.identity_confidence || 0);
      if (score > bestScore) {
        bestScore = score;
        best = det.identity_id;
      }
    }
    return best ? identityColor(best) : null;
  }

  // Box-shadow glow style applied to the tile card when it has a linked GT.
  function tileLinkStyle(cameraId) {
    const color = tileDominantLinkColor(cameraId);
    if (!color) return {};
    return {
      boxShadow: `0 0 0 2px ${color}cc, 0 0 14px ${color}55`,
      transition: "box-shadow 0.4s ease",
    };
  }

  // Returns one entry per multi-camera identity visible on this camera tile,
  // used to render the per-tile link badges.
  function tileLinkEntries(cameraId) {
    if (!cameraId) return [];
    const cam = cameras.value[cameraId];
    if (!cam?.detections?.length) return [];
    const seen = new Set();
    const result = [];
    for (const det of cam.detections) {
      if (!det.identity_id || seen.has(det.identity_id)) continue;
      const cams = identityCameraMap.value.get(det.identity_id);
      if (!cams || cams.size < 2) continue;
      seen.add(det.identity_id);
      const others = [...cams].filter((c) => c !== cameraId);
      result.push({
        identity_id: det.identity_id,
        display_name: det.display_name || det.identity_id,
        color: identityColor(det.identity_id),
        otherCameras: others,
      });
    }
    return result;
  }

  return {
    multiCameraIdentities,
    isMultiCamera,
    multiCameraCount,
    multiCameraTooltip,
    bboxColor,
    tileLinkStyle,
    tileLinkEntries,
  };
}
