import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API_KEY_STORAGE_KEY, setApiKeyProvider } from "@/services/http";
import { getRules } from "@/services/modules/rules";
import { useAuthStore } from "@/stores/auth";

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("seeds from localStorage", () => {
    localStorage.setItem(API_KEY_STORAGE_KEY, "persisted-key");
    setActivePinia(createPinia());

    expect(useAuthStore().apiKey).toBe("persisted-key");
    expect(useAuthStore().isConfigured).toBe(true);
  });

  it("is unconfigured with no stored key", () => {
    expect(useAuthStore().apiKey).toBe("");
    expect(useAuthStore().isConfigured).toBe(false);
  });

  it("persists on set and round-trips into a fresh store", () => {
    useAuthStore().setApiKey("new-key");
    expect(localStorage.getItem(API_KEY_STORAGE_KEY)).toBe("new-key");

    setActivePinia(createPinia());
    expect(useAuthStore().apiKey).toBe("new-key");
  });

  it("clearApiKey empties state and storage", () => {
    const auth = useAuthStore();
    auth.setApiKey("doomed");
    auth.clearApiKey();

    expect(auth.apiKey).toBe("");
    expect(auth.isConfigured).toBe(false);
    expect(localStorage.getItem(API_KEY_STORAGE_KEY)).toBeNull();
  });

  it("feeds the http provider seam: a key set on the store reaches the request header", async () => {
    // The seam main.js wires at startup. Proves the store -- not a localStorage read inside the
    // client -- is what authenticates requests, and that a later setApiKey takes effect without
    // a reload.
    const auth = useAuthStore();
    setApiKeyProvider(() => auth.apiKey);

    const fetchMock = vi.fn(
      async (_request: Request) =>
        new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    auth.setApiKey("live-key");
    await getRules();

    expect(fetchMock.mock.calls[0][0].headers.get("X-API-Key")).toBe("live-key");

    // A rotated key is picked up on the next request, no reload.
    auth.setApiKey("rotated-key");
    await getRules();
    expect(fetchMock.mock.calls[1][0].headers.get("X-API-Key")).toBe("rotated-key");
  });
});
