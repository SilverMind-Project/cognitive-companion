/**
 * Per-identity stable colour utilities for CTS trail and floor-plan rendering.
 *
 * Maps an identity_id string to a deterministic colour so each resident
 * always appears with the same colour across views.
 */

// Distinctive palette optimised for contrast on dark backgrounds.
const PALETTE = [
  "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
  "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F",
  "#BB8FCE", "#85C1E9", "#F8C471", "#82E0AA",
  "#F1948A", "#85C1E9", "#AED6F1", "#D7BDE2",
];

/**
 * Return a stable colour for *identityId*.
 *
 * Uses djb2 hash so the same string always maps to the same palette entry.
 * Returns ``"#888888"`` for empty / unknown inputs.
 */
export function identityColor(identityId) {
  if (!identityId) return "#888888";
  let hash = 5381;
  for (let i = 0; i < identityId.length; i++) {
    hash = ((hash << 5) + hash) + identityId.charCodeAt(i); // hash * 33 + c
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

/**
 * Return a lighter version of the identity colour for fading trail opacity.
 */
export function identityColorWithAlpha(identityId, alpha = 0.3) {
  const hex = identityColor(identityId);
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
