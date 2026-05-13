/**
 * Relative-time formatting for display timestamps.
 *
 * Replaces duplicated ``function formatRelative(iso)`` definitions in
 * CTSPresenceView, PresenceWidget, and CameraMediaView.
 */

export function formatRelative(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.abs(Math.floor(diff / 1000));
  if (secs < 60) return secs < 10 ? "just now" : `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return mins === 1 ? "1 min ago" : `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs === 1 ? "1 hr ago" : `${hrs} hr ago`;
  const days = Math.floor(hrs / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}
