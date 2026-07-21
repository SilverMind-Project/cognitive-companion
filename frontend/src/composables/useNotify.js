/**
 * Notification entry point — a thin delegate to the notifications Pinia store.
 *
 * Usage:
 *   const { notify } = useNotify();
 *   notify("Saved successfully");
 *   notify("Something went wrong", "error");
 *
 * No template wiring is needed: CcSnackbarHost in App.vue renders every message, whichever
 * module raised it. Never add a local <v-snackbar> for app feedback — a per-view snackbar bound
 * to per-view refs was the bug this replaced.
 *
 * The store is resolved per call rather than at useNotify() time, so composables constructed
 * outside a setup context can still notify.
 */

import { useNotificationsStore } from "@/stores/notifications";

function notify(text, color = "success") {
  return useNotificationsStore().notify(text, color);
}

notify.success = (text) => notify(text, "success");
notify.error = (text) => notify(text, "error");
notify.warning = (text) => notify(text, "warning");
notify.info = (text) => notify(text, "info");

export function useNotify() {
  return { notify };
}
