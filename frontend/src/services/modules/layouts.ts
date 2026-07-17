/**
 * Knowledge layout registry (operator-authored YAML, not DB rows).
 *
 * `applies_to` was raw-interpolated by the previous client; the typed client encodes it.
 */

import { client, unwrap } from "@/services/http";
import type { components } from "@/generated/api-types";

export type LayoutOut = components["schemas"]["LayoutOut"];

export const getKnowledgeLayouts = (appliesTo?: string) =>
  unwrap(
    client.GET("/api/v1/knowledge/layouts", {
      params: { query: appliesTo ? { applies_to: appliesTo } : {} },
    }),
  );

export const getKnowledgeLayout = (id: string) =>
  unwrap(
    client.GET("/api/v1/knowledge/layouts/{layout_id}", { params: { path: { layout_id: id } } }),
  );
