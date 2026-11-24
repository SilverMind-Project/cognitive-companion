/**
 * Where the BFF lives, relative to the page.
 *
 * The household serves the app and the API on separate HTTPS names (the app on
 * `nanai.khoofia.com`, the API on `api.nanai.khoofia.com`); `VITE_API_ORIGIN`, set at
 * build time, names the API's origin. Empty means the API shares the page's origin
 * (the dev server's proxy, tests, and the plain-HTTP `cc-frontend` port, whose nginx
 * forwards `/api` and `/ws`). Every request and socket URL is built here, so the
 * two layouts cannot drift.
 */

const configured: string = import.meta.env.VITE_API_ORIGIN ?? "";

/** The API origin without a trailing slash, or "" for the page's own origin. */
export const API_ORIGIN = configured.trim().replace(/\/+$/, "");

/** An absolute API path (`/api/v1/...`) on the API origin. */
export function apiUrl(path: string): string {
  return `${API_ORIGIN}${path}`;
}

/** A WebSocket URL (`/ws/...`) on the API origin, `wss:` whenever that origin is HTTPS. */
export function wsUrl(path: string, location: Location = window.location): string {
  const base = API_ORIGIN || location.origin;
  return `${base.replace(/^http/, "ws")}${path}`;
}
