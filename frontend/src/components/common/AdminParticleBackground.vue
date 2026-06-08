<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref(null)

// Sage-400 (#5A896E) — warm, calm, brand-consistent
const PARTICLE_COLOR = [90 / 255, 137 / 255, 110 / 255]
let currentColor = PARTICLE_COLOR

const prefersReducedMotion =
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const NUM_PARTICLES = 70
const MAX_DIST = 130
const MOUSE_DIST = 180
const VELOCITY = 0.28

let particles = []
let mouse = { x: -1000, y: -1000 }
let animationId = 0
let cleanupFns = []

const vShaderSrc = `
attribute vec2 a_position;
attribute float a_alpha;
varying float v_alpha;
uniform vec2 u_resolution;
void main() {
  vec2 clipSpace = (a_position / u_resolution) * 2.0 - 1.0;
  gl_Position = vec4(clipSpace * vec2(1, -1), 0, 1);
  gl_PointSize = 2.5;
  v_alpha = a_alpha;
}
`

const fShaderSrc = `
precision mediump float;
varying float v_alpha;
uniform vec3 u_color;
void main() {
  gl_FragColor = vec4(u_color, v_alpha);
}
`

function makeShader(gl, type, src) {
  const s = gl.createShader(type)
  gl.shaderSource(s, src)
  gl.compileShader(s)
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { gl.deleteShader(s); return null }
  return s
}

function makeProgram(gl, vs, fs) {
  const p = gl.createProgram()
  gl.attachShader(p, vs)
  gl.attachShader(p, fs)
  gl.linkProgram(p)
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) { gl.deleteProgram(p); return null }
  return p
}

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return

  const gl = canvas.getContext('webgl', { premultipliedAlpha: false, alpha: true })
  if (!gl) return

  const vs = makeShader(gl, gl.VERTEX_SHADER, vShaderSrc)
  const fs = makeShader(gl, gl.FRAGMENT_SHADER, fShaderSrc)
  if (!vs || !fs) return

  const program = makeProgram(gl, vs, fs)
  if (!program) return

  const posLoc = gl.getAttribLocation(program, 'a_position')
  const alphaLoc = gl.getAttribLocation(program, 'a_alpha')
  const resLoc = gl.getUniformLocation(program, 'u_resolution')
  const colorLoc = gl.getUniformLocation(program, 'u_color')
  const buf = gl.createBuffer()

  function resize() {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
    gl.viewport(0, 0, canvas.width, canvas.height)
  }

  resize()
  window.addEventListener('resize', resize)

  particles = []
  for (let i = 0; i < NUM_PARTICLES; i++) {
    particles.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * VELOCITY * 2,
      vy: (Math.random() - 0.5) * VELOCITY * 2,
    })
  }

  function onMouseMove(e) { mouse.x = e.clientX; mouse.y = e.clientY }
  function onTouchMove(e) {
    if (e.touches.length > 0) { mouse.x = e.touches[0].clientX; mouse.y = e.touches[0].clientY }
  }
  function onOut() { mouse.x = -1000; mouse.y = -1000 }

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('touchmove', onTouchMove, { passive: true })
  document.addEventListener('mouseleave', onOut)
  window.addEventListener('touchend', onOut)

  function draw() {
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.useProgram(program)
    gl.uniform2f(resLoc, canvas.width, canvas.height)
    const [cr, cg, cb] = currentColor
    gl.uniform3f(colorLoc, cr, cg, cb)

    const verts = []

    for (let i = 0; i < NUM_PARTICLES; i++) {
      const p = particles[i]
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > canvas.width) p.vx *= -1
      if (p.y < 0 || p.y > canvas.height) p.vy *= -1

      const dxm = mouse.x - p.x
      const dym = mouse.y - p.y
      const dm = Math.sqrt(dxm * dxm + dym * dym)
      if (dm < MOUSE_DIST) {
        p.x += dxm * 0.003
        p.y += dym * 0.003
      }

      verts.push(p.x, p.y, 0.7)
    }

    for (let i = 0; i < NUM_PARTICLES; i++) {
      const p1 = particles[i]
      for (let j = i + 1; j < NUM_PARTICLES; j++) {
        const p2 = particles[j]
        const dx = p1.x - p2.x
        const dy = p1.y - p2.y
        const d2 = dx * dx + dy * dy
        if (d2 < MAX_DIST * MAX_DIST) {
          const a = (1 - Math.sqrt(d2) / MAX_DIST) * 0.45
          verts.push(p1.x, p1.y, a, p2.x, p2.y, a)
        }
      }
    }

    const data = new Float32Array(verts)
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW)

    const stride = 12 // 3 floats × 4 bytes
    gl.enableVertexAttribArray(posLoc)
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, stride, 0)
    gl.enableVertexAttribArray(alphaLoc)
    gl.vertexAttribPointer(alphaLoc, 1, gl.FLOAT, false, stride, 8)

    gl.enable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)

    gl.drawArrays(gl.POINTS, 0, NUM_PARTICLES)
    const total = data.length / 3
    if (total > NUM_PARTICLES) {
      gl.drawArrays(gl.LINES, NUM_PARTICLES, total - NUM_PARTICLES)
    }

    if (!prefersReducedMotion) {
      animationId = requestAnimationFrame(draw)
    }
  }

  draw()

  cleanupFns = [
    () => cancelAnimationFrame(animationId),
    () => window.removeEventListener('resize', resize),
    () => window.removeEventListener('mousemove', onMouseMove),
    () => window.removeEventListener('touchmove', onTouchMove),
    () => document.removeEventListener('mouseleave', onOut),
    () => window.removeEventListener('touchend', onOut),
  ]
})

onUnmounted(() => {
  cleanupFns.forEach((fn) => fn())
  cleanupFns = []
  particles = []
})
</script>

<template>
  <canvas ref="canvasRef" class="admin-particles" aria-hidden="true" />
</template>

<style scoped>
/*
 * Full-viewport canvas masked to the top 20% and bottom 20% of the screen.
 * Top band fades from 100% opacity at 0% → 0% at the 20% mark.
 * Bottom band fades from 0% at the 80% mark → 100% at 100%.
 * Middle 60% is fully transparent so it never interferes with content.
 * z-index 0 keeps it behind VMain content (z-index: auto, later in DOM)
 * while VAppBar / VNavigationDrawer (z-index ≈1004) always paint above.
 */
.admin-particles {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  pointer-events: none;
  mask-image: linear-gradient(
    to bottom,
    black 0%,
    transparent 20%,
    transparent 80%,
    black 100%
  );
  -webkit-mask-image: linear-gradient(
    to bottom,
    black 0%,
    transparent 20%,
    transparent 80%,
    black 100%
  );
}
</style>
