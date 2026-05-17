/**
 * Persistent blur-mode toggle for camera-image views.
 *
 * Default ON — the caregiver must explicitly disable blur to show raw frames.
 * State persists across page reloads via localStorage.
 */

import { ref, watch } from "vue";

const STORAGE_KEY = "cts_blur_mode";

function readStorage() {
  const raw = localStorage.getItem(STORAGE_KEY);
  // Default: blur ON (null → true).
  return raw === null ? true : raw === "true";
}

const blurMode = ref(readStorage());

watch(blurMode, (val) => {
  localStorage.setItem(STORAGE_KEY, String(val));
});

export function useBlurMode() {
  return { blurMode };
}
