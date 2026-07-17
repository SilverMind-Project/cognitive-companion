/**
 * API key ownership (M18).
 *
 * The key used to live in raw `localStorage` reads scattered across `api.js` and `AdminView`.
 * This store is now the only reader/writer: `main.js` points `http.ts`'s `setApiKeyProvider`
 * seam here at startup, so the HTTP client and the WebSocket helpers both take the key from one
 * reactive source. `r4_bypass_guard.spec.js` enforces that this file is the only site touching
 * the storage key.
 *
 * localStorage remains the persistence layer (unchanged behavior: the key survives a reload and
 * is not sent anywhere but the `X-API-Key` header).
 */

import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { API_KEY_STORAGE_KEY } from "@/services/http";

export const useAuthStore = defineStore("auth", () => {
  const apiKey = ref<string>(localStorage.getItem(API_KEY_STORAGE_KEY) ?? "");

  const isConfigured = computed(() => apiKey.value.length > 0);

  function setApiKey(key: string): void {
    apiKey.value = key;
    localStorage.setItem(API_KEY_STORAGE_KEY, key);
  }

  function clearApiKey(): void {
    apiKey.value = "";
    localStorage.removeItem(API_KEY_STORAGE_KEY);
  }

  return { apiKey, isConfigured, setApiKey, clearApiKey };
});
