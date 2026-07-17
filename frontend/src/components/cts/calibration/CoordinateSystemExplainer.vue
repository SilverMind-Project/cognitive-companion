<template>
  <!-- Coordinate system explainer -->
  <v-card class="mb-4">
    <v-card-title class="text-subtitle-2">
      <v-icon size="16" class="mr-1">mdi-help-circle-outline</v-icon>
      What do X and Y metres mean?
    </v-card-title>
    <v-card-text class="pb-2">
      <!-- SVG diagram -->
      <svg viewBox="0 0 320 218" class="coord-diagram">
        <!-- Floor plan rectangle -->
        <rect
          x="20"
          y="34"
          width="280"
          height="160"
          rx="4"
          fill="rgba(99,102,241,0.07)"
          stroke="var(--cc-brand)"
          stroke-width="1.5"
          stroke-dasharray="6 3"
        />
        <text x="160" y="12" text-anchor="middle" fill="var(--cc-brand)" font-size="10" font-weight="600">
          Floor plan image
        </text>

        <!-- Origin -->
        <circle cx="20" cy="34" r="5" fill="var(--cc-brand)" />
        <text x="26" y="32" fill="var(--cc-brand)" font-size="10" font-weight="700">
          Origin (0, 0)
        </text>
        <text x="26" y="44" fill="var(--cc-text-3)" font-size="9">top-left corner</text>

        <!-- X axis -->
        <line
          x1="20"
          y1="34"
          x2="280"
          y2="34"
          stroke="var(--cc-brand)"
          stroke-width="1.5"
          marker-end="url(#arrowX)"
        />
        <text x="290" y="38" fill="var(--cc-brand)" font-size="11" font-weight="700">X</text>
        <text x="145" y="30" text-anchor="middle" fill="var(--cc-brand)" font-size="9">
          → increases right
        </text>

        <!-- Y axis -->
        <line
          x1="20"
          y1="34"
          x2="20"
          y2="179"
          stroke="var(--cc-brand)"
          stroke-width="1.5"
          marker-end="url(#arrowY)"
        />
        <text x="6" y="189" fill="var(--cc-brand)" font-size="11" font-weight="700">Y</text>
        <text
          x="12"
          y="106"
          text-anchor="middle"
          fill="var(--cc-brand)"
          font-size="9"
          transform="rotate(-90 12 106)"
        >
          ↓ increases downward
        </text>

        <!-- Example point -->
        <circle cx="180" cy="134" r="5" fill="#10b981" />
        <!-- X dashed measurement line -->
        <line
          x1="20"
          y1="134"
          x2="180"
          y2="134"
          stroke="#10b981"
          stroke-width="1"
          stroke-dasharray="4 3"
        />
        <text x="100" y="129" text-anchor="middle" fill="#10b981" font-size="10">X = 3.2 m</text>
        <!-- Y dashed measurement line -->
        <line
          x1="180"
          y1="34"
          x2="180"
          y2="134"
          stroke="#10b981"
          stroke-width="1"
          stroke-dasharray="4 3"
        />
        <text x="215" y="84" text-anchor="middle" fill="#10b981" font-size="10">Y = 2.5 m</text>

        <!-- Arrow markers -->
        <defs>
          <marker id="arrowX" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="var(--cc-brand)" />
          </marker>
          <marker id="arrowY" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="var(--cc-brand)" />
          </marker>
        </defs>
      </svg>

      <div class="text-body-2 mt-2">
        <strong>X</strong> and <strong>Y</strong> are straight-line distances measured
        <em>on the floor</em> — not from the camera, not slanted distances through the air.
        Measure them as if you were standing on the floor with a tape measure, from the top-left
        corner of your floor plan image.
      </div>
      <v-alert type="warning" variant="tonal" density="compact" class="mt-3 text-caption">
        All cameras must use the <strong>same origin</strong>. If camera A calls the front door
        "X=0, Y=0" and camera B calls it "X=1, Y=0", tracks will not align on the shared floor
        plan.
      </v-alert>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.coord-diagram {
  display: block;
  width: 100%;
  max-width: 320px;
  height: auto;
  margin-bottom: 4px;
}
</style>
