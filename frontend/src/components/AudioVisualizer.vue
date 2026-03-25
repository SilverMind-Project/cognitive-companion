<template>
  <canvas ref="canvas" class="audio-canvas" />
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from "vue";

const props = defineProps({
  audioState: { type: String, default: "idle" },
});

const emit = defineEmits(["audio-data", "state-change"]);

const canvas = ref(null);
let audioContext = null;
let analyser = null;
let mediaStream = null;
let processor = null;
let animFrameId = null;

function draw() {
  const ctx = canvas.value?.getContext("2d");
  if (!ctx || !analyser) {
    animFrameId = requestAnimationFrame(draw);
    return;
  }

  const w = canvas.value.width;
  const h = canvas.value.height;
  const data = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteTimeDomainData(data);

  ctx.clearRect(0, 0, w, h);

  // Draw waveform
  ctx.lineWidth = 2;
  ctx.strokeStyle = props.audioState === "idle" ? "#444" : "#6366f1";
  ctx.beginPath();

  const sliceWidth = w / data.length;
  let x = 0;
  for (let i = 0; i < data.length; i++) {
    const v = data[i] / 128.0;
    const y = (v * h) / 2;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
    x += sliceWidth;
  }
  ctx.lineTo(w, h / 2);
  ctx.stroke();

  animFrameId = requestAnimationFrame(draw);
}

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

    // Use ScriptProcessor for raw PCM streaming
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    processor.connect(audioContext.destination);

    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      // Convert float32 to int16
      const buffer = new ArrayBuffer(input.length * 2);
      const view = new DataView(buffer);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      }
      emit("audio-data", buffer);

      // Simple VAD
      let rms = 0;
      for (let i = 0; i < input.length; i++) rms += input[i] * input[i];
      rms = Math.sqrt(rms / input.length);
      if (rms > 0.01) {
        emit("state-change", "speaking");
      }
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
  analyser = null;
  mediaStream = null;
  audioContext = null;
  emit("state-change", "idle");
}

watch(() => props.audioState, (state, oldState) => {
  // External control could trigger mic start/stop
});

onMounted(() => {
  if (canvas.value) {
    const dpr = window.devicePixelRatio || 1;
    canvas.value.width = 400 * dpr;
    canvas.value.height = 200 * dpr;
    canvas.value.style.width = "400px";
    canvas.value.style.height = "200px";
  }
  draw();
  startMic();
});

onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId);
  stopMic();
});
</script>

<style scoped>
.audio-canvas {
  max-width: 100%;
  border-radius: 12px;
}
</style>
