<template>
  <div ref="containerRef" class="visualizer-wrap" :class="stateClass">
    <canvas ref="canvasRef" class="visualizer-canvas" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { ccToken } from "@/composables/useChartTheme.js";

const props = defineProps({
  audioState: { type: String, default: "idle" },
  // When false, voice-activity state changes are suppressed so the card
  // stays at "idle" until the user explicitly starts recording.
  recording: { type: Boolean, default: false },
});

// `capture-change` reports whether the microphone is really open ({ live, error }),
// which `recording` alone cannot: recording is the wish to listen, and a denied or
// missing microphone must never be shown to her as "Listening".
const emit = defineEmits(["audio-data", "state-change", "capture-change"]);

const canvasRef = ref(null);
const containerRef = ref(null);

let audioContext = null;
let analyser = null;
let mediaStream = null;
let processor = null;
let highPassFilter = null;
let animFrameId = null;
let resizeObserver = null;
let phase = 0;
let currentRms = 0;

// Tracks the last state we emitted so we only call emit() on actual transitions,
// preventing redundant parent re-renders and ensuring every state is explicit.
let _lastEmitted = "idle";

const VAD_THRESHOLD = ref(0.06);
const isCalibrating = ref(false);
const calibrationSamples = [];

const CANVAS_HEIGHT = 150;

const stateClass = computed(() => `state-${props.audioState}`);

// ─── State helper ────────────────────────────────────────────────────────────

function _emitState(state) {
  if (state !== _lastEmitted) {
    _lastEmitted = state;
    emit("state-change", state);
  }
}

// ─── Recording prop drives capture and listening/idle transitions ────────────
// The microphone is open only while `recording` is true. Opening it on mount would
// capture in a room nobody asked to listen to, and, before any tap, leave its
// AudioContext suspended by the browser's autoplay policy so it never produced
// audio. The ambient noise floor is calibrated at the start of each recording.

// Bumped on every recording change so a slow `startMic` that finishes after the
// recording was turned off again closes what it opened instead of keeping it.
let captureGeneration = 0;
let captureFailed = false;

watch(
  () => props.recording,
  async (active) => {
    _emitState(active ? "listening" : "idle");
    const generation = ++captureGeneration;
    if (!active) {
      stopMic();
      return;
    }
    if (!audioContext) {
      await startMic();
    } else if (audioContext.state === "suspended") {
      await audioContext.resume();
    }
    if (generation !== captureGeneration && !props.recording) stopMic();
  },
  { immediate: true },
);

// ─── Canvas sizing ──────────────────────────────────────────────────────────

function resizeCanvas() {
  const canvas = canvasRef.value;
  const container = containerRef.value;
  if (!canvas || !container) return;

  const w = container.getBoundingClientRect().width || 400;
  const dpr = window.devicePixelRatio || 1;

  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(CANVAS_HEIGHT * dpr);
  canvas.style.width = `${w}px`;
  canvas.style.height = `${CANVAS_HEIGHT}px`;

  const ctx = canvas.getContext("2d");
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

// ─── Animation ──────────────────────────────────────────────────────────────

// Warm DS waveform palette (stone idle, sage listening, gold speaking, sage
// system). Tokens live in styles/theme.css and match VoiceWidget status pills.
const COLOR_TOKEN_SETS = {
  idle: ["--cc-visualizer-idle-1", "--cc-visualizer-idle-2", "--cc-visualizer-idle-3"],
  listening: [
    "--cc-visualizer-listening-1",
    "--cc-visualizer-listening-2",
    "--cc-visualizer-listening-3",
  ],
  speaking: [
    "--cc-visualizer-speaking-1",
    "--cc-visualizer-speaking-2",
    "--cc-visualizer-speaking-3",
  ],
  system_speaking: [
    "--cc-visualizer-system-1",
    "--cc-visualizer-system-2",
    "--cc-visualizer-system-3",
  ],
};

function resolveColorSet(audioState) {
  const tokens = COLOR_TOKEN_SETS[audioState] ?? COLOR_TOKEN_SETS.idle;
  return tokens.map((name) => ccToken(name));
}

function draw() {
  const canvas = canvasRef.value;
  const ctx = canvas?.getContext("2d");
  if (!ctx) {
    animFrameId = requestAnimationFrame(draw);
    return;
  }

  const width = canvas.clientWidth || 400;
  const height = CANVAS_HEIGHT;
  ctx.clearRect(0, 0, width, height);

  const state = props.audioState;

  let targetAmplitude = 4;
  let speed = 0.04;

  if (state === "listening") {
    const ratio = Math.min(currentRms / Math.max(VAD_THRESHOLD.value, 0.001), 1);
    targetAmplitude = 5 + ratio * 24;
    speed = 0.07;
  } else if (state === "speaking") {
    if (analyser) {
      const data = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += Math.abs(data[i] - 128);
      targetAmplitude = Math.max(30, (sum / data.length) * 3.5);
    } else {
      targetAmplitude = 50;
    }
    speed = 0.14;
  } else if (state === "system_speaking") {
    targetAmplitude = 54;
    speed = 0.11;
  }

  phase += speed;

  const colors = resolveColorSet(state);

  for (let c = 0; c < colors.length; c++) {
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    for (let x = 0; x < width; x++) {
      const envelope = Math.sin((x / width) * Math.PI);
      const y = height / 2 + envelope * targetAmplitude * Math.sin(x * 0.03 + phase + c * 1.6);
      ctx.lineTo(x, y);
    }
    ctx.strokeStyle = colors[c];
    ctx.lineWidth = 2.5 + (colors.length - c) * 0.6;
    ctx.stroke();
  }

  animFrameId = requestAnimationFrame(draw);
}

// ─── Microphone ─────────────────────────────────────────────────────────────

async function startMic() {
  try {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 16000,
    });
    // Created outside a tap (a server-sent "listen now"), the context may start
    // suspended; it is resumed here because nothing else would.
    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
    });
    emit("capture-change", { live: true, error: null });

    const source = audioContext.createMediaStreamSource(mediaStream);

    // High-pass filter: attenuates frequencies below ~150 Hz.
    // Fan and AC hum typically sits at 50-120 Hz; filtering before the
    // analyser and processor removes those frequencies from both the RMS
    // calculation and the PCM stream sent to the backend.
    highPassFilter = audioContext.createBiquadFilter();
    highPassFilter.type = "highpass";
    highPassFilter.frequency.value = 150;
    highPassFilter.Q.value = 0.7;
    source.connect(highPassFilter);

    analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    highPassFilter.connect(analyser);

    processor = audioContext.createScriptProcessor(4096, 1, 1);
    highPassFilter.connect(processor);
    processor.connect(audioContext.destination);

    // Calibrate ambient noise floor for 2.5 s before evaluating VAD.
    // Sampling runs on the filtered signal so residual low-frequency hum
    // does not inflate the threshold.
    isCalibrating.value = true;
    calibrationSamples.length = 0;
    setTimeout(() => {
      isCalibrating.value = false;
      if (calibrationSamples.length > 0) {
        const avg = calibrationSamples.reduce((a, b) => a + b, 0) / calibrationSamples.length;
        VAD_THRESHOLD.value = Math.max(0.015, avg + 0.025);
      }
    }, 2500);

    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);

      // RMS on the high-pass filtered signal
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      currentRms = Math.sqrt(sum / input.length);

      if (isCalibrating.value) {
        calibrationSamples.push(currentRms);
      } else if (props.recording) {
        // While the user has the mic active, toggle between "speaking" and
        // "listening" based on signal level.  Never emit either state when
        // recording is false so background noise never moves the status pill.
        _emitState(currentRms > VAD_THRESHOLD.value ? "speaking" : "listening");
      }

      // Always emit PCM16; the parent guards whether to send it to the backend.
      const buf = new ArrayBuffer(input.length * 2);
      const view = new DataView(buf);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      emit("audio-data", buf);
    };
  } catch (err) {
    console.error("Mic error:", err);
    stopMic(false);
    captureFailed = true;
    _emitState("idle");
    emit("capture-change", { live: false, error: err?.name || "Error" });
  }
}

function stopMic(emitCleared = true) {
  if (emitCleared && (mediaStream || captureFailed)) {
    captureFailed = false;
    emit("capture-change", { live: false, error: null });
  }
  processor?.disconnect();
  highPassFilter?.disconnect();
  mediaStream?.getTracks().forEach((t) => t.stop());
  audioContext?.close();
  processor = null;
  highPassFilter = null;
  analyser = null;
  mediaStream = null;
  audioContext = null;
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  resizeCanvas();
  resizeObserver = new ResizeObserver(resizeCanvas);
  if (containerRef.value) resizeObserver.observe(containerRef.value);
  draw();
});

onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId);
  resizeObserver?.disconnect();
  stopMic();
});
</script>

<style scoped>
.visualizer-wrap {
  width: 100%;
  border-radius: var(--cc-radius-md);
  overflow: hidden;
  transition: filter var(--cc-dur-slow) var(--cc-ease-standard);
}

.state-listening {
  filter: drop-shadow(0 0 12px var(--cc-brand-glow));
}

.state-speaking {
  filter: drop-shadow(0 0 12px var(--cc-warning-glow));
}

.state-system_speaking {
  filter: drop-shadow(0 0 14px var(--cc-brand-glow));
}

@media (prefers-reduced-motion: reduce) {
  .visualizer-wrap {
    transition: none;
  }
}

.visualizer-canvas {
  display: block;
  width: 100%;
  height: 150px;
}
</style>
