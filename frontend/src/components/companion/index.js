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
import InteractivePromptDialog from "./InteractivePromptDialog.vue";
import InfoCardDialog from "./InfoCardDialog.vue";
import QuizDialog from "./QuizDialog.vue";
import KnowledgeAnswerWidget from "./KnowledgeAnswerWidget.vue";

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

registerWidget({
  id: "interactive-prompt",
  name: "Interactive Prompt",
  icon: "mdi-message-question",
  component: InteractivePromptDialog,
  position: "overlay",
  priority: 2,
});

registerWidget({
  id: "info-card",
  name: "Info Card",
  icon: "mdi-card-text-outline",
  component: InfoCardDialog,
  position: "overlay",
  priority: 3,
});

registerWidget({
  id: "quiz",
  name: "Quiz",
  icon: "mdi-help-box-outline",
  component: QuizDialog,
  position: "overlay",
  priority: 4,
});

registerWidget({
  id: "knowledge-answer",
  name: "Knowledge Answer",
  icon: "mdi-brain",
  component: KnowledgeAnswerWidget,
  position: "overlay",
  priority: 5,
});
