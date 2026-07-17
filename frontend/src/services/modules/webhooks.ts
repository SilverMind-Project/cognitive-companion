/** Webhook trigger (per-rule HMAC auth) and secret rotation. */

import { ApiError, client, unwrap } from "@/services/http";

/**
 * Trigger a rule via its webhook.
 *
 * Deliberately not on the typed client: this endpoint authenticates with a per-rule
 * `X-Webhook-Secret` rather than the app's API key, so it must not go through the auth
 * middleware. It is the one place a raw fetch is correct.
 */
export async function triggerWebhook(
  ruleId: number,
  payload: unknown,
  secret: string,
): Promise<unknown> {
  const response = await fetch(`/api/v1/webhooks/${ruleId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Webhook-Secret": secret },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, (body as { detail?: unknown })?.detail);
  }
  return response.json();
}

export const generateWebhookSecret = (ruleId: number) =>
  unwrap(
    client.POST("/api/v1/webhooks/{rule_id}/generate-secret", {
      params: { path: { rule_id: ruleId } },
    }),
  );
