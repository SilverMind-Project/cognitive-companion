<template>
  <v-dialog :model-value="screen !== 'hidden'" max-width="560" persistent no-click-animation>
    <v-fade-transition mode="out-in" :duration="200">
      <!-- ============================================================ -->
      <!-- INTRO SCREEN (brief: advances on its own)                    -->
      <!-- ============================================================ -->
      <v-card v-if="screen === 'intro'" key="intro" class="quiz-card">
        <v-card-item>
          <template #prepend>
            <v-icon color="primary" size="32">mdi-help-box-outline</v-icon>
          </template>
          <v-card-title class="quiz-title">{{ title }}</v-card-title>
        </v-card-item>

        <v-divider class="mx-4" />

        <v-card-text class="pt-4">
          <p class="intro-text mb-3">{{ introText }}</p>
          <p class="text-medium-emphasis intro-count">
            {{ totalQuestions }}
            {{ totalQuestions === 1 ? "question" : "questions" }}
          </p>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            color="primary"
            variant="flat"
            size="x-large"
            class="px-8 start-btn"
            data-test="quiz-start"
            @click="startQuiz"
          >
            Let's begin
          </v-btn>
        </v-card-actions>
      </v-card>

      <!-- ============================================================ -->
      <!-- QUESTION SCREEN                                              -->
      <!-- ============================================================ -->
      <v-card v-else-if="screen === 'question'" key="question" class="quiz-card">
        <v-card-item class="pb-0">
          <template #prepend>
            <div class="mr-2">
              <v-chip color="primary" size="large" variant="tonal">
                {{ currentOrd + 1 }}&thinsp;/&thinsp;{{ totalQuestions }}
              </v-chip>
            </div>
          </template>
          <v-card-title class="quiz-title question-title text-wrap" data-test="question-text">
            {{ questionText }}
          </v-card-title>
        </v-card-item>

        <v-divider class="mx-4 my-2" />

        <v-card-text class="pt-2">
          <v-img
            v-if="questionImage"
            :src="questionImage.url"
            :width="questionImage.width || undefined"
            :height="questionImage.height || 200"
            :alt="questionImage.alt_text || ''"
            cover
            class="rounded-lg mb-4 question-image"
          />

          <!-- A clue offered before answering: errorless learning prevents the
               wrong guess rather than correcting it afterwards. -->
          <div v-if="isGentle && hint && answered === null && !answerRecorded" class="mb-3">
            <v-btn
              v-if="!hintShown"
              variant="text"
              color="primary"
              size="large"
              prepend-icon="mdi-lightbulb-on-outline"
              class="hint-btn"
              data-test="quiz-hint"
              @click="hintShown = true"
            >
              Give me a hint
            </v-btn>
            <div v-else class="feedback-bar feedback-bar--reminder" data-test="quiz-hint-text">
              <v-icon size="22" class="mr-2">mdi-lightbulb-on-outline</v-icon>
              <span>{{ hint }}</span>
            </div>
          </div>

          <div v-if="questionType === 'multiple_choice'" class="choices-stack">
            <v-btn
              v-for="choice in choices"
              :key="choice.id"
              block
              size="x-large"
              variant="tonal"
              class="choice-btn mb-3"
              :class="{ 'choice-btn--selected': answered === choice.id }"
              :color="getChoiceColor(choice.id)"
              :disabled="answered !== null || answerRecorded"
              :data-test="`quiz-choice-${choice.id}`"
              @click="selectChoice(choice.id)"
            >
              {{ choice.text }}
            </v-btn>
          </div>

          <div v-else class="open-ended-hint">
            <div class="mic-icon-wrap">
              <v-icon size="48" color="primary">mdi-microphone</v-icon>
            </div>
            <p class="text-center text-medium-emphasis mt-3 open-ended-text">
              Tell me your answer out loud
            </p>
          </div>
        </v-card-text>

        <v-slide-y-transition>
          <v-card-text v-if="answerRecorded" class="pt-0">
            <div class="feedback-bar" :class="feedbackClass" data-test="quiz-feedback">
              <v-icon size="22" class="mr-2">{{ feedbackIcon }}</v-icon>
              <span>
                {{ feedbackText }}
                <span v-if="showExplanation" class="feedback-explanation">
                  {{ explanation }}
                </span>
              </span>
            </div>
          </v-card-text>
        </v-slide-y-transition>
      </v-card>

      <!-- ============================================================ -->
      <!-- COMPLETE SCREEN                                              -->
      <!-- ============================================================ -->
      <v-card v-else-if="screen === 'complete'" key="complete" class="quiz-card">
        <v-card-item>
          <template #prepend>
            <v-icon color="primary" size="32">{{
              isGentle ? "mdi-heart-outline" : "mdi-trophy-outline"
            }}</v-icon>
          </template>
          <v-card-title class="quiz-title">
            {{ isGentle ? "Thank you for chatting with me!" : "Quiz complete!" }}
          </v-card-title>
        </v-card-item>

        <v-divider class="mx-4" />

        <v-card-text class="pt-6 pb-4 text-center">
          <p v-if="isGentle" class="intro-text" data-test="quiz-complete-gentle">
            That was lovely. I enjoyed remembering together.
          </p>
          <template v-else>
            <p class="text-h3 font-weight-bold text-primary score-text" data-test="quiz-score">
              {{ numCorrect }} / {{ numAnswered }}
            </p>
            <p class="text-medium-emphasis mt-1 intro-count">questions answered correctly</p>
          </template>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            color="primary"
            variant="flat"
            size="x-large"
            class="px-8 done-btn"
            data-test="quiz-done"
            @click="close"
          >
            Done
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-fade-transition>
  </v-dialog>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { wsClient } from "../../services/WebSocketClient.js";

// How long the answer feedback stays before the next question or the closing
// screen. A gentle reminder needs longer than a "Wonderful!" to be read.
const FEEDBACK_DWELL_MS = 1500;
const REMINDER_DWELL_MS = 5000;
// The intro is a short greeting, not a gate: a senior who does not tap is never
// left on it, and a voice quiz shows question 1 as soon as it is spoken.
const INTRO_DWELL_MS = 3000;

// ---------------------------------------------------------------------------
// Screen: 'hidden' | 'intro' | 'question' | 'complete'
// ---------------------------------------------------------------------------
const screen = ref("hidden");

const sessionId = ref(null);
const title = ref("");
const introText = ref("");
const totalQuestions = ref(0);
// "gentle" (errorless learning: no right/wrong, no score) or "standard".
const interactionMode = ref("gentle");
const voiceQuiz = ref(false);

const questionQueue = ref([]);
const currentOrd = ref(0);
const questionText = ref("");
const questionType = ref("multiple_choice");
const choices = ref([]);
const questionImage = ref(null);
const hint = ref("");
const hintShown = ref(false);
let questionShownAt = 0;

const answered = ref(null); // selected choice id, or null
const answerRecorded = ref(false);
const isCorrect = ref(null); // true | false | null
const explanation = ref("");

const numCorrect = ref(0);
const numAnswered = ref(0);

let advanceTimer = null;
let introTimer = null;
let completeDismissTimer = null;
const COMPLETE_AUTO_DISMISS_MS = 45000;

const isGentle = computed(() => interactionMode.value !== "standard");

// ---------------------------------------------------------------------------
// Incoming message handlers
// ---------------------------------------------------------------------------
function handleQuizStart(data) {
  resetState();
  screen.value = "intro";
  sessionId.value = data.session_id;
  title.value = data.title || "";
  introText.value = data.intro_voice_text || data.intro_text || "";
  totalQuestions.value = data.total_questions || 0;
  interactionMode.value = data.interaction_mode === "standard" ? "standard" : "gentle";
  voiceQuiz.value = Boolean(data.voice);
  introTimer = setTimeout(startQuiz, INTRO_DWELL_MS);
}

function isOurs(data) {
  return data.session_id === sessionId.value;
}

function handleQuizQuestion(data) {
  if (!isOurs(data)) return;
  questionQueue.value.push(data);
  if (screen.value === "intro" && voiceQuiz.value) {
    // The companion is already asking question 1 aloud; show the same question.
    startQuiz();
  } else if (
    screen.value === "question" &&
    advanceTimer === null &&
    (answerRecorded.value || !questionText.value)
  ) {
    loadNextQuestion();
  }
}

function handleQuizAnswerRecorded(data) {
  if (!isOurs(data)) return;
  answerRecorded.value = true;
  isCorrect.value = data.is_correct;
  explanation.value = data.explanation || "";
  numAnswered.value++;
  if (data.is_correct) numCorrect.value++;

  if (data.advance) {
    clearTimeout(advanceTimer);
    advanceTimer = setTimeout(() => {
      advanceTimer = null;
      loadNextQuestion();
    }, feedbackDwell());
  }
}

function handleQuizComplete(data) {
  if (!isOurs(data)) return;
  clearTimeout(advanceTimer);
  advanceTimer = null;
  numCorrect.value = data.num_correct;
  numAnswered.value = data.num_answered;

  // quiz_complete follows the last quiz_answer_recorded immediately; hold the
  // feedback for the same beat so the last answer's reminder is still seen.
  const showComplete = () => {
    screen.value = "complete";
    clearTimeout(completeDismissTimer);
    // Hands-free TVs and bedside tablets must not stay blocked by a finished quiz.
    completeDismissTimer = setTimeout(close, COMPLETE_AUTO_DISMISS_MS);
  };
  if (answerRecorded.value) {
    advanceTimer = setTimeout(() => {
      advanceTimer = null;
      showComplete();
    }, feedbackDwell());
  } else {
    showComplete();
  }
}

function handleQuizTimeout(data) {
  if (!isOurs(data)) return;
  close();
}

// ---------------------------------------------------------------------------
// State helpers
// ---------------------------------------------------------------------------
function feedbackDwell() {
  return showExplanation.value ? REMINDER_DWELL_MS : FEEDBACK_DWELL_MS;
}

function clearTimers() {
  clearTimeout(advanceTimer);
  clearTimeout(introTimer);
  clearTimeout(completeDismissTimer);
  advanceTimer = null;
  introTimer = null;
  completeDismissTimer = null;
}

function resetState() {
  clearTimers();
  screen.value = "hidden";
  sessionId.value = null;
  title.value = "";
  introText.value = "";
  totalQuestions.value = 0;
  interactionMode.value = "gentle";
  voiceQuiz.value = false;
  questionQueue.value = [];
  currentOrd.value = 0;
  questionText.value = "";
  questionType.value = "multiple_choice";
  choices.value = [];
  questionImage.value = null;
  hint.value = "";
  hintShown.value = false;
  answered.value = null;
  answerRecorded.value = false;
  isCorrect.value = null;
  explanation.value = "";
  numCorrect.value = 0;
  numAnswered.value = 0;
}

function loadNextQuestion() {
  if (questionQueue.value.length === 0) return;
  const q = questionQueue.value.shift();
  answered.value = null;
  answerRecorded.value = false;
  isCorrect.value = null;
  explanation.value = "";
  hintShown.value = false;
  currentOrd.value = q.question_ord;
  questionText.value = q.question_text || "";
  questionType.value = q.question_type || "multiple_choice";
  choices.value = q.choices || [];
  questionImage.value = q.image || null;
  hint.value = q.hint || "";
  questionShownAt = performance.now();
}

// ---------------------------------------------------------------------------
// User actions
// ---------------------------------------------------------------------------
function startQuiz() {
  if (screen.value !== "intro") return;
  clearTimeout(introTimer);
  introTimer = null;
  screen.value = "question";
  loadNextQuestion();
}

function selectChoice(choiceId) {
  if (answered.value !== null) return;
  answered.value = choiceId;
  wsClient._sendJson({
    type: "quiz_answer",
    session_id: sessionId.value,
    question_ord: currentOrd.value,
    choice_id: choiceId,
    latency_ms: Math.round(performance.now() - questionShownAt),
  });
}

function close() {
  clearTimers();
  screen.value = "hidden";
}

// ---------------------------------------------------------------------------
// Feedback presentation: gentle mode never shows right/wrong or a score.
// ---------------------------------------------------------------------------
const showExplanation = computed(
  () => answerRecorded.value && isCorrect.value !== true && explanation.value !== "",
);

function getChoiceColor(choiceId) {
  if (answered.value !== choiceId) return undefined;
  if (!answerRecorded.value || isGentle.value) return "primary";
  return isCorrect.value === true ? "success" : "error";
}

const feedbackClass = computed(() => {
  if (!answerRecorded.value) return "";
  if (isCorrect.value === true) return "feedback-bar--correct";
  if (isCorrect.value === false && !isGentle.value) return "feedback-bar--incorrect";
  return "feedback-bar--reminder";
});

const feedbackIcon = computed(() => {
  if (isCorrect.value === true) return "mdi-check-circle-outline";
  if (isCorrect.value === false && !isGentle.value) return "mdi-information-outline";
  return "mdi-heart-outline";
});

const feedbackText = computed(() => {
  if (!answerRecorded.value) return "";
  if (isCorrect.value === true) return isGentle.value ? "Wonderful!" : "Correct!";
  if (isGentle.value) {
    return showExplanation.value ? "Good thought! Here is a little reminder:" : "Thank you!";
  }
  return isCorrect.value === false ? "Not quite." : "Answer recorded.";
});

// ---------------------------------------------------------------------------
// WS listener: quiz messages arrive through onStatus (no dedicated callbacks).
// ---------------------------------------------------------------------------
function onWsStatus(data) {
  switch (data.type) {
    case "quiz_start":
      handleQuizStart(data);
      break;
    case "quiz_question":
      handleQuizQuestion(data);
      break;
    case "quiz_answer_recorded":
      handleQuizAnswerRecorded(data);
      break;
    case "quiz_complete":
      handleQuizComplete(data);
      break;
    case "quiz_timeout":
      handleQuizTimeout(data);
      break;
  }
}

onMounted(() => {
  wsClient.on("onStatus", onWsStatus);
});

onUnmounted(() => {
  wsClient.off("onStatus", onWsStatus);
  clearTimers();
});

// Allow CompanionView (or tests) to trigger quiz_start programmatically.
defineExpose({ show: handleQuizStart });
</script>

<style scoped>
/* The global dialog rule (theme.css) already gives this v-card warm paper +
   --cc-radius-xl; v-card-title is serif display globally. Senior-surface work
   here is legibility: >=22px body and choices, >=28px titles, >=64px targets. */

.quiz-title {
  font-size: 1.75rem;
  line-height: 1.3;
  font-weight: 600;
}

.intro-text {
  font-size: 1.375rem;
  line-height: 1.6;
  white-space: pre-wrap;
  color: var(--cc-text-1);
}

.intro-count,
.open-ended-text {
  font-size: 1.375rem;
}

.start-btn,
.done-btn,
.hint-btn {
  min-height: 64px;
  font-size: 1.25rem;
  letter-spacing: 0.02em;
  font-weight: 600;
  text-transform: none;
  border-radius: var(--cc-radius-md);
}

.question-title {
  overflow-wrap: break-word;
}

.question-image {
  border: 1px solid var(--cc-divider);
}

.choices-stack {
  display: flex;
  flex-direction: column;
}

.choice-btn {
  min-height: 72px;
  height: auto !important;
  border-radius: var(--cc-radius-md) !important;
  font-size: 1.375rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  text-transform: none;
  white-space: normal;
  transition:
    transform 0.12s ease,
    box-shadow 0.2s ease;
}

/* Long choices wrap to multiple lines rather than truncating. */
.choice-btn :deep(.v-btn__content) {
  white-space: normal;
  line-height: 1.3;
}

.choice-btn:not(:disabled):hover {
  transform: scale(1.01);
}

.choice-btn:not(:disabled):active {
  transform: scale(0.98);
}

.choice-btn--selected {
  box-shadow: 0 0 0 2px currentcolor;
}

@media (prefers-reduced-motion: reduce) {
  .choice-btn {
    transition: none;
  }

  .choice-btn:not(:disabled):hover,
  .choice-btn:not(:disabled):active {
    transform: none;
  }
}

.open-ended-hint {
  padding: 32px 0 24px;
}

.mic-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  margin: 0 auto;
  border-radius: 50%;
  background: var(--cc-brand-softer);
  animation: mic-pulse 2s ease-in-out infinite;
}

@keyframes mic-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 var(--cc-brand-soft);
  }

  50% {
    box-shadow: 0 0 0 12px transparent;
  }
}

@media (prefers-reduced-motion: reduce) {
  .mic-icon-wrap {
    animation: none;
  }
}

.feedback-bar {
  display: flex;
  align-items: flex-start;
  padding: 14px 18px;
  border-radius: var(--cc-radius-md);
  font-size: 1.375rem;
  line-height: 1.45;
  font-weight: 600;
}

.feedback-explanation {
  display: block;
  margin-top: 4px;
  font-weight: 400;
  color: var(--cc-text-1);
}

.feedback-bar--correct {
  background: color-mix(in srgb, var(--cc-success) 12%, transparent);
  color: var(--cc-success);
}

/* A calm, warm reminder: never the error color. */
.feedback-bar--reminder {
  background: color-mix(in srgb, var(--cc-info) 12%, transparent);
  color: var(--cc-info);
}

.feedback-bar--incorrect {
  background: color-mix(in srgb, var(--cc-warning) 14%, transparent);
  color: var(--cc-text-1);
}

.score-text {
  letter-spacing: -0.02em;
}
</style>
