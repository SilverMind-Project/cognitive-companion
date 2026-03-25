import { ref } from "vue";

/**
 * Composable for a promise-based Vuetify confirmation dialog.
 *
 * Usage:
 *   const { confirmDialog, confirmTitle, confirmText, showConfirm } = useConfirm();
 *   if (await showConfirm("Delete Item", "Are you sure?")) { ... }
 *
 * Template:
 *   <v-dialog v-model="confirmDialog" max-width="400">
 *     <v-card rounded="xl">
 *       <v-card-title>{{ confirmTitle }}</v-card-title>
 *       <v-card-text>{{ confirmText }}</v-card-text>
 *       <v-card-actions>
 *         <v-spacer />
 *         <v-btn variant="text" @click="onCancel">Cancel</v-btn>
 *         <v-btn color="error" @click="onConfirm">Confirm</v-btn>
 *       </v-card-actions>
 *     </v-card>
 *   </v-dialog>
 */
export function useConfirm() {
  const confirmDialog = ref(false);
  const confirmTitle = ref("");
  const confirmText = ref("");

  let _resolve = null;

  function showConfirm(title, text) {
    confirmTitle.value = title;
    confirmText.value = text;
    confirmDialog.value = true;
    return new Promise((resolve) => {
      _resolve = resolve;
    });
  }

  function onConfirm() {
    confirmDialog.value = false;
    if (_resolve) _resolve(true);
    _resolve = null;
  }

  function onCancel() {
    confirmDialog.value = false;
    if (_resolve) _resolve(false);
    _resolve = null;
  }

  return { confirmDialog, confirmTitle, confirmText, showConfirm, onConfirm, onCancel };
}
