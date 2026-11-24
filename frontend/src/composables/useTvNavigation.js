/**
 * Remote-control (D-pad) navigation for the companion screen on a TV.
 *
 * A TV remote has arrows and a select key, no touch. On a TV this moves focus
 * between the controls of whatever the resident is looking at (the topmost open
 * dialog, else the companion screen) and selects the focused one, so the
 * guided-task buttons, quiz choices, info-card and interactive-prompt buttons all
 * work from the sofa. Focus moves in on-screen reading order and stops at the ends
 * rather than wrapping, so pressing an arrow repeatedly always lands in the same
 * place. Back/Escape are deliberately not bound: a stray press must never dismiss
 * something she has not read.
 *
 * Not a Pinia store: it owns a document-level key listener and the <html> class,
 * both scoped to the view that mounts it.
 */

import { computed, reactive } from "vue";

export const TV_MODE_CLASS = "cc-tv-mode";

const FOCUSABLE = [
  "button:not([disabled])",
  "a[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

const PREVIOUS_KEYS = new Set(["ArrowUp", "ArrowLeft"]);
const NEXT_KEYS = new Set(["ArrowDown", "ArrowRight"]);

/**
 * @param {object} [deps]
 * @param {{ query?: Record<string, unknown> } | null} [deps.route]
 * @param {() => string} [deps.surfaceKind] The kiosk's configured surface kind.
 * @param {() => boolean} [deps.deviceIsTelevision] The native shell's report.
 * @param {() => Element | null} [deps.root] The companion screen's root element.
 * @param {Document} [deps.documentRef]
 */
export function useTvNavigation({
  route = null,
  surfaceKind = () => "",
  deviceIsTelevision = () => false,
  root = () => null,
  documentRef = globalThis.document,
} = {}) {
  const state = reactive({
    active: computed(
      () => route?.query?.surface_kind === "tv" || surfaceKind() === "tv" || deviceIsTelevision(),
    ),
  });

  function scope() {
    const overlays = documentRef.querySelectorAll(".v-overlay--active .v-overlay__content");
    return overlays.length ? overlays[overlays.length - 1] : root();
  }

  function focusables(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll(FOCUSABLE)).filter(
      (el) => !el.hidden && !el.closest('[aria-hidden="true"], [inert]'),
    );
  }

  function handleKeydown(event) {
    if (!state.active) return;
    const isMove = PREVIOUS_KEYS.has(event.key) || NEXT_KEYS.has(event.key);
    if (!isMove && event.key !== "Enter") return;

    const items = focusables(scope());
    if (!items.length) return;
    const index = items.indexOf(documentRef.activeElement);

    if (event.key === "Enter") {
      if (index < 0) {
        items[0].focus();
      } else {
        // Selected here, and the browser's own Enter activation suppressed, so a
        // press is one click on every element type.
        items[index].click();
      }
      event.preventDefault();
      return;
    }

    let next;
    if (index < 0) next = 0;
    else if (NEXT_KEYS.has(event.key)) next = Math.min(index + 1, items.length - 1);
    else next = Math.max(index - 1, 0);
    items[next].focus();
    event.preventDefault();
  }

  function syncClass() {
    documentRef.documentElement.classList.toggle(TV_MODE_CLASS, state.active);
  }

  function mount() {
    documentRef.addEventListener("keydown", handleKeydown);
    syncClass();
  }

  function unmount() {
    documentRef.removeEventListener("keydown", handleKeydown);
    documentRef.documentElement.classList.remove(TV_MODE_CLASS);
  }

  return { state, actions: { mount, unmount, handleKeydown, syncClass } };
}
