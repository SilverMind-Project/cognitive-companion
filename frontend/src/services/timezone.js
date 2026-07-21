/**
 * Centralised timezone utilities for Cognitive Companion.
 *
 * The application timezone is configured in config/settings.yaml under
 * `app.timezone` and is fetched from the backend at startup via
 * GET /api/v1/admin/app-info.  All display-layer formatting goes through
 * this module so the timezone is consistent everywhere regardless of the
 * browser's own locale or timezone settings.
 *
 * DST handling is fully automatic: Intl.DateTimeFormat resolves DST
 * transitions using the IANA database bundled with the JavaScript engine.
 *
 * ## Why localStorage and _parseISO?
 *
 * Two independent problems required two fixes:
 *
 * 1. **Naive UTC strings from SQLite.**  SQLite has no native datetime type;
 *    SQLAlchemy stores datetimes as plain text (e.g. "2025-01-15T14:30:00")
 *    with no timezone suffix.  ECMAScript 2015+ treats such strings as *local*
 *    browser time, not UTC, producing the wrong instant when the browser
 *    timezone differs from UTC.  `_parseISO` appends "Z" to any string that
 *    lacks a timezone designator, forcing correct UTC interpretation everywhere.
 *
 * 2. **Vite HMR resetting module state.**  Vite's Hot Module Replacement
 *    re-evaluates individual ES modules when they change.  A plain module-level
 *    `let _appTimezone = "UTC"` would revert to "UTC" on every HMR cycle
 *    without re-running bootstrap(). Storing the value in localStorage and
 *    reading it on every formatter call removes all in-memory state: there is
 *    nothing to reset.
 */

const _STORAGE_KEY = "cc_timezone";

/**
 * Standard column width for datetime columns in data tables.
 * Wide enough to prevent line-wrapping for the full formatDateTime output
 * ("01/15/2025, 02:30:45 PM").
 */
export const DATETIME_COLUMN_WIDTH = 195;

// ---------------------------------------------------------------------------
// Init / accessor
// ---------------------------------------------------------------------------

/**
 * Persist the application timezone.  Call once at app startup with the value
 * received from GET /api/v1/admin/app-info.
 *
 * @param {string} tz  IANA timezone string, e.g. "America/New_York".
 */
export function initTimezone(tz) {
  if (typeof tz === "string" && tz) {
    localStorage.setItem(_STORAGE_KEY, tz);
  }
}

/**
 * Return the active application timezone string.
 *
 * Reads directly from localStorage so it is always authoritative, even after
 * Vite HMR re-evaluates this module.
 *
 * @returns {string}  IANA timezone identifier.
 */
export function getAppTimezone() {
  return localStorage.getItem(_STORAGE_KEY) ?? "UTC";
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Parse an ISO-8601 datetime string, always treating naive strings as UTC.
 *
 * When the string already carries a timezone designator (trailing "Z",
 * "+HH:MM", or "-HH:MM") the browser's built-in parser handles it correctly.
 * Naive strings: as produced by SQLite via SQLAlchemy: get an explicit "Z"
 * appended so `new Date` interprets them as UTC rather than local time.
 *
 * @param {string} iso
 * @returns {Date}
 */
function _parseISO(iso) {
  return /[Zz]|[+-]\d{2}:?\d{2}$/.test(iso) ? new Date(iso) : new Date(iso + "Z");
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

/**
 * Full datetime: "01/15/2025, 02:30:45 PM"
 * Use for audit tables (events, workflows, activities, alerts, executions).
 *
 * @param {string|null|undefined} iso  ISO-8601 string from the API.
 * @returns {string}
 */
export function formatDateTime(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: getAppTimezone(),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  }).format(_parseISO(iso));
}

/**
 * Compact datetime: "Jan 15, 2:30 PM"
 * Use for dashboard cards and inline timeline entries.
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function formatDateTimeShort(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: getAppTimezone(),
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).format(_parseISO(iso));
}

/**
 * Date only: "01/15/2025"
 * Use for person created-at, date-oriented columns.
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function formatDateOnly(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: getAppTimezone(),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(_parseISO(iso));
}

/**
 * Time only: "02:30 PM"
 * Use for transcript timestamps and other time-only displays.
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function formatTimeOnly(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: getAppTimezone(),
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).format(_parseISO(iso));
}

/**
 * Full datetime with explicit timezone abbreviation: "Jan 15, 2025, 2:30:45 PM EST"
 * Use for camera media lightbox where the absolute moment matters most.
 *
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function formatDateTimeFull(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: getAppTimezone(),
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZoneName: "short",
  }).format(_parseISO(iso));
}

// ---------------------------------------------------------------------------
// Step-config helpers (verification step fixed-window time inputs)
// ---------------------------------------------------------------------------

/**
 * Extract an "HH:MM" (24-hour) string from a UTC ISO datetime, displayed in
 * the app timezone.  Used by StepConfigDialog to populate time inputs when
 * loading a saved verification condition.
 *
 * @param {string|null|undefined} iso  UTC ISO-8601 string from the backend.
 * @returns {string}  "HH:MM" in the app timezone, or "" on error.
 */
export function isoToLocalHHMM(iso) {
  if (!iso) return "";
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: getAppTimezone(),
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(_parseISO(iso));
    const h = parts.find((p) => p.type === "hour")?.value ?? "00";
    const m = parts.find((p) => p.type === "minute")?.value ?? "00";
    // Intl may return "24" for midnight in hour12:false mode on some engines
    return `${h === "24" ? "00" : h}:${m}`;
  } catch {
    return "";
  }
}

/**
 * Convert an "HH:MM" local time (in the app timezone) for today's date into a
 * UTC ISO-8601 string.  Used by StepConfigDialog when saving a verification
 * condition's fixed time window.
 *
 * DST is handled correctly: we first find today's date in the app timezone,
 * construct an approximate UTC instant, then correct for the timezone offset
 * at that instant.  A single correction step is sufficient because DST offsets
 * only shift by a whole number of minutes (typically 60).
 *
 * @param {string|null|undefined} timeStr  "HH:MM" in the app timezone.
 * @returns {string|null}  UTC ISO string, or null for empty input.
 */
export function localHHMMToUTCISO(timeStr) {
  if (!timeStr) return null;
  const [hStr, mStr] = timeStr.split(":");
  const h = parseInt(hStr, 10);
  const m = parseInt(mStr, 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;

  // Use today's date in the app timezone as the calendar anchor.
  const localDateStr = new Date().toLocaleDateString("en-CA", {
    timeZone: getAppTimezone(),
  });
  return _localWallToUTCISO(localDateStr, h, m);
}

/**
 * Convert a calendar date plus an optional "HH:MM" wall-clock time, interpreted
 * in the app timezone, into a UTC ISO-8601 string.  Used for date-range pickers
 * where the user selects local calendar boundaries that must be sent to the
 * backend as absolute UTC instants.
 *
 * @param {string|null|undefined} dateStr  "YYYY-MM-DD" in the app timezone.
 * @param {string} [timeStr="00:00"]       "HH:MM" wall-clock time (app tz).
 * @returns {string|null}  UTC ISO string, or null for empty input.
 */
export function localDateToUTCISO(dateStr, timeStr = "00:00") {
  if (!dateStr) return null;
  const [hStr, mStr] = timeStr.split(":");
  const h = parseInt(hStr, 10);
  const m = parseInt(mStr, 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return _localWallToUTCISO(dateStr, h, m);
}

/**
 * Core conversion: given a "YYYY-MM-DD" date and an hour/minute interpreted as
 * wall-clock time in the app timezone, return the matching UTC ISO string.
 *
 * DST is handled by a single offset-correction step: we treat the wall-clock
 * value as if it were UTC to get an approximate instant, observe what time that
 * instant actually shows in the app timezone, then shift by the difference.
 *
 * @param {string} dateStr  "YYYY-MM-DD".
 * @param {number} h        Hour (0-23).
 * @param {number} m        Minute (0-59).
 * @returns {string}        UTC ISO string.
 */
function _localWallToUTCISO(dateStr, h, m) {
  const tz = getAppTimezone();
  const approxUTC = new Date(
    `${dateStr}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00Z`,
  );
  const displayParts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(approxUTC);
  const dh = parseInt(displayParts.find((p) => p.type === "hour")?.value ?? "0", 10);
  const dm = parseInt(displayParts.find((p) => p.type === "minute")?.value ?? "0", 10);
  const offsetMs = ((h - (dh === 24 ? 0 : dh)) * 60 + (m - dm)) * 60_000;
  return new Date(approxUTC.getTime() + offsetMs).toISOString();
}
