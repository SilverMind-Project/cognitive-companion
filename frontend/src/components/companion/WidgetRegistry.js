/**
 * Widget registry for the CompanionView.
 *
 * Widgets are registered here and rendered by CompanionView based on
 * position and priority.  New widgets can be added by importing them
 * and calling `registerWidget()`.
 *
 * Positions: 'main' (center column), 'sidebar' (right column), 'overlay'
 * Priority: lower number = higher priority (rendered first)
 */

import { markRaw, reactive } from "vue";

/**
 * @typedef {Object} CompanionWidget
 * @property {string} id - Unique widget identifier
 * @property {string} name - Display name
 * @property {string} icon - MDI icon name
 * @property {import('vue').Component} component - Vue component
 * @property {'main'|'sidebar'|'overlay'} position
 * @property {number} priority - Lower = rendered first
 * @property {boolean} [enabled=true]
 */

const state = reactive({
  /** @type {CompanionWidget[]} */
  widgets: [],
});

/**
 * Register a companion widget.
 * @param {CompanionWidget} widget
 */
export function registerWidget(widget) {
  // Prevent duplicates
  if (state.widgets.some((w) => w.id === widget.id)) return;
  state.widgets.push({
    ...widget,
    component: markRaw(widget.component),
    enabled: widget.enabled !== false,
  });
  // Sort by priority
  state.widgets.sort((a, b) => a.priority - b.priority);
}

/**
 * Get all widgets for a given position.
 * @param {'main'|'sidebar'|'overlay'} position
 * @returns {CompanionWidget[]}
 */
export function getWidgets(position) {
  return state.widgets.filter((w) => w.position === position && w.enabled);
}
