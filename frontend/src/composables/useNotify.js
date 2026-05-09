import { ref } from "vue";

/**
 * Composable for Vuetify snackbar notifications.
 *
 * Usage:
 *   const { snack, snackText, snackColor, notify } = useNotify();
 *   notify("Saved successfully");
 *   notify("Something went wrong", "error");
 *
 * Template:
 *   <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackText }}</v-snackbar>
 */
export function useNotify() {
  const snack = ref(false);
  const snackText = ref("");
  const snackColor = ref("success");

  function notify(text, color = "success") {
    snackText.value = text;
    snackColor.value = color;
    snack.value = true;
  }

  notify.success = (text) => notify(text, "success");
  notify.error = (text) => notify(text, "error");
  notify.warning = (text) => notify(text, "warning");
  notify.info = (text) => notify(text, "info");

  return { snack, snackText, snackColor, notify };
}
