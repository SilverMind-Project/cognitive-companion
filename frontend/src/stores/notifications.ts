/**
 * Notification queue — the app's single source of user feedback (closes the defect).
 *
 * Before this store, useNotify() minted a *fresh* set of refs on every call, so it was a
 * factory wearing a singleton's clothes. A view bound its `<v-snackbar>` to its own instance's
 * refs; a shared composable calling useNotify().notify.error(...) wrote to refs no template
 * rendered, and the message vanished. Errors raised inside composables were silently dropped.
 *
 * One store, one queue, one renderer (`CcSnackbarHost` in `App.vue`): a message is visible no
 * matter which module raised it.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

export type NotificationColor = "success" | "error" | "warning" | "info";

export interface Notification {
  id: number;
  text: string;
  color: NotificationColor;
  timeout: number;
}

/** Matches the timeout every hand-rolled `<v-snackbar>` used before the migration. */
export const DEFAULT_TIMEOUT = 3000;

export const useNotificationsStore = defineStore("notifications", () => {
  const queue = ref<Notification[]>([]);
  let nextId = 0;

  function notify(text: string, color: NotificationColor = "success"): number {
    const id = nextId++;
    queue.value = [...queue.value, { id, text, color, timeout: DEFAULT_TIMEOUT }];
    return id;
  }

  function dismiss(id: number): void {
    queue.value = queue.value.filter((n) => n.id !== id);
  }

  function clear(): void {
    queue.value = [];
  }

  return {
    queue,
    notify,
    dismiss,
    clear,
    success: (text: string) => notify(text, "success"),
    error: (text: string) => notify(text, "error"),
    warning: (text: string) => notify(text, "warning"),
    info: (text: string) => notify(text, "info"),
  };
});
