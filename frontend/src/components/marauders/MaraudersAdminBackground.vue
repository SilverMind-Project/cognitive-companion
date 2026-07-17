<template>
  <div
    class="marauders-admin-background"
    :class="{ 'is-reduced-motion': state.reducedMotion }"
    aria-hidden="true"
  >
    <canvas ref="canvasRef" class="ink-network" />
    <svg
      class="decorative-footprints"
      viewBox="0 0 1200 800"
      preserveAspectRatio="none"
      focusable="false"
    >
      <MaraudersFootprintGlyph
        v-for="print in decorativePrints"
        :key="print.key"
        class="map-footprint"
        :class="`map-footprint--${print.phase}`"
        :transform="print.transform"
        :mirrored="print.mirrored"
      />
    </svg>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useMaraudersMode } from "@/composables/useMaraudersMode.js";
import MaraudersFootprintGlyph from "@/components/marauders/MaraudersFootprintGlyph.vue";

const NUM_PARTICLES = 58;
const MAX_DIST = 140;
const MOUSE_DIST = 180;
const VELOCITY = 0.22;
const NODE_SEGMENTS = 9;

const decorativePrints = [
  { key: "top-1", phase: 1, transform: "translate(455 86) rotate(66)", mirrored: false },
  { key: "top-2", phase: 2, transform: "translate(475 103) rotate(62)", mirrored: true },
  { key: "top-3", phase: 3, transform: "translate(500 105) rotate(72)", mirrored: false },
  { key: "bottom-1", phase: 2, transform: "translate(880 680) rotate(-68)", mirrored: true },
  { key: "bottom-2", phase: 3, transform: "translate(902 663) rotate(-62)", mirrored: false },
  { key: "bottom-3", phase: 1, transform: "translate(927 660) rotate(-72)", mirrored: true },
];

const canvasRef = ref(null);
const { state } = useMaraudersMode();

let particles = [];
let mouse = { x: -1000, y: -1000 };
let animationId = 0;
let context = null;
let cleanupFns = [];

function seededUnit(seed) {
  const value = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return value - Math.floor(value);
}

function pairSeed(a, b, pass = 0) {
  return (a + 1) * 92821 + (b + 1) * 68917 + pass * 283;
}

function initializeParticles(width, height) {
  particles = Array.from({ length: NUM_PARTICLES }, (_, index) => ({
    index,
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * VELOCITY * 2,
    vy: (Math.random() - 0.5) * VELOCITY * 2,
  }));
}

function moveParticles(width, height) {
  for (const particle of particles) {
    particle.x += particle.vx;
    particle.y += particle.vy;

    if (particle.x < 0 || particle.x > width) particle.vx *= -1;
    if (particle.y < 0 || particle.y > height) particle.vy *= -1;

    const dx = mouse.x - particle.x;
    const dy = mouse.y - particle.y;
    const distance = Math.sqrt(dx * dx + dy * dy);
    if (distance < MOUSE_DIST) {
      particle.x += dx * 0.003;
      particle.y += dy * 0.003;
    }
  }
}

function drawSketchEdge(ctx, first, second, alpha) {
  const midX = (first.x + second.x) / 2;
  const midY = (first.y + second.y) / 2;

  for (let pass = 0; pass < 2; pass++) {
    const seed = pairSeed(first.index, second.index, pass);
    const startJitterX = (seededUnit(seed) - 0.5) * 1.7;
    const startJitterY = (seededUnit(seed + 1) - 0.5) * 1.7;
    const endJitterX = (seededUnit(seed + 2) - 0.5) * 1.7;
    const endJitterY = (seededUnit(seed + 3) - 0.5) * 1.7;
    const bendX = (seededUnit(seed + 4) - 0.5) * 7;
    const bendY = (seededUnit(seed + 5) - 0.5) * 7;

    ctx.globalAlpha = alpha * (pass === 0 ? 0.72 : 0.34);
    ctx.lineWidth = pass === 0 ? 0.85 : 0.45;
    ctx.beginPath();
    ctx.moveTo(first.x + startJitterX, first.y + startJitterY);
    ctx.quadraticCurveTo(midX + bendX, midY + bendY, second.x + endJitterX, second.y + endJitterY);
    ctx.stroke();
  }
}

function drawInkNode(ctx, particle) {
  const baseRadius = 1.35 + seededUnit(particle.index + 41) * 1.1;

  ctx.globalAlpha = 0.68;
  ctx.lineWidth = 0.75;
  ctx.beginPath();

  for (let segment = 0; segment <= NODE_SEGMENTS; segment++) {
    const angle = (segment / NODE_SEGMENTS) * Math.PI * 2;
    const radiusJitter = 0.72 + seededUnit(particle.index * 31 + segment) * 0.5;
    const x = particle.x + Math.cos(angle) * baseRadius * radiusJitter;
    const y = particle.y + Math.sin(angle) * baseRadius * radiusJitter;
    if (segment === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }

  ctx.closePath();
  ctx.stroke();

  ctx.globalAlpha = 0.22;
  ctx.fill();
}

function drawScene({ advance }) {
  if (!context || !canvasRef.value) return;

  const canvas = canvasRef.value;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;

  context.clearRect(0, 0, width, height);
  context.strokeStyle = getComputedStyle(canvas).color;
  context.fillStyle = getComputedStyle(canvas).color;
  context.lineCap = "round";
  context.lineJoin = "round";

  if (advance) moveParticles(width, height);

  for (let firstIndex = 0; firstIndex < particles.length; firstIndex++) {
    const first = particles[firstIndex];
    for (let secondIndex = firstIndex + 1; secondIndex < particles.length; secondIndex++) {
      const second = particles[secondIndex];
      const dx = first.x - second.x;
      const dy = first.y - second.y;
      const distanceSquared = dx * dx + dy * dy;
      if (distanceSquared >= MAX_DIST * MAX_DIST) continue;

      const alpha = (1 - Math.sqrt(distanceSquared) / MAX_DIST) * 0.48;
      drawSketchEdge(context, first, second, alpha);
    }
  }

  for (const particle of particles) drawInkNode(context, particle);
  context.globalAlpha = 1;
}

function runFrame() {
  animationId = 0;
  drawScene({ advance: !state.reducedMotion });
  if (!state.reducedMotion) animationId = requestAnimationFrame(runFrame);
}

onMounted(() => {
  const canvas = canvasRef.value;
  if (!canvas) return;

  context = canvas.getContext("2d");
  if (!context) return;

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const width = window.innerWidth;
    const height = window.innerHeight;

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (!particles.length) initializeParticles(width, height);
    drawScene({ advance: false });
  }

  function onMouseMove(event) {
    mouse.x = event.clientX;
    mouse.y = event.clientY;
  }

  function onTouchMove(event) {
    if (!event.touches.length) return;
    mouse.x = event.touches[0].clientX;
    mouse.y = event.touches[0].clientY;
  }

  function clearPointer() {
    mouse = { x: -1000, y: -1000 };
  }

  resize();
  window.addEventListener("resize", resize);
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("touchmove", onTouchMove, { passive: true });
  document.addEventListener("mouseleave", clearPointer);
  window.addEventListener("touchend", clearPointer);

  if (!state.reducedMotion) animationId = requestAnimationFrame(runFrame);

  cleanupFns = [
    () => cancelAnimationFrame(animationId),
    () => window.removeEventListener("resize", resize),
    () => window.removeEventListener("mousemove", onMouseMove),
    () => window.removeEventListener("touchmove", onTouchMove),
    () => document.removeEventListener("mouseleave", clearPointer),
    () => window.removeEventListener("touchend", clearPointer),
  ];
});

watch(
  () => state.reducedMotion,
  (reducedMotion) => {
    if (!context) return;
    if (reducedMotion) {
      cancelAnimationFrame(animationId);
      animationId = 0;
      drawScene({ advance: false });
    } else if (!animationId) {
      animationId = requestAnimationFrame(runFrame);
    }
  },
);

onUnmounted(() => {
  cleanupFns.forEach((cleanup) => cleanup());
  cleanupFns = [];
  particles = [];
  context = null;
});
</script>

<style scoped>
.marauders-admin-background {
  position: fixed;
  inset: 0;
  z-index: 0;
  color: var(--cc-particle);
  pointer-events: none;
  mask-image: linear-gradient(to bottom, black 0%, transparent 22%, transparent 78%, black 100%);
  -webkit-mask-image: linear-gradient(
    to bottom,
    black 0%,
    transparent 22%,
    transparent 78%,
    black 100%
  );
}

.ink-network,
.decorative-footprints {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.ink-network {
  opacity: 0.48;
}

.decorative-footprints {
  overflow: visible;
}

.map-footprint {
  color: var(--cc-annotation-ink);
  opacity: 0.18;
  animation: marauders-print-fade 7.5s ease-in-out infinite;
}

.map-footprint--2 {
  animation-delay: -2.5s;
}

.map-footprint--3 {
  animation-delay: -5s;
}

@keyframes marauders-print-fade {
  0%,
  100% {
    opacity: 0.12;
  }
  45% {
    opacity: 0.5;
  }
}

@media (prefers-reduced-motion: reduce) {
  .map-footprint {
    animation: none;
  }
}

.is-reduced-motion .map-footprint {
  animation: none;
}
</style>
