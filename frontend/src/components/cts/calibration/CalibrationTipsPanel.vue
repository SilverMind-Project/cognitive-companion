<template>
  <!-- Tips panel -->
  <v-expansion-panels class="mt-5" variant="accordion">
    <v-expansion-panel>
      <v-expansion-panel-title class="text-body-2 font-weight-medium">
        <v-icon start size="16">mdi-lightbulb-outline</v-icon>
        Tips for accurate calibration
      </v-expansion-panel-title>
      <v-expansion-panel-text>
        <v-row>
          <v-col cols="12" md="4">
            <div class="text-subtitle-2 mb-2">Choose good points</div>
            <ul class="text-body-2 tip-list">
              <li>
                Pick points on the <strong>floor surface</strong>, not walls or elevated objects
              </li>
              <li>Spread points across the full camera view — avoid clustering in one area</li>
              <li>Use fixed landmarks: doorway corners, tile intersections, rug edges</li>
              <li>Avoid points that are very close to the camera's edge</li>
            </ul>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-subtitle-2 mb-2">Measure carefully</div>
            <ul class="text-body-2 tip-list">
              <li>Use a tape measure on the actual floor — never estimate by eye</li>
              <li>Measure from the same reference corner for every camera</li>
              <li>Measure horizontal and vertical distances separately (not diagonal)</li>
              <li>
                Double-check: if the floor plan shows a wall at X=5.0 m, stand there and measure
                from your origin
              </li>
            </ul>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-subtitle-2 mb-2">Interpreting errors</div>
            <ul class="text-body-2 tip-list">
              <li>Under 0.05 m: excellent — person dots will be accurate to ~5 cm</li>
              <li>0.05–0.15 m: acceptable for most use cases</li>
              <li>Over 0.3 m: re-calibrate; check measurements and point placement</li>
              <li>One "poor" point usually means a mis-click or measurement error — replace it</li>
            </ul>
          </v-col>
        </v-row>
      </v-expansion-panel-text>
    </v-expansion-panel>
  </v-expansion-panels>
</template>

<style scoped>
.tip-list {
  padding-left: 18px;
  line-height: 1.7;
}

.tip-list li {
  margin-bottom: 4px;
}
</style>
