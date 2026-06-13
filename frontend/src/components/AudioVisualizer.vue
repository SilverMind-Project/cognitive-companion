<template>
  <div ref="containerRef" class="visualizer-wrap" :class="stateClass">
    <canvas ref="canvasRef" class="visualizer-canvas" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from "vue";

const props = defineProps({
  audioState: { type: String,  default: "idle" },
  // When false, voice-activity state changes are suppressed so the card
  // stays at "idle" until the user explicitly starts recording.
  recording:  { type: Boolean, default: false },
});

const emit = defineEmits(["audio-data", "state-change"]);

const canvasRef    = ref(null);
const containerRef = ref(null);

let audioContext   = null;
let analyser       = null;
let mediaStream    = null;
let processor      = null;
let highPassFilter = null;
let animFrameId    = null;
let resizeObserver = null;
let phase          = 0;
let currentRms     = 0;

// Tracks the last state we emitted so we only call emit() on actual transitions,
// preventing redundant parent re-renders and ensuring every state is explicit.
let _lastEmitted = "idle";

const VAD_THRESHOLD      = ref(0.06);
const isCalibrating      = ref(false);
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

// ─── Recording prop drives listening/idle transitions ────────────────────────
// The mic always runs for calibration, but the status pill must only change
// state when the user has tapped the button.

watch(() => props.recording, (active) => {
  _emitState(active ? "listening" : "idle");
}, { immediate: true });

// ─── Canvas sizing ──────────────────────────────────────────────────────────

function resizeCanvas() {
  const canvas = canvasRef.value;
  const container = containerRef.value;
  if (!canvas || !container) return;

  const w = container.getBoundingClientRect().width || 400;
  const dpr = window.devicePixelRatio || 1;

  canvas.width  = Math.floor(w * dpr);
  canvas.height = Math.floor(CANVAS_HEIGHT * dpr);
  canvas.style.width  = `${w}px`;
  canvas.style.height = `${CANVAS_HEIGHT}px`;

  const ctx = canvas.getContext("2d");
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

// ─── Animation ──────────────────────────────────────────────────────────────

// Warm DS waveform palette (stone idle, sage listening, gold speaking, sage
// system). Tints match the status-pill pairs in VoiceWidget.
const COLOR_SETS = {
  idle:           ["rgba(135,121,96,0.18)", "rgba(135,121,96,0.10)", "rgba(135,121,96,0.05)"],
  listening:      ["rgba(63,107,82,0.85)",  "rgba(90,137,110,0.55)", "rgba(130,178,146,0.30)"],
  speaking:       ["rgba(201,138,46,0.85)", "rgba(220,141,107,0.55)","rgba(240,217,168,0.35)"],
  system_speaking:["rgba(48,83,64,0.85)",   "rgba(63,107,82,0.55)",  "rgba(130,178,146,0.32)"],
};

function draw() {
  const canvas = canvasRef.value;
  const ctx    = canvas?.getContext("2d");
  if (!ctx) {
    animFrameId = requestAnimationFrame(draw);
    return;
  }

  const width  = canvas.clientWidth || 400;
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

  const colors = COLOR_SETS[state] ?? COLOR_SETS.idle;

  for (let c = 0; c < colors.length; c++) {
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    for (let x = 0; x < width; x++) {
      const envelope = Math.sin((x / width) * Math.PI);
      const y = height / 2
        + envelope * targetAmplitude
        * Math.sin(x * 0.030 + phase + c * 1.6);
      ctx.lineTo(x, y);
    }
    ctx.strokeStyle = colors[c];
    ctx.lineWidth   = 2.5 + (colors.length - c) * 0.6;
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
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
    });

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
    isCalibrating.value   = true;
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
      const buf  = new ArrayBuffer(input.length * 2);
      const view = new DataView(buf);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      emit("audio-data", buf);
    };
  } catch (err) {
    console.error("Mic error:", err);
  }
}

function stopMic() {
  processor?.disconnect();
  highPassFilter?.disconnect();
  mediaStream?.getTracks().forEach((t) => t.stop());
  audioContext?.close();
  processor      = null;
  highPassFilter = null;
  analyser       = null;
  mediaStream    = null;
  audioContext   = null;
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  resizeCanvas();
  resizeObserver = new ResizeObserver(resizeCanvas);
  if (containerRef.value) resizeObserver.observe(containerRef.value);
  draw();
  startMic();
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
  filter: drop-shadow(0 0 12px rgba(63, 107, 82, 0.30));
}

.state-speaking {
  filter: drop-shadow(0 0 12px rgba(201, 138, 46, 0.30));
}

.state-system_speaking {
  filter: drop-shadow(0 0 14px rgba(63, 107, 82, 0.32));
}

@media (prefers-reduced-motion: reduce) {
  .visualizer-wrap { transition: none; }
}

.visualizer-canvas {
  display: block;
  width: 100%;
  height: 150px;
}
</style>
