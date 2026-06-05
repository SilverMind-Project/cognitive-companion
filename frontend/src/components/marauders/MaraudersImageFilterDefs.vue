<template>
  <svg
    class="marauders-svg-defs"
    width="0"
    height="0"
    aria-hidden="true"
    focusable="false"
  >
    <defs>
      <!-- Gentle photo treatment: soften, lift saturation, flatten tones,
           introduce a subtle brush displacement, then warm toward parchment. -->
      <filter
        id="marauders-paint"
        x="-5%"
        y="-5%"
        width="110%"
        height="110%"
        color-interpolation-filters="sRGB"
      >
        <feGaussianBlur in="SourceGraphic" stdDeviation="0.35" result="paint-soft" />
        <feColorMatrix
          in="paint-soft"
          type="saturate"
          values="1.12"
          result="paint-color"
        />
        <feComponentTransfer in="paint-color" result="paint-bands">
          <feFuncR type="discrete" tableValues="0 0.16 0.34 0.54 0.74 0.9 1" />
          <feFuncG type="discrete" tableValues="0 0.15 0.33 0.53 0.73 0.89 1" />
          <feFuncB type="discrete" tableValues="0 0.14 0.31 0.5 0.7 0.87 1" />
        </feComponentTransfer>
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.018"
          numOctaves="1"
          seed="17"
          result="paint-brush"
        />
        <feDisplacementMap
          in="paint-bands"
          in2="paint-brush"
          scale="1.25"
          xChannelSelector="R"
          yChannelSelector="G"
          result="paint-texture"
        />
        <feColorMatrix
          in="paint-texture"
          type="matrix"
          values="
            0.86 0.12 0.02 0 0.025
            0.07 0.84 0.09 0 0.018
            0.02 0.15 0.74 0 0.005
            0    0    0    1 0
          "
        />
      </filter>

      <!-- Strong treatment is opt-in for decorative imagery only. -->
      <filter
        id="marauders-paint-strong"
        x="-8%"
        y="-8%"
        width="116%"
        height="116%"
        color-interpolation-filters="sRGB"
      >
        <feGaussianBlur in="SourceGraphic" stdDeviation="0.65" result="paint-strong-soft" />
        <feColorMatrix
          in="paint-strong-soft"
          type="saturate"
          values="1.2"
          result="paint-strong-color"
        />
        <feComponentTransfer in="paint-strong-color" result="paint-strong-bands">
          <feFuncR type="discrete" tableValues="0 0.2 0.43 0.68 0.86 1" />
          <feFuncG type="discrete" tableValues="0 0.18 0.41 0.65 0.84 1" />
          <feFuncB type="discrete" tableValues="0 0.16 0.37 0.61 0.81 1" />
        </feComponentTransfer>
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.026"
          numOctaves="2"
          seed="29"
          result="paint-strong-brush"
        />
        <feDisplacementMap
          in="paint-strong-bands"
          in2="paint-strong-brush"
          scale="2.25"
          xChannelSelector="R"
          yChannelSelector="G"
          result="paint-strong-texture"
        />
        <feColorMatrix
          in="paint-strong-texture"
          type="matrix"
          values="
            0.82 0.15 0.03 0 0.035
            0.09 0.8  0.11 0 0.025
            0.03 0.18 0.67 0 0.008
            0    0    0    1 0
          "
        />
      </filter>

      <filter
        id="marauders-heat-blur"
        x="-25%"
        y="-25%"
        width="150%"
        height="150%"
        color-interpolation-filters="sRGB"
      >
        <feGaussianBlur stdDeviation="6" />
      </filter>
      <linearGradient id="marauders-heat-ramp" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="var(--cc-heat-ink-low)" />
        <stop offset="100%" stop-color="var(--cc-heat-ink-high)" />
      </linearGradient>
    </defs>
  </svg>
</template>

<style scoped>
.marauders-svg-defs {
  position: absolute;
  overflow: hidden;
  pointer-events: none;
}
</style>
