<template>
  <v-dialog
    :model-value="screen !== 'hidden'"
    max-width="520"
    persistent
    no-click-animation
    @after-leave="onDialogClosed"
  >
    <v-fade-transition mode="out-in" :duration="200">
      <!-- ============================================================ -->
      <!-- INTRO SCREEN                                                 -->
      <!-- ============================================================ -->
      <v-card v-if="screen === 'intro'" key="intro" class="quiz-card">
        <v-card-item>
          <template #prepend>
            <v-icon color="primary" size="28">mdi-help-box-outline</v-icon>
          </template>
          <v-card-title class="text-h6 font-weight-bold">{{ title }}</v-card-title>
        </v-card-item>

        <v-divider class="mx-4" />

        <v-card-text class="pt-4">
          <p class="text-body-1 intro-text mb-3">{{ introText }}</p>
          <p class="text-caption text-medium-emphasis">
            {{ totalQuestions }}
            {{ totalQuestions === 1 ? "question" : "questions" }}
          </p>
        </v-card-text>

        <v-divider class="mx-4" />

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            color="primary"
            variant="flat"
            size="large"
            class="px-8 start-btn"
            @click="startQuiz"
          >
            Start
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
              <v-chip
                color="primary"
                size="small"
                variant="tonal"
              >
                {{ currentOrd + 1 }}&thinsp;/&thinsp;{{ totalQuestions }}
              </v-chip>
            </div>
          </template>
          <v-card-title class="text-h6 font-weight-bold question-title text-wrap" style="line-height: 1.3">
            {{ questionText }}
          </v-card-title>
        </v-card-item>

        <v-divider class="mx-4 my-2" />

        <v-card-text class="pt-2">
          <!-- Question image -->
          <v-img
            v-if="questionImage"
            :src="questionImage.url"
            :width="questionImage.width || undefined"
            :height="questionImage.height || 200"
            :alt="questionImage.alt_text || ''"
            cover
            class="rounded-lg mb-4 question-image"
          />

          <!-- Multiple choice -->
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
              :disabled="answered !== null"
              @click="selectChoice(choice.id)"
            >
              {{ choice.text }}
            </v-btn>
          </div>

          <!-- Open ended -->
          <div v-else class="open-ended-hint">
            <div class="mic-icon-wrap">
              <v-icon size="48" color="primary">mdi-microphone</v-icon>
            </div>
            <p class="text-center text-body-2 text-medium-emphasis mt-3">
              Speak your answer aloud
            </p>
          </div>
        </v-card-text>

        <!-- Feedback bar (visible after answer is recorded) -->
        <v-slide-y-transition>
          <v-card-text v-if="answerRecorded" class="pt-0">
            <div class="feedback-bar" :class="feedbackClass">
              <v-icon size="18" class="mr-1">{{ feedbackIcon }}</v-icon>
              <span>{{ feedbackText }}</span>
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
            <v-icon color="primary" size="28">mdi-trophy-outline</v-icon>
          </template>
          <v-card-title class="text-h6 font-weight-bold">Quiz Complete!</v-card-title>
        </v-card-item>

        <v-divider class="mx-4" />

        <v-card-text class="pt-6 pb-4 text-center">
          <p class="text-h3 font-weight-bold text-primary score-text">{{ numCorrect }} / {{ numAnswered }}</p>
          <p class="text-body-2 text-medium-emphasis mt-1">
            questions answered correctly
          </p>
        </v-card-text>

        <v-divider class="mx-4" />

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            color="primary"
            variant="flat"
            size="large"
            class="px-8 done-btn"
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

// ---------------------------------------------------------------------------
// Screen: 'hidden' | 'intro' | 'question' | 'complete'
// ---------------------------------------------------------------------------
const screen = ref("hidden");

// Quiz-level data
const sessionId = ref(null);
const quizId = ref(null);
const title = ref("");
const introText = ref("");
const totalQuestions = ref(0);

// Current question
const questionQueue = ref([]);
const currentOrd = ref(0);
const questionText = ref("");
const questionType = ref("multiple_choice");
const choices = ref([]);
const questionImage = ref(null);

// Answer state for the current question
const answered = ref(null);       // selected choice id, or null
const answerRecorded = ref(false); // true once quiz_answer_recorded arrives
const isCorrect = ref(null);      // true | false | null

// Running tally (final numbers from quiz_complete override these)
const numCorrect = ref(0);
const numAnswered = ref(0);

let advanceTimer = null;

// ---------------------------------------------------------------------------
// Incoming message handlers
// ---------------------------------------------------------------------------
function handleQuizStart(data) {
  resetState();
  screen.value = "intro";
  sessionId.value = data.session_id;
  quizId.value = data.quiz_id;
  title.value = data.title || "";
  introText.value = data.intro_voice_text || data.intro_text || "";
  totalQuestions.value = data.total_questions || 0;
}

function handleQuizQuestion(data) {
  questionQueue.value.push(data);
  // If we are in the question screen and waiting for the next question,
  // load it immediately.
  if (screen.value === "question" && advanceTimer === null) {
    loadNextQuestion();
  }
}

function handleQuizAnswerRecorded(data) {
  answerRecorded.value = true;
  isCorrect.value = data.is_correct;
  numAnswered.value++;
  if (data.is_correct) {
    numCorrect.value++;
  }

  // When advance is true, load the next question after a brief delay
  // so the user can see the correct/incorrect feedback.
  if (data.advance) {
    clearTimeout(advanceTimer);
    advanceTimer = setTimeout(() => {
      advanceTimer = null;
      loadNextQuestion();
    }, 1500);
  }
}

function handleQuizComplete(data) {
  clearTimeout(advanceTimer);
  advanceTimer = null;

  // Use server-authoritative tallies
  numCorrect.value = data.num_correct;
  numAnswered.value = data.num_answered;
  screen.value = "complete";
}

// ---------------------------------------------------------------------------
// State helpers
// ---------------------------------------------------------------------------
function resetState() {
  screen.value = "hidden";
  sessionId.value = null;
  quizId.value = null;
  title.value = "";
  introText.value = "";
  totalQuestions.value = 0;
  questionQueue.value = [];
  currentOrd.value = 0;
  questionText.value = "";
  questionType.value = "multiple_choice";
  choices.value = [];
  questionImage.value = null;
  answered.value = null;
  answerRecorded.value = false;
  isCorrect.value = null;
  numCorrect.value = 0;
  numAnswered.value = 0;
  clearTimeout(advanceTimer);
  advanceTimer = null;
}

function loadNextQuestion() {
  answered.value = null;
  answerRecorded.value = false;
  isCorrect.value = null;

  if (questionQueue.value.length > 0) {
    const q = questionQueue.value.shift();
    currentOrd.value = q.question_ord;
    questionText.value = q.question_text || "";
    questionType.value = q.question_type || "multiple_choice";
    choices.value = q.choices || [];
    questionImage.value = q.image || null;
  }
  // If the queue is empty, we stay in 'question' state and wait for
  // the next quiz_question message to arrive.
}

// ---------------------------------------------------------------------------
// User actions
// ---------------------------------------------------------------------------
function startQuiz() {
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
  });
}

function close() {
  screen.value = "hidden";
}

function onDialogClosed() {
  // After-leave hook — clean up if the dialog was dismissed via backdrop,
  // though persistent prevents that. Included for defensive safety.
}

// ---------------------------------------------------------------------------
// Color logic for choice buttons
// ---------------------------------------------------------------------------
function getChoiceColor(choiceId) {
  if (answered.value !== choiceId) return undefined;
  if (!answerRecorded.value) return "primary";
  return isCorrect.value === true ? "success" : "error";
}

const feedbackClass = computed(() => {
  if (!answerRecorded.value) return "";
  if (isCorrect.value === true) return "feedback-bar--correct";
  if (isCorrect.value === false) return "feedback-bar--incorrect";
  return "";
});

const feedbackIcon = computed(() => {
  if (!answerRecorded.value) return "";
  if (isCorrect.value === true) return "mdi-check-circle";
  if (isCorrect.value === false) return "mdi-close-circle";
  return "mdi-check";
});

const feedbackText = computed(() => {
  if (!answerRecorded.value) return "";
  if (isCorrect.value === true) return "Correct!";
  if (isCorrect.value === false) return "Not quite";
  return "Answer recorded";
});

// ---------------------------------------------------------------------------
// WS listener — all quiz messages flow through onStatus since wsClient
// does not have dedicated callback arrays for these types.
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
  }
}

onMounted(() => {
  wsClient.on("onStatus", onWsStatus);
});

onUnmounted(() => {
  clearTimeout(advanceTimer);
});

// Allow CompanionView (or tests) to trigger quiz_start programmatically.
defineExpose({ show: handleQuizStart });
</script>

<style scoped>
.quiz-card {
  border-radius: 16px;
}

/* ── Intro ─────────────────────────────────────────────────────────────── */
.intro-text {
  line-height: 1.7;
  white-space: pre-wrap;
  color: var(--cc-text-1);
}

.start-btn,
.done-btn {
  letter-spacing: 0.02em;
  font-weight: 600;
  border-radius: 12px;
}

/* ── Question ──────────────────────────────────────────────────────────── */
.question-title {
  word-break: break-word;
}

.question-image {
  border: 1px solid var(--cc-divider);
}

.choices-stack {
  display: flex;
  flex-direction: column;
}

.choice-btn {
  height: 56px !important;
  border-radius: 12px !important;
  font-weight: 600;
  letter-spacing: 0.01em;
  text-transform: none;
  transition: transform 0.12s ease, box-shadow 0.2s ease;
}

.choice-btn:not(:disabled):hover {
  transform: scale(1.01);
}

.choice-btn:not(:disabled):active {
  transform: scale(0.98);
}

.choice-btn--selected {
  box-shadow: 0 0 0 2px currentColor;
}

/* ── Open ended hint ───────────────────────────────────────────────────── */
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
  background: rgba(var(--v-theme-primary), 0.08);
  animation: mic-pulse 2s ease-in-out infinite;
}

@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(var(--v-theme-primary), 0.15); }
  50%      { box-shadow: 0 0 0 12px rgba(var(--v-theme-primary), 0); }
}

@media (prefers-reduced-motion: reduce) {
  .mic-icon-wrap { animation: none; }
}

/* ── Feedback bar ──────────────────────────────────────────────────────── */
.feedback-bar {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 0.875rem;
  font-weight: 600;
}

.feedback-bar--correct {
  background: rgba(var(--v-theme-success), 0.12);
  color: rgb(var(--v-theme-success));
}

.feedback-bar--incorrect {
  background: rgba(var(--v-theme-error), 0.12);
  color: rgb(var(--v-theme-error));
}

/* ── Complete screen ───────────────────────────────────────────────────── */
.score-text {
  letter-spacing: -0.02em;
}
</style>
