import { afterEach, describe, expect, it, vi } from "vitest";

const page = { origin: "https://nanai.khoofia.com" } as Location;

async function load(origin: string | undefined) {
  vi.resetModules();
  vi.unstubAllEnvs();
  if (origin !== undefined) vi.stubEnv("VITE_API_ORIGIN", origin);
  return import("@/services/apiOrigin");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("apiOrigin", () => {
  it("sends requests and sockets to the API's own HTTPS name when one is configured", async () => {
    const { API_ORIGIN, apiUrl, wsUrl } = await load("https://api.nanai.khoofia.com/");

    expect(API_ORIGIN).toBe("https://api.nanai.khoofia.com");
    expect(apiUrl("/api/v1/health")).toBe("https://api.nanai.khoofia.com/api/v1/health");
    expect(wsUrl("/ws/audio", page)).toBe("wss://api.nanai.khoofia.com/ws/audio");
  });

  it("stays on the page's origin when none is configured", async () => {
    const { apiUrl, wsUrl } = await load("");

    expect(apiUrl("/api/v1/health")).toBe("/api/v1/health");
    expect(wsUrl("/ws/audio", page)).toBe("wss://nanai.khoofia.com/ws/audio");
    expect(wsUrl("/ws/audio", { origin: "http://192.0.2.10:8081" } as Location)).toBe(
      "ws://192.0.2.10:8081/ws/audio",
    );
  });
});
