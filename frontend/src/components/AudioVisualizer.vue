<template>
  <div ref="containerRef" class="visualizer-wrap" :class="stateClass">
    <canvas ref="canvasRef" class="visualizer-canvas" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";

const props = defineProps({
  audioState: { type: String, default: "idle" },
});

const emit = defineEmits(["audio-data", "state-change"]);

const canvasRef = ref(null);
const containerRef = ref(null);

let audioContext = null;
let analyser = null;
let mediaStream = null;
let processor = null;
let animFrameId = null;
let resizeObserver = null;
let phase = 0;
let currentRms = 0;

const VAD_THRESHOLD = ref(0.06);
const isCalibrating = ref(false);
const calibrationSamples = [];

const CANVAS_HEIGHT = 150;

const stateClass = computed(() => `state-${props.audioState}`);

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

const COLOR_SETS = {
  idle:           ["rgba(255,255,255,0.10)", "rgba(255,255,255,0.06)", "rgba(255,255,255,0.03)"],
  listening:      ["rgba(99,102,241,0.80)",  "rgba(139,92,246,0.55)", "rgba(167,139,250,0.30)"],
  speaking:       ["rgba(245,158,11,0.80)",  "rgba(251,191,36,0.55)", "rgba(253,230,138,0.30)"],
  system_speaking:["rgba(139,92,246,0.80)",  "rgba(167,139,250,0.58)","rgba(196,181,253,0.35)"],
};

function draw() {
  const canvas = canvasRef.value;
  const ctx = canvas?.getContext("2d");
  if (!ctx) {
    animFrameId = requestAnimationFrame(draw);
    return;
  }

  const width  = canvas.clientWidth || 400;
  const height = CANVAS_HEIGHT;
  ctx.clearRect(0, 0, width, height);

  const state = props.audioState;

  // Determine target amplitude and phase speed
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

  // Three overlapping sine waves with bell-curve envelope (Siri effect)
  for (let c = 0; c < colors.length; c++) {
    ctx.beginPath();
    ctx.moveTo(0, height / 2);

    for (let x = 0; x < width; x++) {
      const envelope = Math.sin((x / width) * Math.PI); // tapers at edges
      const y = height / 2
        + envelope * targetAmplitude
        * Math.sin(x * 0.030 + phase + c * 1.6);
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
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
    });

    const source = audioContext.createMediaStreamSource(mediaStream);

    analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    processor = audioContext.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    processor.connect(audioContext.destination);

    // Calibrate ambient noise floor for 2.5 s before forwarding VAD events
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

      // RMS for VAD
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      currentRms = Math.sqrt(sum / input.length);

      if (isCalibrating.value) {
        calibrationSamples.push(currentRms);
      } else if (currentRms > VAD_THRESHOLD.value) {
        emit("state-change", "speaking");
      }

      // PCM16 buffer for backend
      const buf = new ArrayBuffer(input.length * 2);
      const view = new DataView(buf);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      emit("audio-data", buf);
    };

    emit("state-change", "listening");
  } catch (err) {
    console.error("Mic error:", err);
  }
}

function stopMic() {
  processor?.disconnect();
  mediaStream?.getTracks().forEach((t) => t.stop());
  audioContext?.close();
  processor = null;
  analyser  = null;
  mediaStream = null;
  audioContext = null;
  emit("state-change", "idle");
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
  border-radius: 12px;
  overflow: hidden;
  transition: filter 0.4s ease;
}

.state-listening {
  filter: drop-shadow(0 0 12px rgba(99, 102, 241, 0.35));
}

.state-speaking {
  filter: drop-shadow(0 0 12px rgba(245, 158, 11, 0.35));
}

.state-system_speaking {
  filter: drop-shadow(0 0 14px rgba(139, 92, 246, 0.40));
}

.visualizer-canvas {
  display: block;
  width: 100%;
  height: 150px;
}
</style>
