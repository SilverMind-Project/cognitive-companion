/**
 * CTS pixelation — single source of truth.
 *
 * The blur *flag* lives in the `ui` Pinia store: it is one app-wide privacy setting that
 * eight views and the BlurToggle all share. The pixelation *engine* below stays here — those are
 * pure functions over a module-level image cache, called from non-component code, and a store
 * would add indirection without sharing anything.
 *
 * True square-block pixelation via off-screen canvas downsampling.
 * Each N×N pixel block is averaged to a single colour, then the image is
 * scaled back to original dimensions with nearest-neighbour interpolation.
 * Only the image content is pixelated — DOM overlays (bounding boxes,
 * labels, pose evidence) render natively on top and remain crisp.
 *
 * Block size is controlled via CSS custom property --cts-block-size (default 16).
 */

import { watch, reactive } from "vue";
import { storeToRefs } from "pinia";

import { useUiStore } from "@/stores/ui";

// ---------------------------------------------------------------------------
// Canvas-based square-block pixelation
// ---------------------------------------------------------------------------

let currentBlockSize = 128;

// Cache: key → { promise, blobUrl }. blobUrl is set once the promise resolves.
const cache = new Map();
const MAX_CACHE = 128;

/**
 * Revoke a cache entry's blob URL (if already resolved) and remove from cache.
 * If the promise hasn't settled yet, chain revocation onto it.
 */
function evictCacheEntry(key) {
  const entry = cache.get(key);
  if (!entry) return;
  cache.delete(key);
  if (entry.blobUrl !== undefined) {
    URL.revokeObjectURL(entry.blobUrl);
  } else {
    entry.promise
      .then((blobUrl) => {
        if (blobUrl) URL.revokeObjectURL(blobUrl);
      })
      .catch(() => {});
  }
}

/**
 * Load an image URL, downsample to square blocks (nearest-neighbour), return a
 * blob URL.  Uses `toBlob` so canvas encoding stays off the main thread.
 *
 * @param {string} url
 * @param {number} blockSize
 * @returns {Promise<string>}  resolved blob URL (caller must revoke)
 */
function pixelateImageUrl(url, blockSize = currentBlockSize) {
  const key = `${url}::${blockSize}`;
  const cached = cache.get(key);
  if (cached) return cached.promise;

  const entry = { promise: null, blobUrl: undefined };
  entry.promise = new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const w = img.naturalWidth;
      const h = img.naturalHeight;
      const bw = Math.max(1, Math.round(w / blockSize));
      const bh = Math.max(1, Math.round(h / blockSize));

      // Step 1 — downsample to block-sized grid
      const small = document.createElement("canvas");
      small.width = bw;
      small.height = bh;
      small.getContext("2d").drawImage(img, 0, 0, bw, bh);

      // Step 2 — scale back to original size with nearest-neighbour
      const out = document.createElement("canvas");
      out.width = w;
      out.height = h;
      const octx = out.getContext("2d");
      octx.imageSmoothingEnabled = false;
      octx.drawImage(small, 0, 0, w, h);

      out.toBlob(
        (blob) => {
          if (blob) {
            const blobUrl = URL.createObjectURL(blob);
            entry.blobUrl = blobUrl;
            resolve(blobUrl);
          } else {
            reject(new Error(`Failed to create blob for: ${url}`));
          }
        },
        "image/jpeg",
        0.85,
      );
    };
    img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
    img.src = url;
  });

  // LRU eviction
  if (cache.size >= MAX_CACHE) {
    const first = cache.keys().next().value;
    evictCacheEntry(first);
  }
  cache.set(key, entry);

  entry.promise.catch(() => {
    cache.delete(key);
  });

  return entry.promise;
}

// ---------------------------------------------------------------------------
// Public composables
// ---------------------------------------------------------------------------

export function useBlurMode() {
  // Writable: BlurToggle v-models it. Persistence lives in the store's watcher.
  const { blurMode } = storeToRefs(useUiStore());
  return { blurMode };
}

/**
 * Returns a reactive display-src helper for templates.
 *
 * Usage:
 *   const { blurMode, displaySrc } = useBlurMode();
 *   // In template: :src="displaySrc(rawUrl)"
 *
 * When blurMode is off the raw URL passes through unchanged.
 * When blurMode is on the function returns null until async pixelation
 * completes, so the <img> renders with no src attribute.  Vue reactivity
 * drives a re-render once the pixelated blob URL is ready.
 * Unblurred image content is never shown.
 */
export function useDisplaySrc(blurModeRef, blockSize = currentBlockSize) {
  // reactive map: source-url → blob-url | null (null = pixelation in flight)
  const pixelated = reactive(new Map());
  const MAX_LOCAL = 256;

  function revokeBlob(blobUrl) {
    if (blobUrl && typeof blobUrl === "string" && blobUrl.startsWith("blob:")) {
      URL.revokeObjectURL(blobUrl);
    }
  }

  function evictOne() {
    if (pixelated.size <= MAX_LOCAL) return;
    const first = pixelated.keys().next().value;
    revokeBlob(pixelated.get(first));
    pixelated.delete(first);
  }

  // Revoke all blob URLs when blur is toggled off.
  watch(blurModeRef, (active) => {
    if (!active) {
      for (const v of pixelated.values()) revokeBlob(v);
      pixelated.clear();
    }
  });

  function displaySrc(rawUrl) {
    if (!blurModeRef.value || !rawUrl) return rawUrl;
    const cached = pixelated.get(rawUrl);
    if (cached !== undefined) return cached; // null (in-flight) or blob URL (done)
    // Mark in-flight, start async pixelation — no raw URL ever stored.
    pixelated.set(rawUrl, null);
    evictOne();
    pixelateImageUrl(rawUrl, blockSize)
      .then((blobUrl) => {
        pixelated.set(rawUrl, blobUrl);
        evictOne();
      })
      .catch(() => {
        pixelated.delete(rawUrl);
      });
    return null;
  }

  return { displaySrc };
}

// Set initial CSS custom property
document.documentElement.style.setProperty("--cts-block-size", String(currentBlockSize));
