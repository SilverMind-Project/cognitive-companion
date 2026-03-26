/**
 * Register built-in companion widgets.
 *
 * Import this module once at app startup to register the default widgets.
 * Third-party or experimental widgets can be registered separately by
 * calling registerWidget() from their own modules.
 */

import { registerWidget } from "./WidgetRegistry.js";
import VoiceWidget from "./VoiceWidget.vue";
import TranscriptWidget from "./TranscriptWidget.vue";
import AlertWidget from "./AlertWidget.vue";

registerWidget({
  id: "voice",
  name: "Voice Interface",
  icon: "mdi-microphone",
  component: VoiceWidget,
  position: "main",
  priority: 1,
});

registerWidget({
  id: "transcript",
  name: "Conversation Transcript",
  icon: "mdi-message-text",
  component: TranscriptWidget,
  position: "sidebar",
  priority: 1,
});

registerWidget({
  id: "alert",
  name: "Emergency Alert",
  icon: "mdi-alert",
  component: AlertWidget,
  position: "overlay",
  priority: 1,
});
