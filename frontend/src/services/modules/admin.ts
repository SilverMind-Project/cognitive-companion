/** Admin surfaces: config reload, telegram defaults, and public app metadata. */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

export type AppInfoOut = components["schemas"]["AppInfoOut"];
export type DailyLivingHealthOut = components["schemas"]["DailyLivingHealthOut"];

export const reloadConfig = () => unwrap(client.POST("/api/v1/admin/config/reload", {}));

export const getTelegramTriggerDefaults = () =>
  unwrap(client.GET("/api/v1/admin/telegram/trigger-defaults", {}));

/**
 * Public application metadata (name, version, timezone).
 *
 * Unauthenticated by design: read during bootstrap to initialise the display timezone before
 * the user has supplied a key. The auth middleware still attaches a key if one happens to be
 * present, which the endpoint ignores.
 */
export const getAppInfo = () => unwrap(client.GET("/api/v1/admin/app-info", {}));

/** Semantic-memory write recency + activity-ledger population (DL-M01). */
export const getDailyLivingHealth = () =>
  unwrap(client.GET("/api/v1/admin/daily-living-health", {}));
