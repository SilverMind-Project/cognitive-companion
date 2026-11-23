// Minimal Vuetify stand-ins for the senior companion overlays: enough structure to
// read text, find buttons by data-test, and see whether a dialog is open.
const passthrough = { template: "<div><slot /></div>" };

export const companionStubs = {
  "v-dialog": {
    props: ["modelValue"],
    template: '<div v-if="modelValue" class="dialog-open"><slot /></div>',
  },
  "v-fade-transition": passthrough,
  "v-slide-y-transition": passthrough,
  "v-card": passthrough,
  "v-card-item": { template: "<div><slot name='prepend' /><slot /></div>" },
  "v-card-title": passthrough,
  "v-card-text": passthrough,
  "v-card-actions": passthrough,
  "v-divider": { template: "<hr />" },
  "v-spacer": { template: "<span />" },
  "v-icon": { template: "<i><slot /></i>" },
  "v-chip": passthrough,
  "v-img": { template: "<img />" },
  "v-progress-linear": {
    props: ["modelValue"],
    template: '<div class="progress" :data-value="modelValue" />',
  },
  "v-btn": {
    props: ["disabled", "color"],
    emits: ["click"],
    template:
      "<button :disabled='disabled' :data-color='color' @click=\"$emit('click')\"><slot /></button>",
  },
};
